
# Agent composition extracted from ./src/td3.py
# (Twin Delayed Deep Deterministic Policy Gradient), following the packaging
# standard defined by ./src/agents/sac.py:
#   - networks parameterized by shapes instead of `env`
#   - a self-contained agent class that owns targets/optimizers and exposes
#     act / update / save / load
#   - training-script concerns (Args/tyro, env setup, logging, buffer creation)
#     are intentionally excluded; the replay buffer is injected into `update`.

import copy
import torch

import numpy as np
import torch.nn as nn
import torch.nn.functional as F
import torch.optim as optim


def soft_update_params(net, target_net, tau):
    for param, target_param in zip(net.parameters(), target_net.parameters()):
        target_param.data.copy_(
            tau * param.data + (1 - tau) * target_param.data
        )


class QFunction(nn.Module):
    def __init__(self, observation_shape, action_shape, hidden_dim):
        super().__init__()
        self.fc1 = nn.Linear(
            np.array(observation_shape).prod() + np.prod(action_shape),
            hidden_dim,
        )
        self.fc2 = nn.Linear(hidden_dim, hidden_dim)
        self.fc3 = nn.Linear(hidden_dim, 1)

    def forward(self, x, a):
        x = torch.cat([x, a], 1)
        x = F.relu(self.fc1(x))
        x = F.relu(self.fc2(x))
        x = self.fc3(x)
        return x


class Critic(nn.Module):
    """Critic network, employs two q-functions (clipped double-Q)."""
    def __init__(self, observation_shape, action_shape, hidden_dim):
        super().__init__()

        self.Q1 = QFunction(observation_shape, action_shape, hidden_dim)
        self.Q2 = QFunction(observation_shape, action_shape, hidden_dim)

    def forward(self, obs, action):
        q1 = self.Q1(obs, action)
        q2 = self.Q2(obs, action)
        return q1, q2


class Actor(nn.Module):
    """Deterministic policy mu(s), tanh-squashed and rescaled to the action range."""
    def __init__(self,
                 observation_shape: tuple,
                 action_shape: tuple,
                 action_bounds: tuple,
                 hidden_dim: int
                 ):
        super().__init__()
        self.fc1 = nn.Linear(np.array(observation_shape).prod(), hidden_dim)
        self.fc2 = nn.Linear(hidden_dim, hidden_dim)
        self.fc_mu = nn.Linear(hidden_dim, np.prod(action_shape))

        # action rescaling (action_bounds = (high, low))
        self.register_buffer(
            "action_scale",
            torch.tensor(
                (action_bounds[0] - action_bounds[1]) / 2.0,
                dtype=torch.float32,
            ),
        )
        self.register_buffer(
            "action_bias",
            torch.tensor(
                (action_bounds[0] + action_bounds[1]) / 2.0,
                dtype=torch.float32,
            ),
        )

    def forward(self, x):
        x = F.relu(self.fc1(x))
        x = F.relu(self.fc2(x))
        x = torch.tanh(self.fc_mu(x))
        return x * self.action_scale + self.action_bias


class TD3Agent:
    def __init__(self,
                 actor_cfg: Actor,
                 critic_cfg: Critic,
                 action_bounds: tuple,
                 actor_lr: float,
                 critic_lr: float,
                 actor_beta: float,
                 critic_beta: float,
                 tau: float,
                 discount: float,
                 policy_noise: float,
                 noise_clip: float,
                 exploration_noise: float,
                 policy_freq: int,
                 batch_size: int,
                 device: str
                 ):

        self.batch_size = batch_size
        self.discount = discount
        self.tau = tau
        self.policy_noise = policy_noise
        self.noise_clip = noise_clip
        self.exploration_noise = exploration_noise
        self.policy_freq = policy_freq
        self.device = device

        # actor + its target
        self.actor = actor_cfg.to(device)
        self.actor_target = copy.deepcopy(self.actor)
        self.actor_target.load_state_dict(self.actor.state_dict())

        # critic (twin Q) + its target
        self.critic = critic_cfg.to(device)
        self.critic_target = copy.deepcopy(self.critic)
        self.critic_target.load_state_dict(self.critic.state_dict())

        # action bounds used to clip exploratory / smoothed actions (action_bounds = (high, low))
        self.action_high = torch.as_tensor(action_bounds[0], dtype=torch.float32, device=device)
        self.action_low = torch.as_tensor(action_bounds[1], dtype=torch.float32, device=device)

        # optimizers
        self.actor_optimizer = optim.Adam(
            self.actor.parameters(), lr=actor_lr, betas=(actor_beta, 0.999)
        )
        self.critic_optimizer = optim.Adam(
            self.critic.parameters(), lr=critic_lr, betas=(critic_beta, 0.999)
        )

    def act(self, obs, explore=False):
        with torch.no_grad():
            obs = torch.FloatTensor(obs).to(self.device)
            obs = obs.unsqueeze(0)
            action = self.actor(obs)
            if explore:
                action += torch.normal(0.0, self.actor.action_scale * self.exploration_noise)
                action = torch.clamp(action, self.action_low, self.action_high)
            return action.cpu().data.numpy().flatten()

    def update_critic(self, obs, action, reward, next_obs, not_done):
        with torch.no_grad():
            # target policy smoothing: add clipped noise to the target action
            noise = (torch.randn_like(action) * self.policy_noise).clamp(
                -self.noise_clip, self.noise_clip
            ) * self.actor_target.action_scale
            next_action = (self.actor_target(next_obs) + noise).clamp(
                self.action_low, self.action_high
            )

            target_Q1, target_Q2 = self.critic_target(next_obs, next_action)
            target_Q = torch.min(target_Q1, target_Q2)
            target_Q = reward + (not_done * self.discount * target_Q)

        # get current Q estimates
        current_Q1, current_Q2 = self.critic(obs, action)
        critic_loss = F.mse_loss(current_Q1, target_Q) + F.mse_loss(current_Q2, target_Q)

        # optimize the critic
        self.critic_optimizer.zero_grad()
        critic_loss.backward()
        self.critic_optimizer.step()

    def update_actor(self, obs):
        # deterministic policy gradient through Q1 only
        actor_loss = -self.critic.Q1(obs, self.actor(obs)).mean()

        # optimize the actor
        self.actor_optimizer.zero_grad()
        actor_loss.backward()
        self.actor_optimizer.step()

    def update(self, replay_buffer, step):
        data = replay_buffer.sample(self.batch_size)
        obs = data.observations
        action = data.actions
        reward = data.rewards
        next_obs = data.next_observations
        not_done = 1.0 - data.dones

        self.update_critic(obs, action, reward, next_obs, not_done)

        # delayed policy update + target sync
        if step % self.policy_freq == 0:
            self.update_actor(obs)
            soft_update_params(self.actor, self.actor_target, self.tau)
            soft_update_params(self.critic, self.critic_target, self.tau)

    def save(self, model_dir):
        actor_path = '%s/actor_last.pt' % (model_dir)
        critic_path = '%s/critic_last.pt' % (model_dir)
        torch.save(
            self.actor.state_dict(), actor_path
        )
        torch.save(
            self.critic.state_dict(), critic_path
        )

        models = {
            'actor': actor_path,
            'critic': critic_path,
        }

        return models

    def load(self, model_dir, step):
        self.actor.load_state_dict(
            torch.load('%s/actor_%s.pt' % (model_dir, step))
        )
        self.critic.load_state_dict(
            torch.load('%s/critic_%s.pt' % (model_dir, step))
        )
