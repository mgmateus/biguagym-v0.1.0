"""T9 (spec recompensas): o env_kwargs do Hydra chega ao gym.make do treino (run.py) e da avaliação (workspace.py)."""
import os
import sys

from omegaconf import OmegaConf

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import run  # noqa: E402
import workspace  # noqa: E402


class Parar(Exception):
    pass


def _cfg(kwargs):
    cfg = OmegaConf.create({'env': 'DjiMatriceNav-v0', 'env_kwargs': kwargs, 'obs_type': None, 'agent': {'family': 'off_policy'}})
    return run._resolve_env(cfg)


def test_treino_recebe_env_kwargs(monkeypatch):
    chamadas = []

    def fake_make(name, **kw):
        chamadas.append((name, kw))
        raise Parar

    monkeypatch.setattr(run.gym, 'make', fake_make)
    cfg = _cfg({'reward_version': 'v0'})
    cfg.runs = 1
    exp = object.__new__(run.Experiment)
    exp.seed = 0
    try:
        exp.train(cfg)
    except Parar:
        pass
    assert chamadas == [('DjiMatriceNav-v0', {'reward_version': 'v0'})]


def test_avaliacao_recebe_env_kwargs(monkeypatch):
    chamadas = []

    class FakeEnv:
        class action_space:
            @staticmethod
            def seed(s):
                pass

        def reset(self, seed=None):
            return None, {}

    def fake_make(name, **kw):
        chamadas.append((name, kw))
        return FakeEnv()

    monkeypatch.setattr(workspace.gym, 'make', fake_make)
    cfg = _cfg({'reward_version': 'v0', 'frame_size': [100, 100]})
    ws = object.__new__(workspace.Workspace)
    ws.eval_env = cfg.env.name
    ws.eval_env_kwargs = OmegaConf.to_container(cfg.env.kwargs, resolve=True)
    ws.seed = 0
    ws._build_eval_env()
    assert chamadas == [('DjiMatriceNav-v0', {'render_mode': 'rgb_array', 'reward_version': 'v0', 'frame_size': [100, 100]})]


def test_sem_env_kwargs():
    cfg = _cfg({})
    assert OmegaConf.to_container(cfg.env.kwargs, resolve=True) == {}
