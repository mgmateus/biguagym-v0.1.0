import gc
import time

import torch
import numpy as np

from src.agents.runner import make_runner


class Workspace:
    """Training infrastructure for the packaged ``src/agents`` agents.

    Builds the requested agent (SAC / DDPG / TD3 / PPO / CUPRL) from the Hydra
    config and wraps it in a family runner that owns its replay/rollout buffer,
    then drives the shared train / evaluate loop. The runner exposes a uniform
    ``act / store / ready / update`` interface so this loop stays agent-agnostic.
    """

    def __init__(self, cfg, env, eval_env, action_shape, logger, device):
        self.obs_type = cfg.env.obs_params.get('anchor', cfg.env.obs_params.type)
        self.init_steps = cfg.init_steps
        self.num_eval_episodes = cfg.num_eval_episodes
        self.num_train_steps = cfg.num_train_steps
        self.eval_freq = cfg.eval_freq
        self.logger = logger
        self.env = env
        self.eval_env = eval_env
        self.device = device
        self.action_shape = action_shape

        self.episode_reward = -np.inf
        self.max_episode_reward = -np.inf
        self.episode_step = 0
        self.episode = 0

        self.agent = self._build_agent(cfg)

    # ------------------------------------------------------------------
    # Agent construction
    # ------------------------------------------------------------------

    def _build_agent(self, cfg):
        """Build the packaged agent + its buffer, wrapped in a family runner."""
        return make_runner(cfg, self.env, self.device, total_steps=self.num_train_steps)

    # ------------------------------------------------------------------
    # Agent hooks (delegated to the runner)
    # ------------------------------------------------------------------

    def _select_action(self, obs, step, eval_mode):
        return self.agent.act(obs, eval_mode=eval_mode, step=step)

    def _store_transition(self, obs, action, reward, next_obs, done, truncated):
        self.agent.store(obs, action, reward, next_obs, done, truncated)

    def _cleanup(self):
        pass

    # ------------------------------------------------------------------
    # Shared utilities
    # ------------------------------------------------------------------

    def _reset_env(self, env):
        obs, _ = env.reset()
        return obs

    def _step_env(self, env, action) -> tuple:
        next_obs, reward, done, truncated, _ = env.step(action)
        done = done.cpu().item() if isinstance(done, torch.Tensor) else bool(np.asarray(done).reshape(-1)[0])
        truncated = truncated.cpu().item() if isinstance(truncated, torch.Tensor) else bool(np.asarray(truncated).reshape(-1)[0])
        reward_scalar = reward.cpu().item() if isinstance(reward, torch.Tensor) else float(np.asarray(reward).reshape(-1)[0])
        return next_obs, reward_scalar, done, truncated

    # ------------------------------------------------------------------
    # Evaluate
    # ------------------------------------------------------------------

    def evaluate(self, max_average, step, record_path: str = None) -> tuple:
        from utils import eval_mode as _eval_mode

        all_ep_rewards = []
        start = time.time()
        
        steps = 0
        for episode_num in range(self.num_eval_episodes):
            self.eval_env.unwrapped.start_recording(f"{self.logger.eval_dir}/eval_{episode_num}.mp4")

            obs = self._reset_env(self.eval_env)
            episode_reward = 0
            episode_over = False

            while not episode_over:
                with torch.no_grad(), _eval_mode(self.agent):
                    with self.logger.eval_profiler.record("action_select"):
                        action = self._select_action(obs, step, eval_mode=True)

                with self.logger.eval_profiler.record("env_step"):
                    obs, reward_scalar, episode_over, truncated = self._step_env(self.eval_env, action)

                self.eval_env.unwrapped.render()
                episode_over = episode_over or truncated
                episode_reward += reward_scalar
                steps += 1

            steps = 0

            self.eval_env.unwrapped.stop_recording()
            all_ep_rewards.append(episode_reward)

        mean_ep_reward = float(np.mean(all_ep_rewards))
        best_id = int(np.argmax(all_ep_rewards))
        best_ep_reward = all_ep_rewards[best_id]

        self.logger.best_record = record_path or f"{self.logger.eval_dir}/eval_{best_id}.mp4"
        self.logger.log('eval/episode', self.episode, step)
        self.logger.log('eval/mean_ep_reward', mean_ep_reward, step)
        self.logger.log('eval/best_ep_reward', best_ep_reward, step)
        self.logger.log('eval/duration', time.time() - start, step)

        if mean_ep_reward >= max_average:
            return True, mean_ep_reward
        return False, max_average

    # ------------------------------------------------------------------
    # Train
    # ------------------------------------------------------------------

    def train(self) -> None:
        self.logger.system_monitor.start()

        start = time.time()
        eval_duration = 0

        new_best, max_average = False, -np.inf
        done, truncated = True, True

        for step in range(self.num_train_steps):

            if step % self.eval_freq == 0:
                start_eval = time.time()
                new_best, max_average = self.evaluate(max_average, step)
                self.logger.save(self.agent, new_best, step)
                self.logger.flush_curve()
                eval_duration = time.time() - start_eval

            if done or truncated:
                if self.max_episode_reward < self.episode_reward:
                    self.max_episode_reward = self.episode_reward

                duration = (time.time() - start) - eval_duration
                self.logger.log('train/episode_reward', self.episode_reward, step)
                self.logger.log('train/max_reward', self.max_episode_reward, step)
                self.logger.log('train/episode', self.episode, step)
                self.logger.log('train/duration', duration, step)
                self.logger.record_curve(self.episode, step, self.episode_reward, duration)
                self.logger.dump(step)

                obs = self._reset_env(self.env)
                done, truncated = False, False
                self.episode_reward = 0
                self.episode_step = 0
                self.episode += 1
                start = time.time()
                eval_duration = 0

            # Action selection (the RL wrapper handles its own exploration and
            # caches the transition for _store_transition -> observe).
            with torch.no_grad():
                with self.logger.train_profiler.record("action_select"):
                    action = self._select_action(obs, step, eval_mode=False)

            if step >= self.init_steps and self.agent.ready(step):
                if not self.logger._flops_profiled:
                    # First eligible update: profile FLOPs (this IS the update).
                    self.logger.profile_agent_flops(self.agent.update, self.logger, step)
                else:
                    with self.logger.train_profiler.record("agent_update"):
                        self.agent.update(self.logger, step)

            with self.logger.train_profiler.record("env_step"):
                next_obs, reward_scalar, done, truncated = self._step_env(self.env, action)
            self.logger.log('train/reward', reward_scalar, step)
            self.episode_reward += reward_scalar

            with self.logger.train_profiler.record("store_transition"):
                self._store_transition(obs, action, reward_scalar, next_obs, done, truncated)

            obs = next_obs
            self.episode_step += 1

        # --- final eval and flush ---
        duration = time.time() - start
        new_best, max_average = self.evaluate(max_average, step)
        self.logger.save(self.agent, new_best, step)

        self.logger.log('train/episode_reward', self.episode_reward, step)
        self.logger.log('train/max_reward', self.max_episode_reward, step)
        self.logger.log('train/episode', self.episode, step)
        self.logger.log('train/duration', duration, step)
        self.logger.dump(step)

        self.logger.record_curve(self.episode, step, self.episode_reward, duration)
        self.logger.flush_curve()

        self.env.close()
        self.logger.save_profilers()

        self._cleanup()
        del self.agent
        del self.env
        del self.eval_env

        gc.collect()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
