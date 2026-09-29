"""Smoke test dos ambientes biguagym no BiguaSim.

Uso:
    python smoke_test.py --list
    python smoke_test.py --env DjiMatriceLand-v0 --steps 200
    python smoke_test.py --all --filter v0 --steps 200 --frame-every 100
    python smoke_test.py --all --filter v0 --filter DjiMatrice,BlueBoat,BlueROV --show-viewer

``--filter`` pode ser repetido: vírgula = OU dentro do filtro, filtros repetidos = E.

Roteiro de ações fixas (em vez de ações aleatórias), com modo de controle opcional:
    python smoke_test.py --env BlueBoatNav-v0 --show-viewer --no-reset --tag motores \
        --action 'parado@40:0,0;frente@100:150,150;giro_esq@60:-120,120'
    python smoke_test.py --env BlueBoatNav-v0 --control cmd_vel --action 'frente@100:1,0,0'
Cada segmento é ``[rótulo@]N:v1,v2,...`` (N passos com a mesma ação), separados por ``;``.
Sem ``N:`` a ação vale para todos os ``--steps``. Com ``--action`` o script também grava
``trajectory.csv`` (posição, atitude, velocidade e ação por passo) e um resumo por segmento.

Seguir um percurso do biguagym (``TrajectoryEnv``) em malha fechada, com ``cmd_pos_yaw``:
    python smoke_test.py --env BlueBoatNav-v0 --show-viewer --no-reset --follow figure8 --lookahead 1.5 --steps 3000
A cada passo o alvo é o ponto ``--lookahead`` m à frente do ponto do percurso mais próximo do barco
(busca só para frente, para não pular de laço no cruzamento do 8). ``--steps`` é o máximo; o
roteiro termina ao completar o percurso. Grava ``trajetoria.png`` e as métricas em ``follow``.

Para cada ambiente: cria com ``gym.make`` (como o ``run.py``), faz ``reset`` e
``--steps`` passos com ações aleatórias, e grava em ``smoke_results/<env>/``:

- ``summary.json``: espaços, sensores, velocidade, NaN/inf, ``obs_in_space``,
  posição inicial/final, VRAM e estado do processo do simulador após ``close()``;
- ``frames/cam_<sensor>_<step>.png``: imagens cruas das câmeras do simulador;
- ``frames/obs_<canal>_<step>.png``: (só v1) o último frame da pilha que a rede
  recebe, lido como (3, H, W) -> (H, W, 3) e ampliado sem interpolação.

Com ``--all`` cada ambiente roda num processo filho (com timeout), e o resumo
vai para ``smoke_results/resumo.csv``.

Este script não altera o código dos ambientes. Como ``BiguaGymEnv.close()`` só
faz ``del self._env``, depois do ``close()`` ele registra se o simulador ainda
está vivo e então o encerra com ``__on_exit__()`` para não deixar órfãos.
"""

import argparse
import csv
import json
import os
import re
import subprocess
import sys
import time
import traceback

import numpy as np

ROOT = os.path.dirname(os.path.abspath(__file__))
BIGUAGYM_DIR = os.path.join(ROOT, 'biguagym')
SIM_PATTERN = re.compile(r'biguasim|holodeck|unreal', re.IGNORECASE)


def register_envs():
    """Mesmo esquema do run.py: biguagym/ no sys.path + import register."""
    if BIGUAGYM_DIR not in sys.path:
        sys.path.insert(0, BIGUAGYM_DIR)
    import gymnasium as gym
    import register  # noqa: F401
    return sorted(
        k for k, spec in gym.registry.items()
        if isinstance(spec.entry_point, str) and spec.entry_point.startswith('core.environments')
    )


# ---------------------------------------------------------------------------
# Utilidades
# ---------------------------------------------------------------------------

def sim_processes():
    """Processos do simulador (mesmo filtro do CLAUDE.md), exceto este script."""
    out = subprocess.run(['ps', '-eo', 'pid,etimes,rss,args'], capture_output=True, text=True).stdout
    procs = []
    for line in out.splitlines()[1:]:
        parts = line.split(None, 3)
        if len(parts) < 4 or not SIM_PATTERN.search(parts[3]):
            continue
        if 'smoke_test.py' in parts[3] or 'grep' in parts[3]:
            continue
        procs.append({'pid': int(parts[0]), 'etimes': int(parts[1]),
                      'rss_mb': int(parts[2]) // 1024, 'cmd': parts[3][:160]})
    return procs


def vram_used_mb():
    try:
        out = subprocess.run(['nvidia-smi', '--query-gpu=memory.used', '--format=csv,noheader,nounits'],
                             capture_output=True, text=True, timeout=10).stdout
        return int(out.strip().splitlines()[0])
    except Exception:
        return None


def to_jsonable(x):
    if isinstance(x, dict):
        return {str(k): to_jsonable(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [to_jsonable(v) for v in x]
    if isinstance(x, np.ndarray):
        return x.tolist()
    if isinstance(x, (np.floating, np.integer, np.bool_)):
        return x.item()
    return x


def describe_space(space):
    from gymnasium import spaces
    if isinstance(space, spaces.Dict):
        return {k: describe_space(v) for k, v in space.spaces.items()}
    if isinstance(space, spaces.Box):
        low, high = np.unique(space.low), np.unique(space.high)
        return {'type': 'Box', 'shape': list(space.shape), 'dtype': str(space.dtype),
                'low': low.tolist() if low.size <= 4 else f'{low.size} valores',
                'high': high.tolist() if high.size <= 4 else f'{high.size} valores'}
    return {'type': type(space).__name__, 'repr': repr(space)}


def space_dim(space):
    """Dimensão legível para a tabela: '19' ou 'rgb:9x84x84'."""
    from gymnasium import spaces
    if isinstance(space, spaces.Dict):
        return ' '.join(f"{k}:{'x'.join(map(str, v.shape))}" for k, v in space.spaces.items())
    return 'x'.join(map(str, space.shape))


def iter_arrays(obs):
    if isinstance(obs, dict):
        for k, v in obs.items():
            yield k, np.asarray(v)
    else:
        yield 'obs', np.asarray(obs)


def not_in_space_reason(space, obs):
    """Explica por que ``obs`` não está em ``space`` (shape/dtype/limites)."""
    from gymnasium import spaces
    if isinstance(space, spaces.Dict):
        if set(space.spaces) != set(obs):
            return f'chaves {sorted(obs)} != {sorted(space.spaces)}'
        return '; '.join(f'{k}: {r}' for k, s in space.spaces.items()
                         if (r := not_in_space_reason(s, obs[k])))
    a = np.asarray(obs)
    if space.contains(a):
        return ''
    if a.shape != space.shape:
        return f'shape {a.shape} != {space.shape}'
    if not np.can_cast(a.dtype, space.dtype):
        return f'dtype {a.dtype} != {space.dtype}'
    return 'fora dos limites'


def as_image(value):
    """Converte leitura de sensor em imagem HxWx3 uint8 (ou None se não for imagem)."""
    if isinstance(value, dict):
        value = value.get('depth_map')
        if value is None:
            return None
    a = np.asarray(value)
    if a.ndim == 4 and a.shape[0] == 1:
        a = a[0]
    if a.ndim == 2 and min(a.shape) >= 32:
        a = np.stack([a] * 3, axis=-1)
    if a.ndim != 3 or a.shape[2] not in (3, 4) or min(a.shape[:2]) < 32:
        return None
    a = a[:, :, :3]
    if a.dtype != np.uint8:
        f = a.astype(np.float32)
        lo, hi = np.nanmin(f), np.nanmax(f)
        a = ((f - lo) / (hi - lo) * 255 if hi > lo else np.zeros_like(f)).astype(np.uint8)
    return a


def save_png(path, img):
    import cv2
    # Salva o array como veio (o simulador entrega BGR(A), a mesma convenção que
    # BiguaGymEnv._write_frame assume ao gravar vídeo).
    cv2.imwrite(path, np.ascontiguousarray(img))


def save_obs_frames(frames_dir, obs, step, scale=4):
    """Último frame (3, H, W) de cada canal pixel da observação."""
    import cv2
    if not isinstance(obs, dict):
        return
    for ch, arr in obs.items():
        arr = np.asarray(arr)
        if arr.ndim != 3:
            continue
        last = arr[-3:].transpose(1, 2, 0)
        img = as_image(last) if last.dtype != np.uint8 else last
        if img is None:
            continue
        h, w = img.shape[:2]
        img = cv2.resize(img, (w * scale, h * scale), interpolation=cv2.INTER_NEAREST)
        save_png(os.path.join(frames_dir, f'obs_{ch}_{step:05d}.png'), img)


def summarize_traj(traj, env_dir, dt=0.05, stall=0.05):
    """Grava trajectory.csv e resume cada segmento (deslocamento, velocidade, paradas)."""
    xyz = np.array([[t['x'], t['y'], t['z']] for t in traj])
    speed = np.r_[0.0, np.linalg.norm(np.diff(xyz[:, :2], axis=0), axis=1) / dt]
    for t, v in zip(traj, speed):
        t['speed_xy'] = v
    with open(os.path.join(env_dir, 'trajectory.csv'), 'w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=list(traj[0]))
        w.writeheader()
        for t in traj:
            w.writerow({k: (round(v, 4) if isinstance(v, float) else v) for k, v in t.items()})
    out, start = [], 0
    for i in range(1, len(traj) + 1):
        if i == len(traj) or traj[i]['seg'] != traj[start]['seg']:
            seg, sp = traj[start:i], speed[start:i]
            p0, p1 = xyz[start], xyz[i - 1]
            # 'travadas': passos quase parados no meio de um segmento em que o barco anda
            moving = sp.mean() > 2 * stall
            out.append({
                'seg': seg[0]['seg'], 'steps': len(seg), 'action': seg[0]['action'],
                'pos_start': p0.round(3).tolist(), 'pos_end': p1.round(3).tolist(),
                'dist_xy_m': round(float(np.linalg.norm(p1[:2] - p0[:2])), 3),
                'path_xy_m': round(float(sp.sum() * dt), 3),
                'dz_m': round(float(p1[2] - p0[2]), 3),
                'z_min_max': [round(float(xyz[start:i, 2].min()), 3), round(float(xyz[start:i, 2].max()), 3)],
                'yaw_start_end_deg': [round(seg[0]['yaw'], 1), round(seg[-1]['yaw'], 1)],
                'roll_pitch_max_deg': [round(max(abs(t['roll']) for t in seg), 1),
                                       round(max(abs(t['pitch']) for t in seg), 1)],
                'speed_xy_mean': round(float(sp.mean()), 3), 'speed_xy_max': round(float(sp.max()), 3),
                'speed_xy_cv': round(float(sp.std() / sp.mean()), 3) if sp.mean() > 0 else None,
                'stall_steps': int((sp < stall).sum()) if moving else None,
                'terminated_steps': sum(t['terminated'] for t in seg),
            })
            start = i
    return out


class PathFollower:
    """Pure pursuit sobre um percurso do biguagym (TrajectoryEnv), gerando alvos para cmd_pos_yaw."""

    def __init__(self, shape, origin, lookahead=1.5, laps=1, window=2.0):
        from core.environments import TrajectoryEnv as T
        local = {'figure8': T._figure8_trajectory, 'sine': T._sine_trajectory}[shape]()
        self.ref = T.arc_length_parameterize(local)[:, :2] + np.asarray(origin[:2], dtype=float)
        self.s = np.r_[0.0, np.cumsum(np.linalg.norm(np.diff(self.ref, axis=0), axis=1))]
        self.L = float(self.s[-1])
        self.closed = bool(np.linalg.norm(self.ref[0] - self.ref[-1]) < 0.5)
        self.total = self.L * laps if self.closed else self.L
        self.lookahead, self.window, self.progress = lookahead, window, 0.0

    def point(self, s):
        s = s % self.L if self.closed else min(s, self.L)
        return np.array([np.interp(s, self.s, self.ref[:, 0]), np.interp(s, self.s, self.ref[:, 1])])

    def target(self, pos_xy):
        cand = np.linspace(self.progress, min(self.progress + self.window, self.total), 80)
        pts = np.array([self.point(c) for c in cand])
        k = int(np.argmin(np.linalg.norm(pts - pos_xy, axis=1)))
        self.progress = float(cand[k])
        return self.point(min(self.progress + self.lookahead, self.total))

    @property
    def done(self):
        return self.progress >= self.total - 0.3

    def report(self, xy, env_dir, title):
        dev = np.min(np.linalg.norm(xy[:, None] - self.ref[None], axis=2), axis=1)
        cov = np.min(np.linalg.norm(self.ref[:, None] - xy[None], axis=2), axis=1) < 0.5
        try:
            import matplotlib
            matplotlib.use('Agg')
            import matplotlib.pyplot as plt
            fig, ax = plt.subplots(figsize=(7, 5))
            ax.plot(self.ref[:, 0], self.ref[:, 1], '--', color='gray', label='referência')
            ax.plot(xy[:, 0], xy[:, 1], label='veículo')
            ax.plot(*xy[0], 'go', label='início')
            ax.set_aspect('equal'); ax.legend(fontsize=8); ax.set_title(title)
            fig.savefig(os.path.join(env_dir, 'trajetoria.png'), dpi=90)
            plt.close(fig)
        except Exception as e:  # noqa: BLE001 — o gráfico é opcional
            print(f'sem gráfico: {e}', file=sys.stderr)
        return {'length_m': round(self.L, 2), 'completed': self.done,
                'progress_m': round(self.progress, 2), 'total_m': round(self.total, 2),
                'dev_mean_m': round(float(dev.mean()), 3), 'dev_max_m': round(float(dev.max()), 3),
                'pct_steps_within_0_5m': round(100 * float((dev < 0.5).mean()), 1),
                'coverage_pct': round(100 * float(cov.mean()), 1)}


def parse_program(text, default_steps):
    """'rot@N:v1,v2;N:v1,v2' ou 'v1,v2' -> [(rótulo, N, [valores]), ...]."""
    segs = []
    for k, part in enumerate(p for p in text.split(';') if p.strip()):
        label, _, rest = part.rpartition('@')
        n, _, vals = rest.rpartition(':')
        n = int(n) if n else default_steps
        segs.append((label.strip() or f'seg{k}', n, [float(v) for v in vals.split(',')]))
    return segs


# ---------------------------------------------------------------------------
# Um ambiente
# ---------------------------------------------------------------------------

def run_one(env_id, steps, frame_every, out_dir, seed, show_viewer=False,
            control=None, program=None, no_reset=False, tag=None,
            follow=None, lookahead=1.5, laps=1):
    import gymnasium as gym

    env_dir = os.path.join(out_dir, f'{env_id}__{tag}' if tag else env_id)
    segments = parse_program(program, steps) if program else None
    if segments:
        steps = sum(n for _, n, _ in segments)
    frames_dir = os.path.join(env_dir, 'frames')
    os.makedirs(frames_dir, exist_ok=True)
    for f in os.listdir(frames_dir):
        os.remove(os.path.join(frames_dir, f))

    s = {'env': env_id, 'status': 'erro', 'steps_requested': steps, 'seed': seed,
         'date': time.strftime('%Y-%m-%d %H:%M:%S'), 'vram_before_mb': vram_used_mb(),
         'sim_procs_before': len(sim_processes()), 'show_viewer': show_viewer,
         'control': control, 'program': program, 'no_reset': no_reset,
         'follow': follow, 'lookahead': lookahead if follow else None}
    env = sim = None
    captured = {}

    def hook(u):
        orig = u._wrap_state

        def wrapped(state):
            captured['state'] = state
            return orig(state)
        u._wrap_state = wrapped

    def position(u):
        d = getattr(u, '_dynamics', None)
        return None if d is None else np.asarray(d[6:9], dtype=float).round(3).tolist()

    def save_cams(step):
        for name, value in (captured.get('state') or {}).items():
            img = as_image(value)
            if img is not None:
                save_png(os.path.join(frames_dir, f'cam_{name}_{step:05d}.png'), img)

    try:
        t0 = time.perf_counter()
        make_kwargs = {'show_viewer': show_viewer}
        if control:
            make_kwargs['control_abstraction'] = control
        env = gym.make(env_id, **make_kwargs)
        s['make_s'] = round(time.perf_counter() - t0, 2)
        u = env.unwrapped
        sim = u.__dict__.get('_env')
        proc = getattr(sim, '_world_process', None)
        s['sim_pid'] = proc.pid if proc is not None else None
        s['vram_after_make_mb'] = vram_used_mb()
        hook(u)

        s['env_class'] = type(u).__name__
        s['agent_type'] = getattr(u, '_agent_type', None)
        s['max_episode_steps'] = getattr(u, 'max_episode_steps', None)
        s['observation_space'] = describe_space(env.observation_space)
        s['action_space'] = describe_space(env.action_space)
        s['obs_dim'] = space_dim(env.observation_space)
        s['act_dim'] = space_dim(env.action_space)
        s['observation_type'] = to_jsonable(getattr(u, '_observation_type', None))
        robot = next(a for a in u.env_cfg['agents'] if a['agent_name'] == 'robot')
        s['sensors_config'] = [
            {'name': x.get('sensor_name', x['sensor_type']), 'type': x['sensor_type'],
             **({'res': [x['configuration']['CaptureWidth'], x['configuration']['CaptureHeight']]}
                if 'CaptureWidth' in x.get('configuration', {}) else {})}
            for x in robot['sensors']]
        s['ticks_per_sec'] = u.env_cfg.get('ticks_per_sec')
        s['frames_per_sec'] = u.env_cfg.get('frames_per_sec')

        env.action_space.seed(seed)
        t0 = time.perf_counter()
        obs, _ = env.reset(seed=seed)
        s['reset_s'] = round(time.perf_counter() - t0, 2)
        s['sensors_state'] = {
            k: (to_jsonable({kk: list(np.shape(vv)) for kk, vv in v.items()}) if isinstance(v, dict)
                else {'shape': list(np.shape(v)), 'dtype': str(np.asarray(v).dtype)})
            for k, v in (captured.get('state') or {}).items()}
        s['pos_initial'] = position(u)
        target = getattr(u, '_target', None)
        s['target'] = None if target is None else np.asarray(target, dtype=float).round(3).tolist()

        nan_obs = inf_obs = not_in_space = 0
        first_not_in_space = None
        rewards, step_times, ep_lens = [], [], []
        episodes, ep_len = 1, 0
        terminated_n = truncated_n = 0

        def check(o, step):
            nonlocal nan_obs, inf_obs, not_in_space, first_not_in_space
            for _, a in iter_arrays(o):
                if np.issubdtype(a.dtype, np.floating):
                    nan_obs += int(np.isnan(a).any())
                    inf_obs += int(np.isinf(a).any())
            if not env.observation_space.contains(o):
                not_in_space += 1
                if first_not_in_space is None:
                    first_not_in_space = f'step {step}: {not_in_space_reason(env.observation_space, o)}'

        check(obs, 0)
        save_cams(0)
        save_obs_frames(frames_dir, obs, 0)

        seq = [(lab, np.asarray(v, dtype=np.float32)) for lab, n, v in segments for _ in range(n)] if segments else None
        follower = PathFollower(follow, u._location, lookahead, laps) if follow else None
        traj = []

        def pose(u):
            d = np.asarray(u._dynamics, dtype=float)
            return d[6:9], np.degrees(d[15:18])

        wall0 = time.perf_counter()
        save_t = 0.0  # tempo salvando PNG, descontado do tempo de parede
        for i in range(1, steps + 1):
            if follower:
                if follower.done:
                    break
                cx, cy = follower.target(pose(u)[0][:2])
                label, a = f'follow_{follow}', np.array([cx, cy, 0.0, 0.0], dtype=np.float32)
            else:
                label, a = seq[i - 1] if seq else ('random', env.action_space.sample())
            t = time.perf_counter()
            obs, r, term, trunc, info = env.step(a)
            step_times.append(time.perf_counter() - t)
            rewards.append(float(r))
            ep_len += 1
            check(obs, i)
            if seq or follower:
                pos, rpy = pose(u)
                traj.append({'step': i, 'seg': label, 'x': pos[0], 'y': pos[1], 'z': pos[2],
                             'roll': rpy[0], 'pitch': rpy[1], 'yaw': rpy[2],
                             'action': ' '.join(f'{v:g}' for v in a), 'reward': float(r),
                             'terminated': bool(term), 'truncated': bool(trunc)})
                if seq and (i == len(seq) or seq[i][0] != label):  # fim do segmento: salva o frame
                    t = time.perf_counter()
                    save_cams(i)
                    save_t += time.perf_counter() - t
            if frame_every and i % frame_every == 0:
                t = time.perf_counter()
                save_cams(i)
                save_obs_frames(frames_dir, obs, i)
                save_t += time.perf_counter() - t
            if term or trunc:
                terminated_n += int(term)
                truncated_n += int(trunc)
                ep_lens.append(ep_len)
                ep_len = 0
                if i < steps and not no_reset:
                    obs, _ = env.reset()
                    episodes += 1
                    check(obs, i)
        wall = time.perf_counter() - wall0 - save_t
        if ep_len:
            ep_lens.append(ep_len)

        st = np.asarray(step_times)
        rw = np.asarray(rewards)
        s.update({
            'steps_done': len(st),
            'steps_per_s': round(len(st) / st.sum(), 2),
            'steps_per_s_wall': round(len(st) / wall, 2),
            'step_ms_mean': round(1000 * st.mean(), 2),
            'step_ms_p95': round(1000 * np.percentile(st, 95), 2),
            'step_ms_max': round(1000 * st.max(), 2),
            'hours_per_100k': round(100_000 / (len(st) / wall) / 3600, 2),
            'episodes': episodes, 'terminated': terminated_n, 'truncated': truncated_n,
            'episode_lengths': ep_lens,
            'obs_nan_steps': nan_obs, 'obs_inf_steps': inf_obs,
            'reward_nan': int(np.isnan(rw).sum()), 'reward_inf': int(np.isinf(rw).sum()),
            'reward_min': float(np.nanmin(rw)), 'reward_max': float(np.nanmax(rw)),
            'reward_mean': float(np.nanmean(rw)),
            'obs_in_space': not_in_space == 0,
            'obs_not_in_space_steps': not_in_space,
            'obs_not_in_space_first': first_not_in_space,
            'pos_final': position(u),
            **({'segments': summarize_traj(traj, env_dir)} if traj else {}),
            **({'follow_result': follower.report(np.array([[t['x'], t['y']] for t in traj]), env_dir,
                                                 f'{env_id} — {follow} (lookahead {lookahead} m)')}
               if follower and traj else {}),
            'last_info': to_jsonable(info),
            'vram_end_mb': vram_used_mb(),
        })
        s['status'] = 'ok'
    except BaseException as e:  # noqa: BLE001 — queremos registrar qualquer falha
        s['error'] = f'{type(e).__name__}: {e}'
        s['traceback'] = traceback.format_exc()
        print(s['traceback'], file=sys.stderr, flush=True)
    finally:
        # 1) close() do jeito que o harness chama; 2) o simulador sobrevive?
        proc = getattr(sim, '_world_process', None)
        if env is not None:
            try:
                env.close()
            except Exception as e:  # noqa: BLE001
                s['close_error'] = f'{type(e).__name__}: {e}'
        if proc is not None:
            time.sleep(2)
            s['sim_alive_after_env_close'] = proc.poll() is None
            try:
                sim.__on_exit__()
            except Exception as e:  # noqa: BLE001
                s['on_exit_error'] = f'{type(e).__name__}: {e}'
            s['sim_alive_after_on_exit'] = proc.poll() is None
        s['sim_procs_after'] = len(sim_processes())
        s['vram_after_close_mb'] = vram_used_mb()
        with open(os.path.join(env_dir, 'summary.json'), 'w') as f:
            json.dump(to_jsonable(s), f, indent=2, ensure_ascii=False)
    return s


# ---------------------------------------------------------------------------
# Vários ambientes (um processo filho por ambiente)
# ---------------------------------------------------------------------------

CSV_FIELDS = ['env', 'status', 'steps_done', 'steps_per_s', 'steps_per_s_wall', 'hours_per_100k',
              'obs_dim', 'act_dim', 'obs_nan_steps', 'obs_inf_steps', 'reward_nan', 'obs_in_space',
              'episodes', 'make_s', 'sim_alive_after_env_close', 'sim_procs_after', 'error']


def run_all(ids, args):
    rows = []
    csv_path = os.path.join(args.out, 'resumo.csv')
    for n, env_id in enumerate(ids, 1):
        print(f'[{n}/{len(ids)}] {env_id} ...', flush=True)
        env_dir = os.path.join(args.out, env_id)
        os.makedirs(env_dir, exist_ok=True)
        summary_path = os.path.join(env_dir, 'summary.json')
        if os.path.exists(summary_path):
            os.remove(summary_path)
        cmd = [sys.executable, os.path.abspath(__file__), '--env', env_id, '--steps', str(args.steps),
               '--frame-every', str(args.frame_every), '--out', args.out, '--seed', str(args.seed)]
        if args.show_viewer:
            cmd.append('--show-viewer')
        with open(os.path.join(env_dir, 'log.txt'), 'w') as log:
            try:
                rc = subprocess.run(cmd, stdout=log, stderr=subprocess.STDOUT, timeout=args.timeout).returncode
            except subprocess.TimeoutExpired:
                rc = 'timeout'
        if os.path.exists(summary_path):
            with open(summary_path) as f:
                s = json.load(f)
        else:
            s = {'env': env_id, 'status': 'erro', 'error': f'processo filho terminou sem summary (rc={rc})'}
        s['returncode'] = rc
        leftover = sim_processes()
        s['sim_procs_after'] = len(leftover)
        if leftover:
            print(f'   ATENÇÃO: {len(leftover)} processo(s) do simulador abertos: '
                  f'{[p["pid"] for p in leftover]}', flush=True)
        print(f"   {s['status']}  {s.get('steps_per_s', '-')} steps/s  obs={s.get('obs_dim', '-')}  "
              f"{s.get('error', '')}", flush=True)
        rows.append(s)
        with open(csv_path, 'w', newline='') as f:
            w = csv.DictWriter(f, fieldnames=CSV_FIELDS, extrasaction='ignore')
            w.writeheader()
            for row in rows:
                w.writerow({k: (str(row.get(k, '')).splitlines() or [''])[0] for k in CSV_FIELDS})
    ok = sum(r['status'] == 'ok' for r in rows)
    print(f'\n{ok}/{len(rows)} ok. Resumo em {csv_path}')
    return rows


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--list', action='store_true', help='lista os ids registrados')
    p.add_argument('--env', help='roda um ambiente (no próprio processo)')
    p.add_argument('--all', action='store_true', help='roda todos (um processo filho por ambiente)')
    p.add_argument('--filter', action='append', default=[],
                   help='substring(s) do id; vírgula = OU, repetir o argumento = E '
                        '(ex.: --filter v0 --filter DjiMatrice,BlueBoat)')
    p.add_argument('--action', default=None,
                   help="roteiro de ações fixas: '[rótulo@]N:v1,v2;...' (ver docstring)")
    p.add_argument('--control', default=None,
                   help='control_abstraction (cmd_motor_speeds, cmd_vel, cmd_vel_yaw, cmd_pos_yaw)')
    p.add_argument('--no-reset', action='store_true',
                   help='com --action: não reseta ao terminar o episódio (o movimento segue contínuo)')
    p.add_argument('--tag', default=None, help='sufixo da pasta de saída: <env>__<tag>')
    p.add_argument('--follow', choices=['figure8', 'sine'], default=None,
                   help='segue o percurso do biguagym em malha fechada (usa cmd_pos_yaw)')
    p.add_argument('--lookahead', type=float, default=1.5, help='distância do alvo à frente no percurso (m)')
    p.add_argument('--laps', type=int, default=1, help='voltas em percursos fechados (figure8)')
    p.add_argument('--show-viewer', action='store_true',
                   help='abre a janela do simulador (steps/s pode não representar o treino)')
    p.add_argument('--steps', type=int, default=200)
    p.add_argument('--frame-every', type=int, default=20, help='salva frames a cada N steps (0 = só o reset)')
    p.add_argument('--seed', type=int, default=0)
    p.add_argument('--timeout', type=int, default=600, help='timeout por ambiente no --all (s)')
    p.add_argument('--out', default=os.path.join(ROOT, 'smoke_results'))
    args = p.parse_args()

    ids = register_envs()
    for f in args.filter:
        alts = [a for a in f.split(',') if a]
        ids = [i for i in ids if any(a in i for a in alts)]

    if args.list:
        for i in ids:
            print(i)
        print(f'\n{len(ids)} ids')
        return 0
    os.makedirs(args.out, exist_ok=True)
    if args.env:
        s = run_one(args.env, args.steps, args.frame_every, args.out, args.seed, args.show_viewer,
                    args.control or ('cmd_pos_yaw' if args.follow else None), args.action,
                    args.no_reset, args.tag, args.follow, args.lookahead, args.laps)
        print(json.dumps({k: s.get(k) for k in CSV_FIELDS}, indent=2, ensure_ascii=False, default=str))
        return 0 if s['status'] == 'ok' else 1
    if args.all:
        rows = run_all(ids, args)
        return 0 if all(r['status'] == 'ok' for r in rows) else 1
    p.print_help()
    return 2


if __name__ == '__main__':
    sys.exit(main())
