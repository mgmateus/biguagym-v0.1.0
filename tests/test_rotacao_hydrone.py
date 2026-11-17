"""Spec rotacao-hydrone: o GotoEnv integra a aceleração angular que o motor do BiguaSim 1.1.0 não aplica (sem simulador)."""
import math
import os
import sys

import numpy as np
import pytest

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
sys.path.insert(0, os.path.join(os.path.dirname(AQUI), 'biguagym'))

from core.goto import GotoEnv  # noqa: E402
from test_hydrone_goto import montar  # noqa: E402

ACC = [0.0, 0.0, 1.0, 0.1, 0.2, 3.0]          # o que a dinâmica "calcula": linear (3) + angular (3), mundo
W = np.array([0.01, -0.02, 0.5])                # ω medido pelo DynamicsSensor (mundo, rad/s)
POS, VEL, RPY = [103.6, 97.4, 2.0], [0.1, -0.2, 0.3], [1.0, -2.0, 30.0]


def estado():
    din = np.zeros(19)
    din[6:9], din[12:15], din[18] = POS, W, 1.0
    rpy = np.zeros(18)
    rpy[3:6], rpy[6:9], rpy[15:18] = VEL, POS, RPY
    return {'DynamicsSensor': din, 'RPYDynamicsSensor': rpy, 'CollisionSensor': np.array([False])}


class ModeloFalso:
    def __init__(self):
        self.chamadas = 0

    def step(self, state, cmds):
        self.chamadas += 1
        return [list(ACC)]


class AgenteFalso:
    def __init__(self):
        self.acoes, self.fisica = [], []

    def act(self, acao):
        self.acoes.append(list(acao))

    def set_physics_state(self, location, rotation, velocity, angular_velocity):
        # cópia, como o np.copyto do BiguaSim (o _set_dynamics converte o RPY do estado no lugar depois)
        self.fisica.append([np.array(v, dtype=np.float64) for v in (location, rotation, velocity, angular_velocity)])


class SimDinamica:
    """Imita o BiguaSim.step: a cada tick, lê o estado, chama a dinâmica e manda a aceleração ao agente."""

    def __init__(self):
        self._dynamics_dict = {'robot': ModeloFalso()}
        self.agente = AgenteFalso()
        self.agents = {'robot-id0': self.agente}
        self.repeticoes, self.props = [], []

    def reset(self):
        return estado()

    def step(self, cmd, action_repeat=1):
        self.repeticoes.append(action_repeat)
        for _ in range(action_repeat):
            st = estado()
            acao = self._dynamics_dict['robot'].step([st['DynamicsSensor']], [cmd])
            self.agente.act(acao[0])
        return st

    def spawn_prop(self, prop_type, **kw):
        self.props.append(prop_type)

    def draw_point(self, *a, **k):
        pass


def preparar(integrar=True, repeticoes=1):
    env = montar()
    env._env = SimDinamica()
    env._integrar_rotacao = integrar
    env._action_repeat = repeticoes
    env.reset_count = 0
    env._reset()
    return env


# --- R1: só a aceleração linear vai ao motor; ω + ω̇·dt é imposta ------------------------------------------------
def test_motor_recebe_so_a_aceleracao_linear():
    env = preparar()
    env._step(np.zeros(3, np.float32))
    assert env._env.agente.acoes == [[0.0, 0.0, 1.0, 0.0, 0.0, 0.0]]
    assert np.allclose(env._w_dot, ACC[3:])


def test_impoe_velocidade_angular_integrada():
    env = preparar()
    env._step(np.zeros(3, np.float32))
    (loc, rot, vel, w), = env._env.agente.fisica
    dt = 1.0 / GotoEnv.TICKS_POR_S
    esperado = (W + np.array(ACC[3:]) * dt) * math.exp(GotoEnv.AMORTECIMENTO_ANGULAR_MOTOR * dt)
    assert np.allclose(loc, POS) and np.allclose(rot, RPY) and np.allclose(vel, VEL)
    assert np.allclose(w, np.degrees(esperado))                      # set_physics_state recebe graus/s


def test_instalar_de_novo_nao_empilha_o_envoltorio():
    env = preparar()
    env._reset()
    env._instalar_integrador()
    modelo = env._env._dynamics_dict['robot']
    assert modelo.step([None], [[0, 0, 0, 0]]) == [[0.0, 0.0, 1.0, 0.0, 0.0, 0.0]]
    assert modelo._step_original.__self__.chamadas == 1               # um só passo da dinâmica original


# --- R2: action_repeat tick a tick --------------------------------------------------------------------------
def test_action_repeat_um_tick_por_vez():
    env = preparar(repeticoes=3)
    env._step(np.zeros(3, np.float32))
    assert env._env.repeticoes == [1, 1, 1]
    assert len(env._env.agente.fisica) == 3


# --- R3: desligada, volta ao comportamento anterior ----------------------------------------------------------
def test_integracao_desligada():
    env = preparar(integrar=False, repeticoes=3)
    env._step(np.zeros(3, np.float32))
    assert env._env.repeticoes == [3]
    assert env._env.agente.fisica == []
    assert env._env.agente.acoes[0] == ACC                            # a aceleração angular segue para o motor


def test_reset_zera_omega_ponto():
    env = preparar()
    env._step(np.zeros(3, np.float32))
    env._reset()
    assert np.all(env._w_dot == 0)


def test_batch_maior_que_1_recusa():
    with pytest.raises(ValueError):
        GotoEnv(0, batch_size=2)
