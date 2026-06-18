
# Agent composition extracted from ./src/sac.py (Soft Actor-Critic).
# This file is the packaging reference for the other agents:
#   - networks parameterized by shapes instead of `env`
#   - a self-contained agent class that owns targets/optimizers and exposes
#     act / update / save / load
#   - training-script concerns (Args/tyro, env setup, logging, buffer creation)
#     are intentionally excluded; the replay buffer is injected into `update`.
#
# Note: the squashed (tanh) policy outputs actions in [-1, 1]; environments are
# expected to be wrapped to that range.

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


def gaussian_logprob(noise, log_std):
    """Compute Gaussian log probability."""
    residual = (-0.5 * noise.pow(2) - log_std).sum(-1, keepdim=True)
    return residual - 0.5 * np.log(2 * np.pi) * noise.size(-1)


def squash(mu, pi, log_pi):
    """Apply squashing function.
    See appendix C from https://arxiv.org/pdf/1812.05905.pdf.
    """
    mu = torch.tanh(mu)
    if pi is not None:
        pi = torch.tanh(pi)
    if log_pi is not None:
        log_pi -= torch.log(F.relu(1 - pi.pow(2)) + 1e-6).sum(-1, keepdim=True)
    return mu, pi, log_pi


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


class Actor(nn.Module):
    """Stochastic Gaussian policy with tanh squashing."""
    def __init__(self,
                 observation_shape: tuple,
                 action_shape: tuple,
                 log_std_min: float,
                 log_std_max: float,
                 hidden_dim: int
                 ):
        super().__init__()
        self.log_std_min = log_std_min
        self.log_std_max = log_std_max

        self.fc1 = nn.Linear(np.array(observation_shape).prod(), hidden_dim)
        self.fc2 = nn.Linear(hidden_dim, hidden_dim)
        self.fc_mean = nn.Linear(hidden_dim, np.prod(action_shape))
        self.fc_logstd = nn.Linear(hidden_dim, np.prod(action_shape))

    def forward(self, obs, compute_pi=True, compute_log_pi=True):
        x = F.relu(self.fc1(obs))
        x = F.relu(self.fc2(x))

        mu = self.fc_mean(x)
        log_std = self.fc_logstd(x)

        # constrain log_std inside [log_std_min, log_std_max]
        log_std = torch.tanh(log_std)
        log_std = self.log_std_min + 0.5 * (
            self.log_std_max - self.log_std_min
        ) * (log_std + 1)

        if compute_pi:
            std = log_std.exp()
            noise = torch.randn_like(mu)
            pi = mu + noise * std
        else:
            pi = None
            noise = None

        if compute_log_pi:
            log_pi = gaussian_logprob(noise, log_std)
        else:
            log_pi = None

        mu, pi, log_pi = squash(mu, pi, log_pi)

        return mu, pi, log_pi, log_std


class Critic(nn.Module):
    """Critic network, employs two q-functions."""
    def __init__(self, observation_shape, action_shape, hidden_dim):
        super().__init__()

        self.Q1 = QFunction(observation_shape, action_shape, hidden_dim)
        self.Q2 = QFunction(observation_shape, action_shape, hidden_dim)

    def forward(self, obs, action):
        q1 = self.Q1(obs, action)
        q2 = self.Q2(obs, action)
        return q1, q2


class SACAgent:
    def __init__(self,
                 actor_cfg: Actor,
                 critic_cfg: Critic,
                 action_shape: tuple,
                 actor_lr: float,
                 critic_lr: float,
                 alpha_lr: float,
                 actor_beta: float,
                 critic_beta: float,
                 alpha_beta: float,
                 critic_tau: float,
                 init_temperature: float,
                 discount: float,
                 actor_update_freq: int,
                 critic_target_update_freq: int,
                 batch_size: int,
                 device: str
                 ):

        self.batch_size = batch_size
        self.discount = discount
        self.critic_tau = critic_tau
        self.actor_update_freq = actor_update_freq
        self.critic_target_update_freq = critic_target_update_freq
        self.device = device

        self.actor = actor_cfg.to(device)
        self.critic = critic_cfg.to(device)

        self.critic_target = copy.deepcopy(self.critic)
        self.critic_target.load_state_dict(self.critic.state_dict())

        self.log_alpha = torch.tensor(np.log(init_temperature)).to(device)
        self.log_alpha.requires_grad = True
        # set target entropy to -|A|
        self.target_entropy = -np.prod(action_shape)

        # optimizers
        self.actor_optimizer = optim.Adam(
            self.actor.parameters(), lr=actor_lr, betas=(actor_beta, 0.999)
        )
        self.critic_optimizer = optim.Adam(
            self.critic.parameters(), lr=critic_lr, betas=(critic_beta, 0.999)
        )
        self.log_alpha_optimizer = optim.Adam(
            [self.log_alpha], lr=alpha_lr, betas=(alpha_beta, 0.999)
        )

    @property
    def alpha(self):
        return self.log_alpha.exp()

    def act(self, obs, sample=False):
        with torch.no_grad():
            obs = torch.FloatTensor(obs).to(self.device)
            obs = obs.unsqueeze(0)
            mu, pi, _, _ = self.actor(obs, compute_log_pi=False)
            action = pi if sample else mu
            return action.cpu().data.numpy().flatten()

    def update_critic(self, obs, action, reward, next_obs, not_done, logger, step):
        with torch.no_grad():
            _, policy_action, log_pi, _ = self.actor(next_obs)
            target_Q1, target_Q2 = self.critic_target(next_obs, policy_action)
            target_V = torch.min(target_Q1, target_Q2) - self.alpha.detach() * log_pi
            target_Q = reward + (not_done * self.discount * target_V)

        # get current Q estimates
        current_Q1, current_Q2 = self.critic(obs, action)
        critic_loss = F.mse_loss(current_Q1, target_Q) + F.mse_loss(current_Q2, target_Q)

        logger.log('train/critic/loss', critic_loss, step)

        # optimize the critic
        self.critic_optimizer.zero_grad()
        critic_loss.backward()
        self.critic_optimizer.step()

    def update_actor_and_alpha(self, obs, logger, step):
        _, pi, log_pi, log_std = self.actor(obs)
        actor_Q1, actor_Q2 = self.critic(obs, pi)

        actor_Q = torch.min(actor_Q1, actor_Q2)
        actor_loss = (self.alpha.detach() * log_pi - actor_Q).mean()

        logger.log('train/actor/loss', actor_loss, step)
        logger.log('train/actor/target_entropy', self.target_entropy, step)
        entropy = 0.5 * log_std.shape[1] * (1.0 + np.log(2 * np.pi)) + log_std.sum(dim=-1)
        logger.log('train/actor/entropy', entropy.mean(), step)

        # optimize the actor
        self.actor_optimizer.zero_grad()
        actor_loss.backward()
        self.actor_optimizer.step()

        # optimize the temperature
        self.log_alpha_optimizer.zero_grad()
        alpha_loss = (self.alpha * (-log_pi - self.target_entropy).detach()).mean()
        logger.log('train/alpha/loss', alpha_loss, step)
        logger.log('train/alpha/value', self.alpha, step)
        alpha_loss.backward()
        self.log_alpha_optimizer.step()

    def update(self, replay_buffer, logger, step):
        data = replay_buffer.sample(self.batch_size)
        obs = data.observations
        action = data.actions
        reward = data.rewards
        next_obs = data.next_observations
        not_done = 1.0 - data.dones

        logger.log('train/batch_reward', reward.mean(), step)

        self.update_critic(obs, action, reward, next_obs, not_done, logger, step)

        if step % self.actor_update_freq == 0:
            self.update_actor_and_alpha(obs, logger, step)

        if step % self.critic_target_update_freq == 0:
            soft_update_params(self.critic.Q1, self.critic_target.Q1, self.critic_tau)
            soft_update_params(self.critic.Q2, self.critic_target.Q2, self.critic_tau)

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
