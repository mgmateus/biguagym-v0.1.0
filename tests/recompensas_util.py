"""Ambientes biguagym sem simulador, para testar recompensa e término (spec recompensas).

O ambiente é criado com ``object.__new__`` (sem abrir o Unreal). Os atributos usados por ``_reward``/``_step`` são
injetados, e o ``_env`` é um simulador falso cujo ``step()`` devolve o próximo vetor de dinâmica da lista do caso.

Layout do vetor de dinâmica (18 posições), como em ``HoverEnv._reward``:
    [0:3] aceleração | [3:6] velocidade | [6:9] posição | [9:12] (não usado) | [12:15] vel. angular | [15:18] roll, pitch, yaw
"""
import os
import sys

import numpy as np

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, 'biguagym'))

from core.environments import DockEnv, HoverEnv, LandEnv, NavEnv, TrajectoryEnv  # noqa: E402

LOC = np.array([100.0, 100.0, 5.0])


def dyn(pos, vel=(0, 0, 0), rpy=(0, 0, 0), ang_vel=(0, 0, 0)):
    d = np.zeros(18)
    d[3:6], d[6:9], d[12:15], d[15:18] = vel, pos, ang_vel, rpy
    return d


class FakeSim:
    """Substitui o BiguaSimEnvironment: devolve a próxima dinâmica a cada step()."""

    def __init__(self):
        self.fila = []

    def step(self, action, action_repeat=1):
        return self.fila.pop(0)

    def draw_point(self, *a, **k):
        pass

    def draw_box(self, *a, **k):
        pass


def make(cls, version=None, bounds=None, target=None, trajectory=None):
    env = object.__new__(cls)
    env._env = FakeSim()
    env._batch_size = 1
    env._action_repeat = 1
    env._episode_steps = 0
    env._last_norm = None
    env._on_target = False
    env._on_target_buf = 0
    env._target_factor = 1
    env._dynamics = None
    if version is not None:
        env._reward_version = version
    env._bounds = np.array(bounds if bounds is not None else [LOC - 10.0, LOC + 10.0], dtype=np.float64)
    if target is not None:
        env._target = np.asarray(target, dtype=np.float64)
        env._target_list = env._target.tolist()
    # Sem o pipeline de observação: o estado já é o vetor de dinâmica.
    env._unwrap_state = lambda s: s
    env._set_dynamics = lambda s: setattr(env, '_dynamics', np.asarray(s, dtype=np.float64))
    if trajectory is not None:
        env.trajectory = np.asarray(trajectory, dtype=np.float32)
        env.n_wp = len(env.trajectory)
        if bounds is None:  # como em TrajectoryEnv.__init__ (margem de 5 m; aéreo: z >= 0)
            env._bounds = np.array([env.trajectory.min(axis=0) - 5.0, env.trajectory.max(axis=0) + 5.0])
            env._bounds[0, 2] = max(float(env._bounds[0, 2]), 0.0)
        env._tangents, env._curvatures = env._precompute_path_geometry()
        env._wp_idx = 0
        env._prev_progress = 0.0
        env._best_wp = 0

        def wrap(state):
            env._wp_idx = env._find_nearest_wp(np.asarray(env._dynamics[6:9]))
            return None
        env._wrap_state = wrap
    else:
        env._wrap_state = lambda s: None
    return env


def rodar(env, estados, passos_iniciais=0):
    """Executa um passo por estado; para no primeiro término. Devolve [(reward, terminated, truncated, info)]."""
    env._env.fila = list(estados)
    env._episode_steps = passos_iniciais
    out = []
    for _ in estados:
        _, r, term, trunc, info = env._step(np.zeros(4, dtype=np.float32))
        out.append((float(r), bool(term), bool(trunc), info))
        if term or trunc:
            break
    return out


# ----------------------------------------------------------------------------------------------------------------
# Casos fixos (usados na referência v0 e nos testes)
# ----------------------------------------------------------------------------------------------------------------
TRAJ = np.stack([LOC[0] + np.arange(300) * 0.2, np.full(300, LOC[1]), np.full(300, LOC[2])], axis=1)
TARGET_HOVER = LOC + np.array([3.0, 0.0, 0.0])
TARGET_LAND = np.array([LOC[0] + 2.0, LOC[1], 0.0])
LOC_DOCK = np.array([100.0, 100.0, -5.0])
B_DOCK = np.array([LOC_DOCK - 10.0, LOC_DOCK + 10.0])
B_DOCK[0, 2] = min(B_DOCK[0, 2] + 10, -0.2)   # topo (como em DockEnv._build_params)
B_DOCK[1, 2] = -10
TARGET_DOCK = np.array([LOC_DOCK[0] + 2.0, LOC_DOCK[1], -8.0])


def _aprox(alvo, ini, n):
    return [dyn(ini + (alvo - ini) * (k + 1) / (n + 1)) for k in range(n)]


def casos():
    """{nome: (classe, kwargs de make, estados, passos_iniciais)}"""
    tilt = np.radians(20)
    c = {}
    for nome, cls in (('hover', HoverEnv), ('nav', NavEnv)):
        kw = dict(target=TARGET_HOVER)
        c[f'{nome}_aproxima'] = (cls, kw, _aprox(TARGET_HOVER, LOC, 5), 0)
        c[f'{nome}_sucesso'] = (cls, kw, _aprox(TARGET_HOVER, LOC, 3) + [dyn(TARGET_HOVER)], 0)
        c[f'{nome}_sucesso_inclinado'] = (cls, kw, [dyn(TARGET_HOVER, rpy=(0.3, 0, 0), ang_vel=(0, 0, 3))], 0)
        c[f'{nome}_tilt'] = (cls, kw, [dyn(LOC), dyn(LOC, rpy=(tilt, 0, 0))], 0)
        c[f'{nome}_fora'] = (cls, kw, [dyn(LOC), dyn(LOC + [11, 0, 0])], 0)
        c[f'{nome}_timeout'] = (cls, kw, [dyn(LOC)], 399)
        c[f'{nome}_parado'] = (cls, kw, [dyn(LOC)] * 50, 0)
    for nome, cls, alvo, b in (('land', LandEnv, TARGET_LAND, None), ('dock', DockEnv, TARGET_DOCK, B_DOCK)):
        ini = LOC if nome == 'land' else LOC_DOCK
        kw = dict(target=alvo, bounds=b)
        c[f'{nome}_aproxima'] = (cls, kw, _aprox(alvo, ini, 5), 0)
        c[f'{nome}_sucesso'] = (cls, kw, _aprox(alvo, ini, 3) + [dyn(alvo)], 0)
        c[f'{nome}_tilt'] = (cls, kw, [dyn(ini), dyn(ini, rpy=(0, tilt, 0))], 0)
        c[f'{nome}_fora'] = (cls, kw, [dyn(ini), dyn(ini + [11, 0, 0])], 0)
        c[f'{nome}_duro'] = (cls, kw, [dyn(alvo + [0, 0, 1.0], vel=(0, 0, -3.0))], 0)
        c[f'{nome}_parado'] = (cls, kw, [dyn(ini)] * 50, 0)
    kw = dict(trajectory=TRAJ)
    c['traj_parado'] = (TrajectoryEnv, kw, [dyn(TRAJ[0])] * 50, 0)
    c['traj_avanca'] = (TrajectoryEnv, kw, [dyn(TRAJ[i]) for i in range(1, 300)], 0)
    c['traj_vai_volta'] = (TrajectoryEnv, kw, [dyn(TRAJ[i]) for i in list(range(1, 11)) + list(range(9, 0, -1)) * 1
                                               + list(range(2, 11))], 0)
    c['traj_tilt'] = (TrajectoryEnv, kw, [dyn(TRAJ[1]), dyn(TRAJ[2], rpy=(tilt, 0, 0))], 0)
    c['traj_fora'] = (TrajectoryEnv, kw, [dyn(TRAJ[1]), dyn(TRAJ[2] + [0, 0, 30])], 0)
    return c


def executar_caso(nome, version=None):
    cls, kw, estados, p0 = casos()[nome]
    env = make(cls, version=version, **kw)
    return rodar(env, estados, p0)
