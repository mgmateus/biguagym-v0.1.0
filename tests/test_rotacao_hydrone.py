"""Spec rotacao-hydrone: o GotoEnv integra as acelerações que o motor do BiguaSim 1.1.0 não aplica (sem simulador)."""
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

ACC = [0.03, 0.0, 1.0, 0.1, 0.2, 3.0]         # o que a dinâmica "calcula": linear (3) + angular (3), mundo
W = np.array([0.01, -0.02, 0.5])                # ω medido pelo DynamicsSensor (mundo, rad/s)
V = np.array([0.2, 0.05, -0.1])                 # v medida pelo DynamicsSensor (centro de massa, mundo)
POS, VEL, RPY = [103.6, 97.4, 2.0], [0.1, -0.2, 0.3], [1.0, -2.0, 30.0]   # RPYDynamicsSensor (ator)


def estado(v=V, w=W):
    din = np.zeros(19)
    din[3:6], din[6:9], din[12:15], din[18] = v, POS, w, 1.0
    rpy = np.zeros(18)
    rpy[3:6], rpy[6:9], rpy[15:18] = VEL, POS, RPY
    return {'DynamicsSensor': din, 'RPYDynamicsSensor': rpy, 'CollisionSensor': np.array([False])}


class ModeloFalso:
    def __init__(self):
        self.chamadas, self.estados, self.acc = 0, [], ACC

    def step(self, state, cmds):
        self.chamadas += 1
        self.estados.append(np.array(state[0], dtype=np.float64))
        return [list(self.acc)]


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
        self.v, self.w = V, W                       # o que o DynamicsSensor mede

    def reset(self):
        return estado()

    def step(self, cmd, action_repeat=1):
        self.repeticoes.append(action_repeat)
        for _ in range(action_repeat):
            st = estado(self.v, self.w)
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
    env._integrar_dinamica = integrar
    env._action_repeat = repeticoes
    env.reset_count = 0
    env._reset()
    return env


# --- R1/R6: o motor recebe aceleração zero; v + v̇·dt e ω + ω̇·dt são impostas ---------------------------------
def test_motor_recebe_aceleracao_zero():
    env = preparar()
    env._step(np.zeros(3, np.float32))
    assert env._env.agente.acoes == [[0.0] * 6]
    assert np.allclose(env._acc, ACC)


def test_impoe_velocidades_integradas():
    env = preparar()
    env._step(np.zeros(3, np.float32))
    (loc, rot, vel, w), = env._env.agente.fisica
    dt = 1.0 / GotoEnv.TICKS_POR_S
    v_esp = (V + np.array(ACC[:3]) * dt) * math.exp(GotoEnv.AMORTECIMENTO_LINEAR_MOTOR * dt)
    w_esp = (W + np.array(ACC[3:]) * dt) * math.exp(GotoEnv.AMORTECIMENTO_ANGULAR_MOTOR * dt)
    assert np.allclose(loc, POS) and np.allclose(rot, RPY)            # posição e atitude ficam as do motor
    assert np.allclose(vel, v_esp)                                    # v do DynamicsSensor, não a do ator
    assert np.allclose(w, np.degrees(w_esp))                          # set_physics_state recebe graus/s


def test_instalar_de_novo_nao_empilha_o_envoltorio():
    env = preparar()
    env._reset()
    env._instalar_integrador()
    modelo = env._env._dynamics_dict['robot']
    assert modelo.step([estado()['DynamicsSensor']], [[0, 0, 0, 0]]) == [[0.0] * 6]
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
    assert env._env.agente.acoes[0] == ACC                            # a aceleração segue inteira para o motor


def test_reset_zera_a_aceleracao():
    env = preparar()
    env._step(np.zeros(3, np.float32))
    env._reset()
    assert np.all(env._acc == 0) and np.all(env._v == 0) and np.all(env._w == 0)


# --- Ajuste: corpo dormindo no motor (mede zero) ----------------------------------------------------------------
ACC_PEQ = [0.03, 0.0, 0.0, 0.0, 0.0, 0.001]     # avanço lento do controlador dos autores, abaixo do limiar do motor


def preparar_parado(repeticoes):
    env = preparar(repeticoes=repeticoes)
    env._env.v, env._env.w = np.zeros(3), np.zeros(3)
    env._env._dynamics_dict['robot']._step_original.__self__.acc = ACC_PEQ
    return env


def test_parado_a_velocidade_acumula():
    env = preparar_parado(5)
    env._step(np.zeros(3, np.float32))
    dt = 1.0 / GotoEnv.TICKS_POR_S
    vx = [f[2][0] for f in env._env.agente.fisica]
    esperado = [k * ACC_PEQ[0] * dt * math.exp(GotoEnv.AMORTECIMENTO_LINEAR_MOTOR * dt) for k in range(1, 6)]
    assert np.allclose(vx, esperado)                                  # cresce a·dt por tick, embora o motor meça 0
    assert np.allclose(env._v, [5 * ACC_PEQ[0] * dt, 0, 0])


def test_parado_a_dinamica_recebe_o_integrado():
    env = preparar_parado(3)
    env._step(np.zeros(3, np.float32))
    estados = env._env._dynamics_dict['robot']._step_original.__self__.estados
    dt = 1.0 / GotoEnv.TICKS_POR_S
    assert [e[3] for e in estados] == pytest.approx([0.0, ACC_PEQ[0] * dt, 2 * ACC_PEQ[0] * dt])
    assert estados[2][14] == pytest.approx(2 * ACC_PEQ[5] * dt)       # ω também
    assert np.all(env._env.v == 0)                                    # o estado do motor não é alterado


def test_acima_do_limiar_vale_a_medida():
    env = preparar_parado(1)
    env._v = np.array([GotoEnv.VEL_DORMINDO + 0.05, 0, 0])            # já devia ter acordado: medida 0 é contato
    env._step(np.zeros(3, np.float32))
    dt = 1.0 / GotoEnv.TICKS_POR_S
    assert env._env.agente.fisica[0][2][0] == pytest.approx(ACC_PEQ[0] * dt * math.exp(dt))


def test_motor_medindo_velocidade_vale_a_medida():
    env = preparar(repeticoes=1)
    env._v = np.array([0.05, 0, 0])                                   # integrado diferente do que o motor mediu (V)
    env._step(np.zeros(3, np.float32))
    assert np.allclose(env._v, V + np.array(ACC[:3]) / GotoEnv.TICKS_POR_S)


def test_batch_maior_que_1_recusa():
    with pytest.raises(ValueError):
        GotoEnv(0, batch_size=2)
