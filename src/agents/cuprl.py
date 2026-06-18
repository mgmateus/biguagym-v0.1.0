import copy

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F


OUT_DIM = {2: 39, 4: 35, 6: 31}
OUT_DIM_64 = {2: 29, 4: 25, 6: 21}

def center_crop_image(image, output_size):
    h, w = image.shape[1:]
    new_h, new_w = output_size, output_size

    top = (h - new_h)//2
    left = (w - new_w)//2

    image = image[:, top:top + new_h, left:left + new_w]
    return image

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


def soft_update_params(net, target_net, tau):
    for param, target_param in zip(net.parameters(), target_net.parameters()):
        target_param.data.copy_(
            tau * param.data + (1 - tau) * target_param.data
        )

def tie_weights(src, trg):
    assert type(src) == type(trg)
    trg.weight = src.weight
    trg.bias = src.bias



def weight_init(m):
    """Custom weight init for Conv2D and Linear layers."""
    if isinstance(m, nn.Linear):
        nn.init.orthogonal_(m.weight.data)
        m.bias.data.fill_(0.0)
    elif isinstance(m, nn.Conv2d) or isinstance(m, nn.ConvTranspose2d):
        # delta-orthogonal init from https://arxiv.org/pdf/1806.05393.pdf
        assert m.weight.size(2) == m.weight.size(3)
        m.weight.data.fill_(0.0)
        m.bias.data.fill_(0.0)
        mid = m.weight.size(2) // 2
        gain = nn.init.calculate_gain('relu')
        nn.init.orthogonal_(m.weight.data[:, :, mid, mid], gain)

class PixelEncoder(nn.Module):
    """Convolutional encoder of pixels observations."""
    def __init__(self, obs_shape, feature_dim, num_layers, num_filters, output_logits):
        super().__init__()

        assert len(obs_shape) == 3
        self.obs_shape = obs_shape
        self.feature_dim = feature_dim
        self.num_layers = num_layers

        self.convs = nn.ModuleList(
            [nn.Conv2d(obs_shape[0], num_filters, 3, stride=2)]
        )
        for i in range(num_layers - 1):
            self.convs.append(nn.Conv2d(num_filters, num_filters, 3, stride=1))

        out_dim = OUT_DIM_64[num_layers] if obs_shape[-1] == 64 else OUT_DIM[num_layers]
        self.fc = nn.Linear(num_filters * out_dim * out_dim, self.feature_dim)
        self.ln = nn.LayerNorm(self.feature_dim)

        self.outputs = dict()
        self.output_logits = output_logits

    def reparameterize(self, mu, logstd):
        std = torch.exp(logstd)
        eps = torch.randn_like(std)
        return mu + eps * std

    def forward_conv(self, obs):
        obs = obs / 255.
        conv = torch.relu(self.convs[0](obs))

        for i in range(1, self.num_layers):
            conv = torch.relu(self.convs[i](conv))
        h = conv.view(conv.size(0), -1)
        return h

    def forward(self, obs, detach=False):
        h = self.forward_conv(obs)

        if detach:
            h = h.detach()

        h_fc = self.fc(h)

        h_norm = self.ln(h_fc)

        if self.output_logits:
            out = h_norm
        else:
            out = torch.tanh(h_norm)

        return out

    def copy_conv_weights_from(self, source):
        """Tie convolutional layers"""
        # only tie conv layers
        for i in range(self.num_layers):
            tie_weights(src=source.convs[i], trg=self.convs[i])


class Actor(nn.Module):
    """MLP actor network fusing pixel features with a proprioceptive pose."""
    def __init__(self, encoder_cfg, action_shape, pose_dim, hidden_dim, log_std_min, log_std_max):
        super().__init__()

        self.encoder = encoder_cfg

        self.log_std_min = log_std_min
        self.log_std_max = log_std_max

        self.trunk = nn.Sequential(
            nn.Linear(self.encoder.feature_dim + pose_dim, hidden_dim), nn.ReLU(),
            nn.Linear(hidden_dim, hidden_dim), nn.ReLU(),
            nn.Linear(hidden_dim, 2 * action_shape[0])
        )

        self.outputs = dict()
        self.apply(weight_init)

    def forward(
        self, obs, pose, compute_pi=True, compute_log_pi=True, detach_encoder=False
    ):
        obs = self.encoder(obs, detach=detach_encoder)
        h = torch.cat([obs, pose], dim=-1)

        mu, log_std = self.trunk(h).chunk(2, dim=-1)

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

        if compute_log_pi:
            log_pi = gaussian_logprob(noise, log_std)
        else:
            log_pi = None

        mu, pi, log_pi = squash(mu, pi, log_pi)

        return mu, pi, log_pi, log_std


class QFunction(nn.Module):
    """MLP for q-function."""
    def __init__(self, obs_dim, action_dim, hidden_dim):
        super(QFunction, self).__init__()

        self.trunk = nn.Sequential(
            nn.Linear(obs_dim + 3+6 + action_dim, hidden_dim), nn.ReLU(),
            nn.Linear(hidden_dim, hidden_dim), nn.ReLU(),
            nn.Linear(hidden_dim, 1)
        )

    def forward(self, obs, pose, action):
        assert obs.size(0) == action.size(0)

        obs_pose = torch.cat([obs, pose], dim=1)
        obs_action = torch.cat([obs_pose, action], dim=1)
        return self.trunk(obs_action)


class Critic(nn.Module):
    """Critic network, employes two q-functions."""
    def __init__(
        self, encoder_cfg, action_shape, hidden_dim):
        super(Critic, self).__init__()


        self.encoder = encoder_cfg

        self.Q1 = QFunction(
            self.encoder.feature_dim, action_shape, hidden_dim
        )
        self.Q2 = QFunction(
            self.encoder.feature_dim, action_shape, hidden_dim
        )

        self.outputs = dict()
        self.apply(weight_init)

    def forward(self, obs, pose, action, detach_encoder=False):
        # detach_encoder allows to stop gradient propogation to encoder
        obs = self.encoder(obs, detach=detach_encoder)
        q1 = self.Q1(obs, pose, action)
        q2 = self.Q2(obs, pose, action)
        return q1, q2


class CURL(nn.Module):
    """
    CURL
    """
    def __init__(self, z_dim, batch_size, critic, critic_target):
        super(CURL, self).__init__()
        self.batch_size = batch_size

        self.encoder = critic.encoder

        self.encoder_target = critic_target.encoder

        self.W = nn.Parameter(torch.rand(z_dim, z_dim))

    def encode(self, x, detach=False, ema=False):
        """
        Encoder: z_t = e(x_t)
        :param x: x_t, x y coordinates
        :return: z_t, value in r2
        """
        if ema:
            with torch.no_grad():
                z_out = self.encoder_target(x)
        else:
            z_out = self.encoder(x)

        if detach:
            z_out = z_out.detach()
        return z_out

    def compute_logits(self, z_a, z_pos):
        """
        Uses logits trick for CURL:
        - compute (B,B) matrix z_a (W z_pos.T)
        - positives are all diagonal elements
        - negatives are all other elements
        - to compute loss use multiclass cross entropy with identity matrix for labels
        """
        Wz = torch.matmul(self.W, z_pos.T)  # (z_dim,B)
        logits = torch.matmul(z_a, Wz)  # (B,B)
        logits = logits - torch.max(logits, 1)[0][:, None]
        return logits


class CurlPriorSacAgent(object):
    """CURL representation learning with prioritized SAC over RGB-D + pose.

    Standardized to the project's agent interface (act / update / save / load).
    The replay buffer is injected into ``update`` and is expected to be a
    ``PrioritizedReplayBuffer`` yielding ``PrioritizedReplayBufferSamples``.
    """
    def __init__(
        self,
        actor_cfg,
        critic_cfg,
        obs_shape,
        action_shape,
        device,
        discount,
        init_temperature,
        alpha_lr,
        alpha_beta,
        actor_lr,
        actor_beta,
        actor_update_freq,
        critic_lr,
        critic_beta,
        critic_tau,
        critic_target_update_freq,
        encoder_feature_dim,
        encoder_lr,
        encoder_tau,
        cl_update_freq,
        detach_encoder,
        curl_latent_dim,
        batch_size,
    ):
        self.device = device
        self.discount = discount
        self.critic_tau = critic_tau
        self.encoder_tau = encoder_tau
        self.actor_update_freq = actor_update_freq
        self.critic_target_update_freq = critic_target_update_freq
        self.cl_update_freq = cl_update_freq
        self.image_size = obs_shape[-1]
        self.curl_latent_dim = curl_latent_dim
        self.detach_encoder = detach_encoder
        self.batch_size = batch_size

        self.actor = actor_cfg.to(device)

        self.critic = critic_cfg.to(device)

        self.critic_target = copy.deepcopy(self.critic)
        self.critic_target.load_state_dict(self.critic.state_dict())

        # tie encoders between actor and critic, and CURL and critic
        self.actor.encoder.copy_conv_weights_from(self.critic.encoder)

        self.log_alpha = torch.tensor(np.log(init_temperature)).to(device)
        self.log_alpha.requires_grad = True
        # set target entropy to -|A|
        self.target_entropy = -np.prod(action_shape)

        # optimizers
        self.actor_optimizer = torch.optim.Adam(
            self.actor.parameters(), lr=actor_lr, betas=(actor_beta, 0.999)
        )

        self.critic_optimizer = torch.optim.Adam(
            self.critic.parameters(), lr=critic_lr, betas=(critic_beta, 0.999)
        )

        self.log_alpha_optimizer = torch.optim.Adam(
            [self.log_alpha], lr=alpha_lr, betas=(alpha_beta, 0.999)
        )

        # create CURL encoder
        self.CURL = CURL(
            encoder_feature_dim, self.batch_size, self.critic, self.critic_target
        ).to(self.device)

        # optimizer for critic encoder for reconstruction loss
        self.encoder_optimizer = torch.optim.Adam(
            self.critic.encoder.parameters(), lr=encoder_lr
        )

        self.cpc_optimizer = torch.optim.Adam(
            self.CURL.parameters(), lr=encoder_lr
        )
        self.cross_entropy_loss = nn.CrossEntropyLoss()

        self.train()
        self.critic_target.train()

    def train(self, training=True):
        self.training = training
        self.actor.train(training)
        self.critic.train(training)
        self.CURL.train(training)

    @property
    def alpha(self):
        return self.log_alpha.exp()

    def act(self, obs, pose, sample=False):
        if obs.shape[-1] != self.image_size:
            obs = center_crop_image(obs, self.image_size)

        with torch.no_grad():
            obs = torch.FloatTensor(obs).to(self.device).unsqueeze(0)
            pose = torch.FloatTensor(pose).to(self.device).unsqueeze(0)
            mu, pi, _, _ = self.actor(
                obs, pose, compute_pi=sample, compute_log_pi=False
            )
            action = pi if sample else mu
            return action.cpu().data.numpy().flatten()

    def update_critic(self, obs, pose, action, reward, next_obs, next_pose, not_done, weights):
        with torch.no_grad():
            _, policy_action, log_pi, _ = self.actor(next_obs, next_pose)
            target_Q1, target_Q2 = self.critic_target(next_obs, next_pose, policy_action)
            target_V = torch.min(target_Q1, target_Q2) - self.alpha.detach() * log_pi
            target_Q = reward + (not_done * self.discount * target_V)

        # get current Q estimates
        current_Q1, current_Q2 = self.critic(
            obs, pose, action, detach_encoder=self.detach_encoder)

        td_error1 = target_Q.detach() - current_Q1
        td_error2 = target_Q.detach() - current_Q2
        critic1_loss = 0.5 * (td_error1.pow(2) * weights).mean()
        critic2_loss = 0.5 * (td_error2.pow(2) * weights).mean()
        # per-sample priorities for PER
        prios = abs(((td_error1 + td_error2) / 2.0 + 1e-5).squeeze())

        critic_loss = critic1_loss + critic2_loss

        # Optimize the critic
        self.critic_optimizer.zero_grad()
        critic_loss.backward()
        self.critic_optimizer.step()

        return prios

    def update_actor_and_alpha(self, obs, pose):
        # detach encoder, so we don't update it with the actor loss
        _, pi, log_pi, _ = self.actor(obs, pose, detach_encoder=True)
        actor_Q1, actor_Q2 = self.critic(obs, pose, pi, detach_encoder=True)

        actor_Q = torch.min(actor_Q1, actor_Q2)
        actor_loss = (self.alpha.detach() * log_pi - actor_Q).mean()

        # optimize the actor
        self.actor_optimizer.zero_grad()
        actor_loss.backward()
        self.actor_optimizer.step()

        # optimize the temperature
        self.log_alpha_optimizer.zero_grad()
        alpha_loss = (self.alpha * (-log_pi - self.target_entropy).detach()).mean()
        alpha_loss.backward()
        self.log_alpha_optimizer.step()

    def update_cpc(self, obs_anchor, obs_pos):
        z_a = self.CURL.encode(obs_anchor)
        z_pos = self.CURL.encode(obs_pos, ema=True)

        logits = self.CURL.compute_logits(z_a, z_pos)
        labels = torch.arange(logits.shape[0]).long().to(self.device)
        loss = self.cross_entropy_loss(logits, labels)

        self.encoder_optimizer.zero_grad()
        self.cpc_optimizer.zero_grad()
        loss.backward()

        self.encoder_optimizer.step()
        self.cpc_optimizer.step()

    def update(self, replay_buffer, step):
        data = replay_buffer.sample(self.batch_size)
        obs = data.observations
        depth = data.depths
        pose = data.poses
        action = data.actions
        reward = data.rewards
        next_obs = data.next_observations
        next_pose = data.next_poses
        not_done = 1.0 - data.dones
        weights = data.weights
        indices = data.indices

        prios = self.update_critic(
            obs, pose, action, reward, next_obs, next_pose, not_done, weights
        )
        replay_buffer.update_priorities(indices, prios.data.cpu().numpy())

        if step % self.actor_update_freq == 0:
            self.update_actor_and_alpha(obs, pose)

        if step % self.critic_target_update_freq == 0:
            soft_update_params(
                self.critic.Q1, self.critic_target.Q1, self.critic_tau
            )
            soft_update_params(
                self.critic.Q2, self.critic_target.Q2, self.critic_tau
            )
            soft_update_params(
                self.critic.encoder, self.critic_target.encoder,
                self.encoder_tau
            )

        # CURL contrastive update: RGB crop anchor vs. depth crop positive
        if step % self.cl_update_freq == 0:
            self.update_cpc(obs, depth)

    def save(self, model_dir):
        actor_path = '%s/actor_last.pt' % (model_dir)
        critic_path = '%s/critic_last.pt' % (model_dir)
        curl_path = '%s/curl_last.pt' % (model_dir)
        torch.save(
            self.actor.state_dict(), actor_path
        )
        torch.save(
            self.critic.state_dict(), critic_path
        )
        torch.save(
            self.CURL.state_dict(), curl_path
        )

        models = {
            'actor': actor_path,
            'critic': critic_path,
            'curl': curl_path
        }

        return models

    def load(self, model_dir, step):
        self.actor.load_state_dict(
            torch.load('%s/actor_%s.pt' % (model_dir, step))
        )
        self.critic.load_state_dict(
            torch.load('%s/critic_%s.pt' % (model_dir, step))
        )
