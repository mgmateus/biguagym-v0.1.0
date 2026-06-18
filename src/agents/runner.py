"""Agent runners (adapters) that bridge the packaged ``src/agents/*`` agents to
the shared :class:`Workspace` train/eval loop.

The packaged agents are self-contained and expect the replay buffer to be
*injected* into ``update`` (``update(buffer, logger, step)`` for the off-policy
and CURL agents, ``update(buffer, logger)`` for PPO). Their action / storage
cadences differ (off-policy continuous, on-policy PPO, pixel + pose PER), so each
family gets a thin runner exposing one uniform interface the Workspace calls:

    runner.act(obs, eval_mode, step) -> np.ndarray   # action for env.step
    runner.store(obs, action, reward, next_obs, done, truncated)
    runner.ready(step) -> bool                        # is an update due?
    runner.update(logger, step)                       # one learning update
    runner.train(mode) / runner.training              # for utils.eval_mode
    runner.save(model_dir) / runner.load(model_dir, step)

Each runner owns its buffer (built from ``replay_buffer.py``) so the Workspace
loop stays agent-agnostic. Networks and agents are built with
``hydra.utils.instantiate`` from the per-agent config group, with env-derived
shapes injected here.
"""

import hydra
import numpy as np
import torch
from gymnasium import spaces

from replay_buffer import ReplayBuffer, RolloutBuffer, PrioritizedReplayBuffer


# ---------------------------------------------------------------------------
# Shape helpers
# ---------------------------------------------------------------------------

def _box_shape(space) -> tuple:
    return tuple(int(d) for d in space.shape)


def _action_dim(action_space) -> int:
    return int(np.prod(action_space.shape))


def _action_bounds(action_space) -> tuple:
    """Return ``(high, low)`` arrays, matching the DDPG/TD3 Actor convention."""
    high = np.asarray(action_space.high, dtype=np.float32)
    low = np.asarray(action_space.low, dtype=np.float32)
    return (high, low)


# ---------------------------------------------------------------------------
# Off-policy continuous: SAC / DDPG / TD3
# ---------------------------------------------------------------------------

class OffPolicyRunner:
    """SAC / DDPG / TD3: per-step updates from a uniform ``ReplayBuffer``."""

    def __init__(self, agent, buffer, action_space, learning_starts, device):
        self.agent = agent
        self.buffer = buffer
        self.action_space = action_space
        self.learning_starts = int(learning_starts)
        self.device = device
        self.training = True
        # SAC samples stochastically (`sample`), DDPG/TD3 add exploration noise
        # (`explore`); detect which kw the packaged `act` accepts.
        self._stochastic_kw = 'sample' if 'sample' in agent.act.__code__.co_varnames else 'explore'

    def train(self, mode=True):
        self.training = mode
        for net in (getattr(self.agent, 'actor', None), getattr(self.agent, 'critic', None)):
            if net is not None:
                net.train(mode)

    def act(self, obs, eval_mode=False, step=None):
        # uniform random warmup before learning starts (skip during eval)
        if not eval_mode and step is not None and step < self.learning_starts:
            return np.asarray(self.action_space.sample(), dtype=np.float32)
        kwargs = {self._stochastic_kw: not eval_mode}
        return self.agent.act(obs, **kwargs)

    def store(self, obs, action, reward, next_obs, done, truncated):
        # `done` is terminal-only; truncation is passed via infos so the buffer's
        # timeout handling does not treat a time-limit as a real terminal state.
        infos = [{"TimeLimit.truncated": bool(truncated) and not bool(done)}]
        self.buffer.add(
            np.asarray(obs, dtype=np.float32),
            np.asarray(next_obs, dtype=np.float32),
            np.asarray(action, dtype=np.float32),
            np.asarray([reward], dtype=np.float32),
            np.asarray([float(done)], dtype=np.float32),
            infos,
        )

    def ready(self, step):
        return True

    def update(self, logger, step):
        self.agent.update(self.buffer, logger, step)

    def save(self, model_dir):
        return self.agent.save(model_dir)

    def load(self, model_dir, step):
        self.agent.load(model_dir, step)


# ---------------------------------------------------------------------------
# On-policy: PPO
# ---------------------------------------------------------------------------

class PPORunner:
    """PPO: collect a fixed-length rollout, then a single GAE + clipped update."""

    def __init__(self, agent, buffer, anneal_lr, total_steps, device):
        self.agent = agent
        self.buffer = buffer
        self.anneal_lr = bool(anneal_lr)
        self.total_steps = int(total_steps)
        self.device = device
        self.training = True
        # rollout bookkeeping
        self._value = None
        self._logprob = None
        self._last_episode_start = np.ones(1, dtype=np.float32)
        self._last_obs = None
        self._last_done = False

    def train(self, mode=True):
        self.training = mode
        self.agent.ac.train(mode)

    def _to_t(self, obs):
        return torch.as_tensor(np.asarray(obs, dtype=np.float32), device=self.device).unsqueeze(0)

    def act(self, obs, eval_mode=False, step=None):
        obs_t = self._to_t(obs)
        if eval_mode:
            with torch.no_grad():
                action = self.agent.ac.actor_mean(obs_t)
            return action.cpu().numpy().flatten()
        action, log_prob, value = self.agent.act(obs_t)
        self._logprob = log_prob
        self._value = value
        return action.cpu().numpy().flatten()

    def store(self, obs, action, reward, next_obs, done, truncated):
        self.buffer.add(
            np.asarray(obs, dtype=np.float32),
            np.asarray(action, dtype=np.float32),
            np.asarray([reward], dtype=np.float32),
            self._last_episode_start,
            self._value,
            self._logprob,
        )
        done_or_trunc = bool(done) or bool(truncated)
        self._last_episode_start = np.asarray([float(done_or_trunc)], dtype=np.float32)
        self._last_obs = next_obs
        self._last_done = done_or_trunc

    def ready(self, step):
        return self.buffer.full

    def update(self, logger, step):
        # bootstrap value for the final state, then GAE
        with torch.no_grad():
            last_values = self.agent.get_value(self._to_t(self._last_obs))
        self.buffer.compute_returns_and_advantage(
            last_values, np.asarray([float(self._last_done)], dtype=np.float32)
        )
        if self.anneal_lr and self.total_steps > 0:
            frac = max(1e-8, 1.0 - step / self.total_steps)
            self.agent.anneal_lr(frac)
        self.agent.update(self.buffer, logger, step)
        self.buffer.reset()

    def save(self, model_dir):
        return self.agent.save(model_dir)

    def load(self, model_dir, step):
        self.agent.load(model_dir, step)


# ---------------------------------------------------------------------------
# Pixel + pose + PER: CUPRL
# ---------------------------------------------------------------------------

class CuprlRunner:
    """CURL prioritized SAC over (rgb, depth, pose).

    NOTE: requires a biguagym *pixel* (``-v1``) env whose Dict observation
    exposes ``rgb``/``depth`` image channels and a proprioceptive ``pose``
    vector. The CUPRL ``QFunction`` hardcodes a 9-d pose (position 3 + 6), so the
    env pose channel must be 9-d. This path is wired to the agent/buffer contract
    but should be validated on a real pixel env.
    """

    def __init__(self, agent, buffer, learning_starts, device, pose_key='state'):
        self.agent = agent
        self.buffer = buffer
        self.learning_starts = int(learning_starts)
        self.device = device
        self.pose_key = pose_key
        self.training = True

    def train(self, mode=True):
        self.training = mode
        self.agent.train(mode)

    def _split_obs(self, obs):
        """Map a biguagym pixel Dict observation -> (rgb, depth, pose).

        rgb keeps its native (uint8) dtype to match the PER buffer's image
        storage; depth and pose are floats.
        """
        rgb = np.asarray(obs['rgb'])
        depth = np.asarray(obs['depth'], dtype=np.float32) if 'depth' in obs else rgb.astype(np.float32)
        pose = np.asarray(obs[self.pose_key], dtype=np.float32)
        return rgb, depth, pose

    def act(self, obs, eval_mode=False, step=None):
        rgb, _, pose = self._split_obs(obs)
        return self.agent.act(rgb, pose, sample=not eval_mode)

    def store(self, obs, action, reward, next_obs, done, truncated):
        rgb, depth, pose = self._split_obs(obs)
        next_rgb, _, next_pose = self._split_obs(next_obs)
        self.buffer.add(
            rgb, depth, pose,
            np.asarray(action, dtype=np.float32),
            np.asarray([reward], dtype=np.float32),
            next_rgb, next_pose,
            np.asarray([float(done)], dtype=np.float32),
        )

    def ready(self, step):
        return True

    def update(self, logger, step):
        self.agent.update(self.buffer, logger, step)

    def save(self, model_dir):
        return self.agent.save(model_dir)

    def load(self, model_dir, step):
        self.agent.load(model_dir, step)


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def _build_off_policy(cfg, env, device):
    obs_space = env.observation_space
    action_space = env.action_space
    obs_shape = _box_shape(obs_space)
    action_shape = _box_shape(action_space)
    action_dim = _action_dim(action_space)
    hidden_dim = int(cfg.agent.hidden_dim)

    net_kwargs = dict(observation_shape=obs_shape, action_shape=action_shape, hidden_dim=hidden_dim)
    agent_kwargs = dict(device=str(device))

    if cfg.agent.name == 'sac':
        actor = hydra.utils.instantiate(cfg.agent.actor, **net_kwargs)
        critic = hydra.utils.instantiate(cfg.agent.critic, **net_kwargs)
        agent = hydra.utils.instantiate(
            cfg.agent.algo, actor_cfg=actor, critic_cfg=critic,
            action_shape=action_shape, **agent_kwargs,
        )
    else:  # ddpg / td3 — deterministic actor needs action_bounds
        bounds = _action_bounds(action_space)
        actor = hydra.utils.instantiate(cfg.agent.actor, action_bounds=bounds, **net_kwargs)
        critic = hydra.utils.instantiate(cfg.agent.critic, **net_kwargs)
        agent = hydra.utils.instantiate(
            cfg.agent.algo, actor_cfg=actor, critic_cfg=critic,
            action_bounds=bounds, **agent_kwargs,
        )

    buffer = ReplayBuffer(
        buffer_size=int(cfg.agent.buffer_size),
        observation_space=obs_space,
        action_space=action_space,
        device=device,
        n_envs=1,
    )
    return OffPolicyRunner(agent, buffer, action_space, cfg.agent.learning_starts, device)


def _build_ppo(cfg, env, device, total_steps):
    obs_space = env.observation_space
    action_space = env.action_space
    obs_shape = _box_shape(obs_space)
    action_dim = _action_dim(action_space)
    num_steps = int(cfg.agent.num_steps)

    ac = hydra.utils.instantiate(
        cfg.agent.net, observation_shape=obs_shape, action_dim=action_dim,
        hidden_dim=int(cfg.agent.hidden_dim),
    )
    # n_envs == 1, so batch_size == num_steps
    agent = hydra.utils.instantiate(
        cfg.agent.algo, actor_critic_cfg=ac, batch_size=num_steps, device=str(device),
    )
    buffer = RolloutBuffer(
        buffer_size=num_steps,
        observation_space=obs_space,
        action_space=action_space,
        device=device,
        gae_lambda=float(cfg.agent.gae_lambda),
        gamma=float(cfg.agent.gamma),
        n_envs=1,
    )
    return PPORunner(agent, buffer, cfg.agent.anneal_lr, total_steps, device)


def _build_cuprl(cfg, env, device):
    obs_space = env.observation_space
    action_space = env.action_space
    assert isinstance(obs_space, spaces.Dict) and 'rgb' in obs_space.spaces, \
        "CUPRL requires a pixel Dict obs with an 'rgb' channel (and depth + state)."
    action_shape = _box_shape(action_space)
    action_dim = _action_dim(action_space)
    image_size = int(cfg.agent.image_size)
    hidden_dim = int(cfg.agent.hidden_dim)

    channels = int(obs_space['rgb'].shape[0])
    # pose comes from the env proprioceptive channel ('state', fallback 'pose')
    pose_key = 'state' if 'state' in obs_space.spaces else 'pose'
    pose_dim = int(obs_space[pose_key].shape[0])
    # depth defaults to rgb when the env does not expose a depth channel
    depth_space = obs_space['depth'] if 'depth' in obs_space.spaces else obs_space['rgb']

    # encoder / agent operate on the CROPPED frame (image_size), while the buffer
    # stores the RAW frames and random-crops them at sample time.
    crop_shape = (channels, image_size, image_size)
    enc_actor = hydra.utils.instantiate(cfg.agent.encoder, obs_shape=crop_shape)
    enc_critic = hydra.utils.instantiate(cfg.agent.encoder, obs_shape=crop_shape)
    actor = hydra.utils.instantiate(
        cfg.agent.actor, encoder_cfg=enc_actor, action_shape=action_shape,
        pose_dim=pose_dim, hidden_dim=hidden_dim,
    )
    critic = hydra.utils.instantiate(
        cfg.agent.critic, encoder_cfg=enc_critic, action_shape=action_dim,
        hidden_dim=hidden_dim, pose_dim=pose_dim,
    )
    agent = hydra.utils.instantiate(
        cfg.agent.algo, actor_cfg=actor, critic_cfg=critic,
        obs_shape=crop_shape, action_shape=action_shape, device=str(device),
    )

    # PER buffer keyed rgb/depth/pose (maps the env's 'state' channel to 'pose')
    buffer_obs_space = spaces.Dict({
        'rgb':   obs_space['rgb'],
        'depth': depth_space,
        'pose':  obs_space[pose_key],
    })
    buffer = PrioritizedReplayBuffer(
        buffer_size=int(cfg.agent.buffer_size),
        observation_space=buffer_obs_space,
        action_space=action_space,
        device=device,
        image_size=image_size,
        n_envs=1,
    )
    return CuprlRunner(agent, buffer, cfg.agent.learning_starts, device, pose_key)


def make_runner(cfg, env, device, total_steps):
    """Build the agent + buffer + runner for ``cfg.agent.family``."""
    family = cfg.agent.family
    if family == 'off_policy':
        return _build_off_policy(cfg, env, device)
    if family == 'ppo':
        return _build_ppo(cfg, env, device, total_steps)
    if family == 'cuprl':
        return _build_cuprl(cfg, env, device)
    raise ValueError(f"unknown agent family: {family!r}")
