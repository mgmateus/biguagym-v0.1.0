import json
import os

# Quiet libkineto's GPU-enumeration logging during the one-shot FLOPs profile.
# On some driver/CUPTI setups the C++ layer prints a harmless
# "gpuGetDeviceCount failed with code 35" at profiler init regardless of the
# requested activities; raising the kineto log level suppresses it. setdefault
# keeps any user-provided value. Must be set before the profiler first runs.
os.environ.setdefault("KINETO_LOG_LEVEL", "5")

import shutil
import threading
import time
import torch

import numpy as np
import pandas as pd
import psutil

from torch import Tensor
from collections import defaultdict
from termcolor import colored
from omegaconf.listconfig import ListConfig

# TensorBoard / torchvision are only needed when use_tb=True; import lazily so
# runs with tensorboard=false don't require the (heavier) optional deps.
try:
    import torchvision
except Exception:
    torchvision = None

try:
    from torch.utils.tensorboard import SummaryWriter
except Exception:
    SummaryWriter = None

try:
    import pynvml as _pynvml
    _pynvml.nvmlInit()
    _PYNVML_OK = True
except Exception:
    _PYNVML_OK = False

from utils import make_dir, get_dir

import logging
import sys
import faulthandler

# ---------------------------------------------------------------------------
# Crash detector
# ---------------------------------------------------------------------------


# Enable low-level crash reports
fault_file = open("fault.log", "w")
faulthandler.enable(file=fault_file)

# Configure normal logging
logging.basicConfig(
    filename="crash.log",
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(message)s",
    force=True,
)

logging.info("Logger initialized")


# Handle uncaught Python exceptions
def handle_exception(exc_type, exc_value, exc_traceback):

    # Keep Ctrl+C behavior normal
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
        return

    logging.critical(
        "Uncaught exception",
        exc_info=(exc_type, exc_value, exc_traceback),
    )


# Register global exception hook
sys.excepthook = handle_exception


# ---------------------------------------------------------------------------
# Profiler
# ---------------------------------------------------------------------------

def _gpu_mb() -> float:
    """Return current GPU memory allocated in MB (0 if no CUDA device)."""
    return torch.cuda.memory_allocated() / 1e6 if torch.cuda.is_available() else 0.0


class _RunningStats:
    """Welford's online algorithm — exact mean/variance in O(1) memory."""

    __slots__ = ('n', '_mean', '_M2', 'min', 'max', 'total')

    def __init__(self):
        self.n      = 0
        self._mean  = 0.0
        self._M2    = 0.0
        self.min    = float('inf')
        self.max    = float('-inf')
        self.total  = 0.0

    def update(self, x: float) -> None:
        self.n      += 1
        self.total  += x
        delta        = x - self._mean
        self._mean  += delta / self.n
        self._M2    += delta * (x - self._mean)
        if x < self.min:
            self.min = x
        if x > self.max:
            self.max = x

    @property
    def mean(self) -> float:
        return self._mean

    @property
    def std(self) -> float:
        return (self._M2 / (self.n - 1)) ** 0.5 if self.n >= 2 else 0.0


class _PhaseTimer:
    """Context manager that times one phase and records it in a ProfilerSession."""

    __slots__ = ('_session', '_phase', '_t0')

    def __init__(self, session: 'ProfilerSession', phase: str):
        self._session = session
        self._phase   = phase

    def __enter__(self) -> '_PhaseTimer':
        self._t0 = time.perf_counter()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self._session._record(self._phase, time.perf_counter() - self._t0)


class ProfilerSession:
    """Accumulates per-phase timing statistics for one mode (train or eval).

    Usage::

        with logger.train_profiler.record("env_step"):
            obs, reward, ... = env.step(action)

        with logger.train_profiler.record("agent_update"):
            agent.update(...)

        logger.save_profilers()   # called once at end of training
    """

    def __init__(self, mode: str, log_path: str) -> None:
        self._mode       = mode
        self._log_path   = log_path
        self._stats: dict[str, _RunningStats] = {}
        self._wall_start = time.perf_counter()
        self._gpu_start  = _gpu_mb()

    # ------------------------------------------------------------------

    def record(self, phase: str) -> _PhaseTimer:
        """Return a context manager that times ``phase``."""
        return _PhaseTimer(self, phase)

    def _record(self, phase: str, elapsed: float) -> None:
        if phase not in self._stats:
            self._stats[phase] = _RunningStats()
        self._stats[phase].update(elapsed)

    def has_data(self) -> bool:
        return bool(self._stats)

    def save(self) -> str:
        """Compute summary statistics and write ``profiler_<mode>.json``.

        Returns the path of the written file.
        """
        total_wall = time.perf_counter() - self._wall_start
        gpu_end    = _gpu_mb()

        phases: dict = {}
        for phase, s in self._stats.items():
            phases[phase] = {
                'calls':        s.n,
                'total_s':      round(s.total, 4),
                'mean_ms':      round(s.mean  * 1e3, 4),
                'std_ms':       round(s.std   * 1e3, 4),
                'min_ms':       round(s.min   * 1e3, 4),
                'max_ms':       round(s.max   * 1e3, 4),
                'pct_of_total': round(s.total / total_wall * 100, 2),
            }

        summary = {
            'mode':             self._mode,
            'total_wall_time_s': round(total_wall, 3),
            'gpu_start_mb':     round(self._gpu_start, 1),
            'gpu_end_mb':       round(gpu_end, 1),
            'phases':           phases,
        }

        out_dir  = os.path.join(self._log_path, 'profiler')
        os.makedirs(out_dir, exist_ok=True)
        out_path = os.path.join(out_dir, f'profiler_{self._mode}.json')
        with open(out_path, 'w') as f:
            json.dump(summary, f, indent=2)
        return out_path


# ---------------------------------------------------------------------------
# SystemMonitor — background thread for GPU / CPU / RAM time-series
# ---------------------------------------------------------------------------

class SystemMonitor:
    """Periodically samples GPU, CPU, and RAM metrics in a background thread.

    Outputs (written on ``stop()``)
    --------------------------------
    ``profiler/system_monitor.csv``
        Full time series — one row per sample.  Ideal for plotting curves
        against wall-clock time.

    ``profiler/system_summary.json``
        Aggregated statistics (mean / std / min / max) over the full run.

    Parameters
    ----------
    log_path:
        Base directory where the ``profiler/`` subdirectory will be created.
    sample_interval:
        Seconds between consecutive samples (default 2 s).
    """

    def __init__(self, log_path: str, sample_interval: float = 2.0) -> None:
        self._log_path  = log_path
        self._interval  = sample_interval
        self._samples:  list[dict] = []
        self._stop      = threading.Event()
        self._thread    = threading.Thread(
            target=self._run, daemon=True, name='SystemMonitor'
        )
        self._t0: float         = 0.0
        self._gpu_handle        = None
        self._gpu_name: str     = ''
        self._gpu_total_mb: float = 0.0

        if _PYNVML_OK and torch.cuda.is_available():
            try:
                idx = torch.cuda.current_device()
                self._gpu_handle   = _pynvml.nvmlDeviceGetHandleByIndex(idx)
                self._gpu_name     = _pynvml.nvmlDeviceGetName(self._gpu_handle)
                mem                = _pynvml.nvmlDeviceGetMemoryInfo(self._gpu_handle)
                self._gpu_total_mb = round(mem.total / 1e6, 1)
            except Exception:
                self._gpu_handle = None

    # ------------------------------------------------------------------

    def start(self) -> None:
        self._t0 = time.perf_counter()
        self._thread.start()

    def stop(self) -> None:
        """Signal the thread to stop and block until it exits."""
        self._stop.set()
        self._thread.join(timeout=self._interval + 2)
        self._flush()

    # ------------------------------------------------------------------

    def _run(self) -> None:
        while not self._stop.wait(self._interval):
            try:
                self._samples.append(self._sample())
            except Exception:
                pass  # never crash the training run

    def _sample(self) -> dict:
        s: dict = {'time_s': round(time.perf_counter() - self._t0, 2)}

        # ── CPU / RAM ─────────────────────────────────────────────────
        s['cpu_pct']     = psutil.cpu_percent(interval=None)
        ram              = psutil.virtual_memory()
        s['ram_used_gb'] = round(ram.used  / 1e9, 3)
        s['ram_pct']     = round(ram.percent, 1)

        # ── PyTorch allocator ─────────────────────────────────────────
        if torch.cuda.is_available():
            s['torch_alloc_mb']    = round(torch.cuda.memory_allocated() / 1e6, 1)
            s['torch_reserved_mb'] = round(torch.cuda.memory_reserved()  / 1e6, 1)

        # ── NVML (utilisation, temperature, power) ────────────────────
        if self._gpu_handle is not None:
            util                  = _pynvml.nvmlDeviceGetUtilizationRates(self._gpu_handle)
            s['gpu_util_pct']     = util.gpu
            s['gpu_mem_util_pct'] = util.memory
            mem                   = _pynvml.nvmlDeviceGetMemoryInfo(self._gpu_handle)
            s['gpu_mem_used_mb']  = round(mem.used / 1e6, 1)
            s['gpu_temp_c']       = _pynvml.nvmlDeviceGetTemperature(
                self._gpu_handle, _pynvml.NVML_TEMPERATURE_GPU
            )
            try:
                s['gpu_power_w'] = round(
                    _pynvml.nvmlDeviceGetPowerUsage(self._gpu_handle) / 1000, 1
                )
            except _pynvml.NVMLError:
                s['gpu_power_w'] = None

        return s

    def _flush(self) -> None:
        if not self._samples:
            return

        out_dir = os.path.join(self._log_path, 'profiler')
        os.makedirs(out_dir, exist_ok=True)

        df = pd.DataFrame(self._samples)
        df.to_csv(os.path.join(out_dir, 'system_monitor.csv'), index=False)

        # Aggregate summary
        numeric = df.select_dtypes(include='number').drop(columns=['time_s'], errors='ignore')
        summary: dict = {
            'gpu':     self._gpu_name,
            'gpu_total_mb': self._gpu_total_mb,
            'samples': len(df),
            'duration_s': round(df['time_s'].iloc[-1], 1) if len(df) else 0,
            'metrics': {},
        }
        for col in numeric.columns:
            col_data = numeric[col].dropna()
            if col_data.empty:
                continue
            summary['metrics'][col] = {
                'mean': round(float(col_data.mean()), 3),
                'std':  round(float(col_data.std()),  3),
                'min':  round(float(col_data.min()),  3),
                'max':  round(float(col_data.max()),  3),
            }

        with open(os.path.join(out_dir, 'system_summary.json'), 'w') as f:
            json.dump(summary, f, indent=2)


# ---------------------------------------------------------------------------
# FLOPs profiler — one-shot torch.profiler pass on agent.update()
# ---------------------------------------------------------------------------

def _profile_flops(fn, *args, **kwargs) -> dict:
    """Run *fn* once under ``torch.profiler`` and return a FLOPs summary dict.

    Only ``matmul``/``conv``-family operations are counted (torch.profiler
    limitation).  Results represent one complete ``agent.update()`` call
    including all forward and backward passes.
    """
    from torch.profiler import profile as _tprof, ProfilerActivity, record_function

    # FLOPs are derived from operator schemas (matmul/conv), so the CPU activity
    # is sufficient. Requesting CUDA activity here only adds the kineto/CUPTI GPU
    # timeline — which is unused by this summary and noisy on some driver/CUPTI
    # setups ("gpuGetDeviceCount failed"). acc_events keeps events across the
    # single profiling cycle.
    activities = [ProfilerActivity.CPU]

    with _tprof(activities=activities, with_flops=True, record_shapes=False,
                acc_events=True) as prof:
        with record_function('agent_update'):
            fn(*args, **kwargs)

    events      = prof.key_averages()
    total_flops = sum(e.flops for e in events if e.flops and e.flops > 0)
    top_ops     = sorted(
        [{'op': e.key, 'gflops': round(e.flops / 1e9, 6), 'calls': e.count}
         for e in events if e.flops and e.flops > 0],
        key=lambda x: -x['gflops'],
    )[:10]

    return {
        'total_flops':  total_flops,
        'total_gflops': round(total_flops / 1e9, 6),
        'top_ops':      top_ops,
        'note': (
            'Counted for one agent.update() call via torch.profiler. '
            'Only matmul/conv-family ops are included.'
        ),
    }


# Common console columns shown for every agent
COMMON_TRAIN_FORMAT = [
    ('step',           'S',       'int'),
    ('episode',        'EP',      'int'),
    ('episode_reward', 'R',       'float'),
    ('max_reward',     'MR',      'float'),
    ('actor_loss',     'A_LOSS',  'float'),
    ('critic_loss',    'CR_LOSS', 'float'),
    ('duration',       'D',       'time'),
]

COMMON_EVAL_FORMAT = [
    ('episode',        'EP', 'int'),
    ('mean_ep_reward', 'MR', 'float'),
    ('best_ep_reward', 'BR', 'float'),
    ('duration',       'D',  'time'),
]

# Extra columns appended to COMMON_TRAIN_FORMAT per agent
# (COMMON_TRAIN_FORMAT already carries actor_loss / critic_loss). Column metric
# names must match the meter keys produced by `Logger.log('train/<name>', ...)`
# after the leading `train/` is stripped and remaining `/` become `_`
# (e.g. 'train/alpha/loss' -> 'alpha_loss').
AGENT_TRAIN_FORMAT = {
    # off-policy continuous + entropy temperature
    'sac':      [('batch_reward',  'BR',       'float'),
                 ('alpha_loss',    'AL_LOSS',  'float'),
                 ('alpha_value',   'AL_VAL',   'float'),
                 ('actor_entropy', 'A_ENT',    'float')],
    'ddpg':     [('batch_reward',  'BR',       'float')],
    'td3':      [('batch_reward',  'BR',       'float')],
    # CURL + prioritized SAC over RGB-D + pose
    'cuprl':    [('batch_reward',  'BR',       'float'),
                 ('alpha_loss',    'AL_LOSS',  'float'),
                 ('alpha_value',   'AL_VAL',   'float'),
                 ('actor_entropy', 'A_ENT',    'float'),
                 ('curl_loss',     'CU_LOSS',  'float')],
    # on-policy PPO: actor/critic columns reused for pg/value loss + diagnostics
    'ppo':      [('entropy',       'ENT',      'float'),
                 ('approx_kl',     'KL',       'float'),
                 ('clipfrac',      'CLIP',     'float')],
    # --- legacy / other agents ---
    'sac_ae':   [('ae_loss',       'AE_LOSS',  'float')],
    'curl_sac': [('curl_loss',     'CU_LOSS',  'float')],
    'drq':      [('alpha_loss',    'AL_LOSS',  'float'),
                 ('alpha_value',   'AL_VAL',   'float'),
                 ('actor_entropy', 'A_ENT',    'float')],
    # MUJEP JEPA objective: prediction / reward / SIGReg losses, the combined
    # JEPA loss, and the (averaged) distillation-active gate.
    'mujep':    [('L_jepa',         'JEPA',    'float'),
                 ('L_pred',         'L_PRED',  'float'),
                 ('L_reward',       'L_REW',   'float'),
                 ('L_reg',          'L_REG',   'float'),
                 ('distill_active', 'DST',     'float')],
}

CAT_TO_COLOR = {
    'train': 'yellow',
    'eval':  'green',
}


def print_run(cfg, action_space):
    """Pretty-print current run metadata. Called by Logger at init."""
    prefix, color, attrs = '  ', 'green', ['bold']

    def _limstr(s, maxlen=120):
        return str(s[:maxlen]) + '...' if len(str(s)) > maxlen else s

    def _exp(cfg):
        agent = colored(f"{cfg['agent']['name']}-{'-'.join(cfg['obs_type'])}", 'yellow', attrs=attrs)
        env   = colored(f"{cfg['env']['name']}", 'yellow', attrs=attrs)
        return f'{agent}:{env}'

    def _pprint(k, v):
        print(prefix + colored(f'{k.capitalize()+":":<15}', color, attrs=attrs), _limstr(v))

    if hasattr(action_space, 'low'):  # Box (continuous) action space
        action_shape = action_space.shape
        action_range = [float(action_space.low.min()), float(action_space.high.max())]
        actions = f'Min:{action_range[0]} - Max:{action_range[1]} - Action Number:{action_shape[0]}'
    else:  # Discrete action space
        actions = f'Discrete - Action Number:{action_space.n}'

    kvs = [
        ('environment', cfg['env']['name']),
        ('steps',       f"{int(cfg['num_train_steps']):,}"),
        ('actions',     actions),
        ('experiment',  _exp(cfg)),
    ]

    w = np.max([len(_limstr(str(kv[1]))) for kv in kvs]) + 25
    div = '-' * w
    print(div)
    for k, v in kvs:
        _pprint(k, v)
    print(div)


class AverageMeter:
    """Accumulates values and returns their running mean."""

    def __init__(self):
        self._sum   = 0.0
        self._count = 0

    @staticmethod
    def _parse(v):
        if isinstance(v, np.integer):
            return int(v)
        if isinstance(v, (np.floating, np.float64)):
            return float(v)
        return v

    def update(self, value, n=1):
        self._sum   += self._parse(value) * n
        self._count += n

    def value(self):
        return self._sum / max(1, self._count)


class MetersGroup:
    def __init__(self, log_path, file_name, formating):
        self._file_name = os.path.join(log_path, file_name)
        if os.path.exists(self._file_name):
            os.remove(self._file_name)
        self._formating = formating
        self._meters    = defaultdict(AverageMeter)

    def log(self, key, value, n=1):
        self._meters[key].update(value, n)

    def _prime_meters(self):
        data = {}
        for key, meter in self._meters.items():
            if key.startswith('train'):
                key = key[len('train') + 1:]
            else:
                key = key[len('eval') + 1:]
            data[key.replace('/', '_')] = meter.value()
        return data

    def _dump_to_file(self, data: dict):
        with open(self._file_name, 'a') as f:
            f.write(json.dumps(data) + '\n')

    def _format(self, key, value, ty):
        template = '%s: '
        if ty == 'int':
            template += '%d'
        elif ty == 'float':
            template += '%.04f'
        elif ty == 'time':
            template += '%.01f s'
        else:
            raise ValueError(f'invalid format type: {ty}')
        return template % (key, value)

    def _dump_to_console(self, data, prefix):
        color  = CAT_TO_COLOR[prefix]
        pieces = ['{:5}'.format(colored(prefix, color))]
        for key, disp_key, ty in self._formating:
            value = data.get(key, 0)
            pieces.append(colored(self._format(disp_key, value, ty), color))
        print('| %s' % (' | '.join(pieces)), flush=True)

    def dump(self, step, prefix):
        if not self._meters:
            return
        data = self._prime_meters()
        data['step'] = step
        self._dump_to_file(data)
        self._dump_to_console(data, prefix)
        self._meters.clear()


# ---------------------------------------------------------------------------
# Context manager for grouped log + dump (from DRQv2/TACO pattern)
# ---------------------------------------------------------------------------

class LogAndDumpCtx:
    """
    Usage::

        with logger.log_and_dump_ctx(step, ty='train') as log:
            log('actor_loss', loss.item())
            log('critic_loss', q_loss.item())
        # metrics are dumped automatically on exit
    """

    def __init__(self, logger: 'Logger', step: int, ty: str):
        self._logger = logger
        self._step   = step
        self._ty     = ty

    def __enter__(self):
        return self

    def __call__(self, key: str, value):
        self._logger.log(f'{self._ty}/{key}', value, self._step)

    def __exit__(self, *args):
        self._logger.dump(self._step, ty=self._ty)


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------

def seed_curves(env_name: str, agent_name: str, obs_type: 'list | str',
                num_train_steps: int, path: str = None):
    curves_path = path or make_dir(''.join((get_dir(__file__), 'curves')))
    agent = agent_name.replace('-', '_')
    obs   = '_'.join(obs_type) if isinstance(obs_type, ListConfig) else obs_type
    task  = env_name.replace('-', '_')

    current_curve      = f'{agent}-{obs}-{task}.csv'
    current_curve_path = '/'.join((curves_path, current_curve))

    if os.path.isfile(current_curve_path):
        try:
            df = pd.read_csv(current_curve_path)
        except Exception:
            df = pd.DataFrame(columns=['episode', 'agent', 'observation_type', 'task',
                                       'seed', 'frame', 'episode_reward', 'duration'])
        size = len(df)
        if size > 0:
            last_frame = df['frame'].iloc[-1]
            last_seed  = int(df['seed'].iloc[-1])
            if last_frame + 1 < num_train_steps:
                df = df[df['seed'] != last_seed]
                df.to_csv(current_curve_path, index=False)
                return (last_seed, current_curve_path)
            return (last_seed + 1, current_curve_path)

    columns = ['episode', 'agent', 'observation_type', 'task', 'seed', 'frame', 'episode_reward', 'duration']
    pd.DataFrame(columns=columns).to_csv(current_curve_path, index=False)
    return (0, current_curve_path)


def make_log_dir(env_name: str, agent_name: str, obs_type, run: int = None,
                 base_path: str = None) -> str:
    """Return (and create) the per-run log directory.

    Parameters
    ----------
    base_path:
        Root directory for all logs.  Defaults to ``<project_root>/logs/``
        when ``None`` or empty.
    """
    root     = base_path if base_path else get_dir(__file__, 'logs')
    obs      = '-'.join(obs_type) if isinstance(obs_type, ListConfig) else 'state'
    base_dir = make_dir('/'.join((root, f'{agent_name}-{obs}')))
    return make_dir('/'.join((base_dir, f'{env_name}/run_{run}')))


# ---------------------------------------------------------------------------
# Logger
# ---------------------------------------------------------------------------

class Logger:
    def __init__(self, cfg, log_path, curve_path, action_space, use_tb=True):
        self._agent      = cfg['agent']['name'].replace('-', '_')
        self._obs        = cfg['obs_type']
        self._task       = cfg['env']['name'].lower()
        self._seed       = cfg['seed']
        self._curve_path = curve_path
        self._log_path   = log_path
        self._chronometer = 0
        self._curve      = []
        self.best_record = None

        if use_tb and SummaryWriter is not None:
            tb_dir = os.path.join(self._log_path, 'tb')
            # Do NOT wipe the directory: each SummaryWriter writes a uniquely
            # named event file (pid + timestamp), so old events simply coexist.
            # Removing a shared, fixed tb dir here races with any other writer
            # (a re-run or a leftover process on the same run_<idx> path), which
            # deletes its live event file mid-run and kills its writer thread.
            os.makedirs(tb_dir, exist_ok=True)
            self._sw = SummaryWriter(tb_dir)
        else:
            self._sw = None

        agent_extra   = AGENT_TRAIN_FORMAT.get(self._agent, [])
        train_format  = COMMON_TRAIN_FORMAT + agent_extra

        self._train_mg = MetersGroup(self._log_path, 'train.log', formating=train_format)
        self._eval_mg  = MetersGroup(self._log_path, 'eval.log',  formating=COMMON_EVAL_FORMAT)

        self.train_profiler  = ProfilerSession('train', log_path)
        self.eval_profiler   = ProfilerSession('eval',  log_path)
        self.system_monitor  = SystemMonitor(log_path)
        self._flops_profiled = False

        print_run(cfg, action_space)

    # --- directory properties ---

    @property
    def log_path(self):
        return self._log_path

    @property
    def eval_dir(self):
        return make_dir(self._log_path, 'eval')

    @property
    def model_dir(self):
        return make_dir(self._log_path, 'models')

    @property
    def best_model_dir(self):
        return make_dir(self._log_path, 'best_models')

    @property
    def buffer_dir(self):
        return make_dir(self._log_path, 'buffer')

    @property
    def duration(self):
        return time.time() - self._chronometer if self._chronometer else 0

    # --- TensorBoard helpers ---

    def _disable_sw(self, exc: Exception) -> None:
        """Disable TensorBoard logging after a writer failure (best-effort).

        The async event-file writer can die mid-run if its event file/directory
        is removed out from under it — e.g. a second run or a leftover writer
        racing on the shared ``run_<idx>/tb`` path that ``__init__`` wipes. That
        must not take training down: drop the writer and keep console/file logs.
        """
        if self._sw is None:
            return
        print(colored(
            f'[logger] TensorBoard logging disabled after writer error: {exc!r}. '
            f'Console/file metrics continue.', 'red'))
        try:
            self._sw.close()
        except Exception:
            pass
        self._sw = None

    def _try_sw_log(self, key, value, step):
        if self._sw is not None:
            try:
                self._sw.add_scalar(key, value, step)
            except Exception as exc:
                self._disable_sw(exc)

    def _try_sw_log_image(self, key, image, step):
        if self._sw is not None:
            try:
                assert image.dim() == 3
                grid = torchvision.utils.make_grid(image.unsqueeze(1))
                self._sw.add_image(key, grid, step)
            except Exception as exc:
                self._disable_sw(exc)

    def _try_sw_log_video(self, key, frames, step):
        if self._sw is not None:
            try:
                frames = torch.from_numpy(np.array(frames)).unsqueeze(0)
                self._sw.add_video(key, frames, step, fps=30)
            except Exception as exc:
                self._disable_sw(exc)

    def _try_sw_log_histogram(self, key, histogram, step):
        if self._sw is not None:
            try:
                self._sw.add_histogram(key, histogram, step)
            except Exception as exc:
                self._disable_sw(exc)

    # --- public logging API ---

    def log(self, key: str, value, step: int, n: int = 1):
        if isinstance(value, torch.Tensor):
            value = value.item()
        mode = key.split('/')[0]
        self._try_sw_log(key, value / n, step)
        getattr(self, f'_{mode}_mg').log(key, value, n)

    def log_metrics(self, metrics: dict, step: int, ty: str):
        """Log a dict of metrics at once. ty is 'train' or 'eval'."""
        for key, value in metrics.items():
            self.log(f'{ty}/{key}', value, step)

    def log_param(self, key: str, param, step: int):
        self.log_histogram(key + '_w', param.weight.data, step)
        if hasattr(param.weight, 'grad') and param.weight.grad is not None:
            self.log_histogram(key + '_w_g', param.weight.grad.data, step)
        if hasattr(param, 'bias') and param.bias is not None:
            self.log_histogram(key + '_b', param.bias.data, step)
            if hasattr(param.bias, 'grad') and param.bias.grad is not None:
                self.log_histogram(key + '_b_g', param.bias.grad.data, step)

    def log_image(self, key: str, image, step: int):
        self._try_sw_log_image(key, image, step)

    def log_video(self, key: str, frames, step: int):
        self._try_sw_log_video(key, frames, step)

    def log_histogram(self, key: str, histogram, step: int):
        self._try_sw_log_histogram(key, histogram, step)

    def log_and_dump_ctx(self, step: int, ty: str) -> LogAndDumpCtx:
        return LogAndDumpCtx(self, step, ty)

    # --- curve CSV ---

    def record_curve(self, episode: int, step: int, episode_reward, duration: float):
        self._curve.append({
            'episode':          episode,
            'agent':            self._agent,
            'observation_type': '-'.join(self._obs) if len(self._obs) > 1 else self._obs[-1],
            'task':             self._task,
            'seed':             self._seed,
            'frame':            step,
            'episode_reward':   episode_reward.cpu().item() if isinstance(episode_reward, Tensor) else episode_reward,
            'duration':         duration,
        })

    def flush_curve(self):
        pd.DataFrame(self._curve).to_csv(self._curve_path, mode='a', header=False, index=False)
        self._curve = []

    # --- dump and save ---

    def start_chronometer(self):
        self._chronometer = time.time()

    def dump(self, step: int, ty: str = None):
        """Flush accumulated metrics to console and file.

        ty=None dumps both train and eval groups.
        ty='train' or ty='eval' dumps only that group.
        """
        if ty is None or ty == 'train':
            self._train_mg.dump(step, 'train')
        if ty is None or ty == 'eval':
            self._eval_mg.dump(step, 'eval')

    def save(self, agent, new_best: bool, step: int):
        models = agent.save(self.model_dir)
        if new_best:
            for k, v in models.items():
                shutil.copy2(v, self.best_model_dir + f'/{k}_best.pt')
            if self.best_record and os.path.exists(self.best_record):
                shutil.copy2(self.best_record, self.best_model_dir + f'/eval_best_{step}.mp4')

    def profile_agent_flops(self, fn, *args, **kwargs) -> None:
        """Profile *fn* (one ``agent.update()`` call) for FLOPs and save to disk.

        Safe to call multiple times — only the first call does actual work.
        """
        if self._flops_profiled:
            return
        result = _profile_flops(fn, *args, **kwargs)
        out_dir = os.path.join(self._log_path, 'profiler')
        os.makedirs(out_dir, exist_ok=True)
        with open(os.path.join(out_dir, 'flops.json'), 'w') as f:
            json.dump(result, f, indent=2)
        self._flops_profiled = True
        print(colored(f'[profiler] FLOPs/update → {result["total_gflops"]:.4f} GFLOPs', 'cyan'))

    def save_profilers(self) -> None:
        """Stop system monitor and write all profiler reports to disk."""
        self.system_monitor.stop()
        for session in (self.train_profiler, self.eval_profiler):
            if session.has_data():
                path = session.save()
                print(colored(f'[profiler] {session._mode:<5} report → {path}', 'cyan'))
