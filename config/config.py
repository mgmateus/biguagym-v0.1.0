"""Lightweight config schema for the biguagym training harness.

These dataclasses document the structure of the Hydra config consumed by
``run.py`` / ``Workspace`` / ``Logger``. They are intentionally permissive
(``agent`` / ``env`` are free-form ``DictConfig`` nodes) because each agent
group carries Hydra ``_target_`` instantiate nodes with heterogeneous fields.
``run.py`` imports :class:`Run` only as the type annotation for ``main(cfg)``;
the actual values come from ``config/config.yaml`` and its groups.
"""

from dataclasses import dataclass, field
from typing import Any, List, Optional


@dataclass
class Run:
    # which Experiment method to dispatch (currently only "train")
    mode: str = "train"
    # number of independent seeds/runs
    runs: int = 1
    # current run seed (set per-run by Experiment.train)
    seed: int = 0
    # launch / attach a TensorBoard server
    tensorboard: bool = False
    # output roots ('' -> default under project root)
    curves_path: str = ""
    logs_path: str = ""

    # training schedule
    num_train_steps: int = 1_000_000
    num_eval_episodes: int = 5
    eval_freq: int = 10_000
    # first step at which updates may run (off-policy warmup; 0 for PPO)
    init_steps: int = 5_000

    # environment gym id, e.g. "BlueBoatNav-v0" (override with env=<GymId>);
    # run.py expands it into a structured node {name, obs_params, kwargs}.
    env: str = "BlueBoatNav-v0"
    # extra kwargs forwarded to gym.make (pixel_channels, frame_size, ...)
    env_kwargs: Any = field(default_factory=dict)
    # observation tag for the Logger; null -> derived from the -vN suffix
    obs_type: Optional[List[str]] = None

    # agent config group (free-form: see config/agent/*.yaml)
    agent: Any = None
