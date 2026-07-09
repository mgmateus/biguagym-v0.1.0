import argparse as _argparse

# --- Python 3.14 / Hydra 1.3.2 compatibility shim ---
# Python 3.14 added an eager `_check_help` hook in argparse that string-formats
# every argument's help at add_argument() time. Hydra's `--shell-completion`
# passes a lazy help *object* (only __repr__), so the eager check raises
# "badly formed help string" before @hydra.main can run. The hook is a 3.14-only
# validation step; disabling it restores the pre-3.14 lazy behavior Hydra relies
# on. Must run before the Hydra arg parser is built (i.e. before main()).
if hasattr(_argparse.ArgumentParser, "_check_help"):
    _argparse.ArgumentParser._check_help = lambda self, action: None

import os
import sys

import hydra
import hydra.core
import hydra.core.global_hydra
import subprocess
import torch
import gymnasium as gym
from gymnasium.wrappers import RecordVideo
from omegaconf import OmegaConf

from config.config import Run
from logger import Logger, seed_curves, make_log_dir
from utils import gpu, get_dir

from workspace import Workspace

torch.backends.cudnn.benchmark = True

# --- biguagym registration ---
# biguagym/register.py declares env ids with bare ``core.environments:...``
# entry points, so the package dir must be importable as a top-level path.
_BIGUAGYM_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'biguagym')


def _register_biguagym_envs():
    """Put biguagym on the path and import ``register`` to declare env ids.

    Called both at module import (single run / direct ``python run.py``) and at
    the top of ``main()``. Under the joblib/loky multirun launcher each job runs
    in a fresh worker process that does *not* re-execute this module's top-level
    code before the task runs, so the gym registry would be empty there and
    ``gym.make`` raises NameNotFound. Importing ``register`` from inside
    ``main()`` guarantees registration happens in every worker. The ``import``
    is cached in ``sys.modules``, so repeated calls in one process are no-ops
    and the ``gym.register`` calls fire exactly once per process.
    """
    if _BIGUAGYM_DIR not in sys.path:
        sys.path.insert(0, _BIGUAGYM_DIR)
    import register  # noqa: F401  (registers biguagym env ids on import)


_register_biguagym_envs()


def _obs_type_from_id(env_id: str) -> list:
    """Derive the observation tag from a biguagym ``-vN`` suffix.

    v0 -> state, v1 -> pixel, v2 -> range (per biguagym/register.py). This is a
    log/curve-naming tag; the real observation structure comes from the env
    itself. Override via ``obs_type=[...]`` when needed (e.g. CUPRL on pixels).
    """
    if env_id.endswith('-v1'):
        return ['pixel']
    if env_id.endswith('-v2'):
        return ['range']
    return ['state']


def _resolve_env(cfg):
    """Expand the ``env`` gym-id string into the structured node the harness
    (Workspace / Logger / curves) expects, so ``env=<GymId>`` is enough."""
    env_id = cfg.env if isinstance(cfg.env, str) else cfg.env.name
    obs_type = list(cfg.obs_type) if cfg.get('obs_type') else _obs_type_from_id(env_id)
    kwargs = OmegaConf.to_container(cfg.env_kwargs, resolve=True) if cfg.get('env_kwargs') else {}

    # CUPRL is a pixel + pose + PER agent: it needs rgb + depth + proprioceptive
    # state, and a raw frame larger than the crop size. Supply sensible defaults
    # on a pixel env unless the user overrode them.
    if cfg.get('agent') is not None and cfg.agent.get('family') == 'cuprl':
        kwargs.setdefault('pixel_channels', ['rgb', 'depth'])
        kwargs.setdefault('include_state', True)
        kwargs.setdefault('frame_size', [100, 100])

    OmegaConf.set_struct(cfg, False)
    cfg.env = OmegaConf.create({
        'name': env_id,
        'obs_params': {'type': obs_type, 'anchor': obs_type[0]},
        'kwargs': kwargs,
    })
    cfg.obs_type = obs_type
    return cfg


class GymRecorder:
    """Eval-rollout video recorder backed by ``gymnasium.wrappers.RecordVideo``.

    Wraps the eval env once and exposes the same ``record(env, path)`` /
    ``stop(env)`` hooks the train loop calls (see ``Workspace.evaluate``).
    Recording is driven manually rather than via RecordVideo's episode/step
    triggers: ``record`` opens a clip whose filename is taken from ``path`` (so
    the existing ``eval_<n>.mp4`` naming under ``video_folder`` is preserved) and
    ``stop`` flushes it. RecordVideo grabs each frame by calling the biguagym
    env's ``render()``, which returns the latest ``rgb_array`` frame, so the env
    must be built with ``render_mode="rgb_array"``; otherwise this is a no-op.
    """

    def __init__(self, env, video_folder, fps: int = 20):
        self.enabled = getattr(env, 'render_mode', None) == 'rgb_array'
        if self.enabled:
            self.env = RecordVideo(
                env,
                video_folder=video_folder,
                episode_trigger=lambda episode_id: False,  # recording is triggered manually
                name_prefix='eval',
                fps=fps,
                disable_logger=True,
            )
        else:
            self.env = env

    def record(self, env=None, path=None, **kwargs):
        if not self.enabled or path is None:
            return
        # RecordVideo saves to ``{video_folder}/{video_name}.mp4``; derive the
        # name from the requested path so the final file lands exactly there.
        video_name = os.path.splitext(os.path.basename(path))[0]
        self.env.start_recording(video_name)

    def stop(self, env=None, **kwargs):
        if self.enabled and self.env.recording:
            self.env.stop_recording()


class Experiment:
    def __init__(self, cfg):
        cfg = _resolve_env(cfg)
        self.seed, self.curves_path = seed_curves(
            cfg.env.name,
            cfg.agent.name,
            cfg.env.obs_params.type,
            cfg.num_train_steps,
            path=cfg.curves_path or None,
        )

        self.device = torch.device('cuda:' + str(gpu()) if torch.cuda.is_available() else 'cpu')
        self.__getattribute__(cfg.mode)(cfg)

    def train(self, cfg):
 
        for idx in range(self.seed, cfg.runs):
            env = gym.make(cfg.env.name)
            env.reset(seed=idx)
            env.action_space.seed(idx)

            # ``render_mode="rgb_array"`` so RecordVideo can capture eval frames.
            eval_env = gym.make(cfg.env.name, 
                                render_mode="rgb_array"
                                )
            eval_env.reset(seed=idx)
            eval_env.action_space.seed(idx)

            cfg.seed = idx

            logs_path = make_log_dir(cfg.env.name,
                                     cfg.agent.name,
                                     cfg.env.obs_params.type,
                                     run=idx,
                                     base_path=cfg.logs_path or None)

            logger = Logger(cfg, logs_path, self.curves_path,
                            env.action_space, cfg.tensorboard)
            # recorder = GymRecorder(eval_env, logger.eval_dir)

            workspace = Workspace(
                cfg, env, eval_env, env.action_space.shape,
                logger, self.device,
            )

            workspace.train()
            hydra.core.global_hydra.GlobalHydra.instance().clear()


def is_tensorboard_alive(url="http://localhost:6006"):
    try:
        import requests
        r = requests.get(url, timeout=1)
        return r.status_code == 200
    except Exception:
        return False


@hydra.main(version_base=None, config_path='config', config_name="config")
def main(cfg: Run) -> None:
    _register_biguagym_envs()  # ensure env ids exist in this (possibly worker) process
    if cfg.tensorboard and not is_tensorboard_alive():
        subprocess.Popen(["tensorboard", f"--logdir={get_dir(__file__)}/logs"])

    Experiment(cfg)


if __name__ == '__main__':
    torch.multiprocessing.set_start_method('spawn')
    main()
