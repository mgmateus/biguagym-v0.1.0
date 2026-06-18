
# Agent composition extracted from ./src/ppo.py (Proximal Policy Optimization),
# following the packaging standard defined by ./src/agents/sac.py:
#   - networks parameterized by shapes instead of `env`
#   - a self-contained agent class that owns the optimizer and exposes
#     act / update / save / load
#   - training-script concerns (Args/tyro, env setup, logging, rollout storage)
#     are intentionally excluded.
#
# PPO is on-policy: instead of a replay buffer, `update` consumes a rollout
# buffer that yields minibatches of `RolloutBufferSamples`
# (observations, actions, old_values, old_log_prob, advantages, returns) via
# `rollout_buffer.get(minibatch_size)`. Advantage/return computation (GAE) is a
# responsibility of the buffer, mirroring ./src/ppo.py's training loop.
#
# This implementation targets a continuous action space (diagonal Gaussian
# policy), following ./aux/ppo_continuous_action.py, so it matches biguagym's
# continuous Box action spaces.

import torch

import numpy as np
import torch.nn as nn
import torch.optim as optim
from torch.distributions.normal import Normal


def layer_init(layer, std=np.sqrt(2), bias_const=0.0):
    torch.nn.init.orthogonal_(layer.weight, std)
    torch.nn.init.constant_(layer.bias, bias_const)
    return layer


class ActorCritic(nn.Module):
    """Separate (non-shared) actor and critic MLP heads with a diagonal Gaussian
    policy: a state-dependent mean and a state-independent log-std parameter."""
    def __init__(self,
                 observation_shape: tuple,
                 action_dim: int,
                 hidden_dim: int = 64
                 ):
        super().__init__()
        obs_dim = np.array(observation_shape).prod()

        self.critic = nn.Sequential(
            layer_init(nn.Linear(obs_dim, hidden_dim)),
            nn.Tanh(),
            layer_init(nn.Linear(hidden_dim, hidden_dim)),
            nn.Tanh(),
            layer_init(nn.Linear(hidden_dim, 1), std=1.0),
        )
        self.actor_mean = nn.Sequential(
            layer_init(nn.Linear(obs_dim, hidden_dim)),
            nn.Tanh(),
            layer_init(nn.Linear(hidden_dim, hidden_dim)),
            nn.Tanh(),
            layer_init(nn.Linear(hidden_dim, action_dim), std=0.01),
        )
        self.actor_logstd = nn.Parameter(torch.zeros(1, action_dim))

    def get_value(self, x):
        return self.critic(x)

    def get_action_and_value(self, x, action=None):
        action_mean = self.actor_mean(x)
        action_logstd = self.actor_logstd.expand_as(action_mean)
        action_std = torch.exp(action_logstd)
        probs = Normal(action_mean, action_std)
        if action is None:
            action = probs.sample()
        # sum over the action dimension -> joint log-prob / entropy per sample
        return action, probs.log_prob(action).sum(1), probs.entropy().sum(1), self.critic(x)


class PPOAgent:
    def __init__(self,
                 actor_critic_cfg: ActorCritic,
                 learning_rate: float,
                 batch_size: int,
                 num_minibatches: int,
                 update_epochs: int,
                 clip_coef: float,
                 ent_coef: float,
                 vf_coef: float,
                 max_grad_norm: float,
                 norm_adv: bool,
                 clip_vloss: bool,
                 target_kl: float,
                 device: str
                 ):

        self.update_epochs = update_epochs
        self.clip_coef = clip_coef
        self.ent_coef = ent_coef
        self.vf_coef = vf_coef
        self.max_grad_norm = max_grad_norm
        self.norm_adv = norm_adv
        self.clip_vloss = clip_vloss
        self.target_kl = target_kl
        self.device = device

        self.minibatch_size = int(batch_size // num_minibatches)

        self.ac = actor_critic_cfg.to(device)
        self.optimizer = optim.Adam(self.ac.parameters(), lr=learning_rate, eps=1e-5)

    def act(self, obs):
        """Sample an action during rollout collection.
        Returns (action, log_prob, value), all detached.
        """
        with torch.no_grad():
            action, log_prob, _, value = self.ac.get_action_and_value(obs)
        return action, log_prob, value.flatten()

    def get_value(self, obs):
        """Bootstrap value used by the buffer's GAE computation."""
        with torch.no_grad():
            return self.ac.get_value(obs)

    def anneal_lr(self, frac):
        """Linearly scale the learning rate; `frac` in (0, 1]."""
        self.optimizer.param_groups[0]["lr"] = frac * self.optimizer.defaults["lr"]

    def update(self, rollout_buffer, logger, step):
        clipfracs = []
        approx_kl = None
        pg_loss = v_loss = entropy_loss = None

        for _ in range(self.update_epochs):
            for batch in rollout_buffer.get(self.minibatch_size):
                obs = batch.observations
                # continuous actions are stored as float (N, action_dim)
                actions = batch.actions

                _, newlogprob, entropy, newvalue = self.ac.get_action_and_value(obs, actions)
                logratio = newlogprob - batch.old_log_prob
                ratio = logratio.exp()

                with torch.no_grad():
                    # calculate approx_kl http://joschu.net/blog/kl-approx.html
                    approx_kl = ((ratio - 1) - logratio).mean()
                    clipfracs += [((ratio - 1.0).abs() > self.clip_coef).float().mean().item()]

                advantages = batch.advantages
                if self.norm_adv:
                    advantages = (advantages - advantages.mean()) / (advantages.std() + 1e-8)

                # Policy loss
                pg_loss1 = -advantages * ratio
                pg_loss2 = -advantages * torch.clamp(ratio, 1 - self.clip_coef, 1 + self.clip_coef)
                pg_loss = torch.max(pg_loss1, pg_loss2).mean()

                # Value loss
                newvalue = newvalue.view(-1)
                if self.clip_vloss:
                    v_loss_unclipped = (newvalue - batch.returns) ** 2
                    v_clipped = batch.old_values + torch.clamp(
                        newvalue - batch.old_values,
                        -self.clip_coef,
                        self.clip_coef,
                    )
                    v_loss_clipped = (v_clipped - batch.returns) ** 2
                    v_loss_max = torch.max(v_loss_unclipped, v_loss_clipped)
                    v_loss = 0.5 * v_loss_max.mean()
                else:
                    v_loss = 0.5 * ((newvalue - batch.returns) ** 2).mean()

                entropy_loss = entropy.mean()
                loss = pg_loss - self.ent_coef * entropy_loss + v_loss * self.vf_coef

                self.optimizer.zero_grad()
                loss.backward()
                nn.utils.clip_grad_norm_(self.ac.parameters(), self.max_grad_norm)
                self.optimizer.step()

            if self.target_kl is not None and approx_kl is not None and approx_kl > self.target_kl:
                break

        # log the final-minibatch losses (mapped to the shared actor/critic
        # columns) plus PPO-specific diagnostics
        if pg_loss is not None:
            logger.log('train/actor/loss', pg_loss, step)
            logger.log('train/critic/loss', v_loss, step)
            logger.log('train/entropy', entropy_loss, step)
            logger.log('train/approx_kl', approx_kl, step)
            logger.log('train/clipfrac', float(np.mean(clipfracs)) if clipfracs else 0.0, step)

    def save(self, model_dir):
        agent_path = '%s/agent_last.pt' % (model_dir)
        torch.save(self.ac.state_dict(), agent_path)

        models = {
            'agent': agent_path,
        }

        return models

    def load(self, model_dir, step):
        self.ac.load_state_dict(
            torch.load('%s/agent_%s.pt' % (model_dir, step))
        )
