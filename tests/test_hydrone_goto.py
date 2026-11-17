"""Spec hydrone-goto-dique: Goto do Hydrone (ação, cenário, alvos, colisão, recompensa do Dranaju) sem simulador."""
import math
import os
import sys

import numpy as np
import pytest

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(AQUI), 'biguagym'))

import core.goto as G  # noqa: E402
from core.goto import GotoEnv, carregar_cenario, recompensa_dranaju  # noqa: E402


def dyn(pos, yaw=0.0):
    d = np.zeros(18)
    d[6:9], d[17] = pos, yaw
    return d


def estado(pos, yaw=0.0, contato=False):
    # o RPYDynamicsSensor chega em graus (o _set_dynamics converte)
    d = dyn(pos, math.degrees(yaw))
    return {'RPYDynamicsSensor': d, 'CollisionSensor': np.array([contato])}


class SimFalso:
    def __init__(self, inicio):
        self.inicio = inicio
        self.fila, self.acoes, self.props, self.resets = [], [], [], 0

    def reset(self):
        self.resets += 1
        return self.inicio

    def step(self, action, action_repeat=1):
        self.acoes.append(action)
        return self.fila.pop(0)

    def spawn_prop(self, prop_type, **kw):
        self.props.append((self.resets, prop_type, kw))

    def draw_point(self, *a, **k):
        pass


def montar(cenario='pilares', inicio=None, seed=0):
    env = object.__new__(GotoEnv)
    env._cena = carregar_cenario(cenario)
    env._cenario = cenario
    env._action_repeat = 1
    env._batch_size = 1
    env._on_target_buf = 0
    env.rng = np.random.default_rng(seed)
    (x0, y0), (x1, y1) = env._cena['area']
    z0, z1 = env._cena['z_limites']
    agua = env._cena['nivel_agua']
    env._bounds = np.array([[x0, y0, agua + z0], [x1, y1, agua + z1]], dtype=np.float64)
    env._env = SimFalso(inicio if inicio is not None else estado(env._cena['spawn']))
    env._init_spaces()
    return env


# --- R3: cenário ----------------------------------------------------------------------------------------------
@pytest.mark.parametrize('nome', ['pilares', 'dique'])
def test_cenario_lido(nome):
    c = carregar_cenario(nome)
    for chave in ('nivel_agua', 'origem', 'area', 'z_limites', 'spawn', 'pilares', 'exclusao',
                  'alvo_z_ar', 'alvo_z_agua', 'p_alvo_agua', 'folga_alvo', 'dist_min_alvo'):
        assert chave in c
    assert len(carregar_cenario('pilares')['pilares']) == 4


def test_cenario_desconhecido():
    with pytest.raises(ValueError):
        carregar_cenario('nao-existe')


# --- R1, R2: ação → cmd_vel_yaw --------------------------------------------------------------------------------
def test_comando_conversao_dranaju():
    env = montar()
    env._dynamics, env._yaw_ref = dyn([0, 0, 1]), 0.0
    assert np.allclose(env._comando([-1, 0, 0]), [0.01, 0, 0, 0], atol=1e-6)        # mínimo: 0 + 0,01
    env._yaw_ref = 0.0
    assert np.allclose(env._comando([1, 0, 1]), [0.31, 0, 0.3, 0], atol=1e-6)       # máximo
    env._yaw_ref = 0.0
    assert np.allclose(env._comando([1, 0, -1])[2], -0.3)


def test_comando_velocidade_no_referencial_do_mundo():
    env = montar()
    env._dynamics, env._yaw_ref = dyn([0, 0, 1], math.pi / 2), math.pi / 2       # nariz para +y
    c = env._comando([1, 0, 0])
    assert np.allclose(c[:2], [0, 0.31], atol=1e-6)


def test_comando_integra_guinada():
    env = montar()
    env._dynamics, env._yaw_ref = dyn([0, 0, 1]), 0.0
    for _ in range(10):                              # 10 ticks a +0,3 rad/s → 0,15 rad de referência
        c = env._comando([0, 1, 0])
    assert env._yaw_ref == pytest.approx(0.15)
    assert c[3] == pytest.approx(math.degrees(0.15), abs=1e-4)
    env._yaw_ref = 0.0
    for _ in range(10):
        c = env._comando([0, -1, 0])
    assert c[3] == pytest.approx(-math.degrees(0.15), abs=1e-4)


def test_comando_desvio_limitado_a_45():
    env = montar()
    env._dynamics, env._yaw_ref = dyn([0, 0, 1], 0.0), math.radians(170)
    c = env._comando([0, 0, 0])
    assert c[3] == pytest.approx(45.0)
    assert env._yaw_ref == pytest.approx(math.radians(45))


def test_comando_desvio_atravessa_pi():
    env = montar()
    env._dynamics, env._yaw_ref = dyn([0, 0, 1], math.radians(179)), math.radians(-179)
    assert env._comando([0, 0, 0])[3] == pytest.approx(2.0, abs=1e-4)


# --- R4: pilares a cada reset ----------------------------------------------------------------------------------
def test_pilares_recriados_a_cada_reset():
    env = montar()
    env._reset()
    env._reset()
    props = env._env.props
    assert len(props) == 8 and {p[0] for p in props} == {1, 2}
    _, tipo, kw = props[0]
    p0 = env._cena['pilares'][0]
    assert tipo == 'cylinder'
    assert kw['scale'] == [2 * p0['raio'], 2 * p0['raio'], p0['altura']]
    assert kw['location'][2] == pytest.approx(env._cena['nivel_agua'] + p0['base_z'] + p0['altura'] / 2)


# --- R5: alvos --------------------------------------------------------------------------------------------------
def test_alvos_validos():
    env = montar()
    c = env._cena
    (x0, y0), (x1, y1) = c['area']
    agua, folga = c['nivel_agua'], c['folga_alvo']
    pos = np.array(c['spawn'], dtype=float)
    n_agua = 0
    for _ in range(1000):
        a = env._sortear_alvo(pos)
        assert x0 + folga <= a[0] <= x1 - folga and y0 + folga <= a[1] <= y1 - folga
        z = a[2] - agua
        assert (c['alvo_z_agua'][0] <= z <= c['alvo_z_agua'][1]) or (c['alvo_z_ar'][0] <= z <= c['alvo_z_ar'][1])
        n_agua += z < 0
        assert env._dist_pilar(a) >= folga
        assert np.linalg.norm(a - pos) >= c['dist_min_alvo']
    assert 350 < n_agua < 650                         # p_alvo_agua = 0,5


def test_alvos_fora_da_exclusao():
    env = montar()
    env._cena = dict(env._cena, exclusao=[{'min': [95, 95, -5], 'max': [100, 105, 5]}])
    for _ in range(300):
        a = env._sortear_alvo()
        assert env._dist_exclusao(a) >= env._cena['folga_alvo'] and a[0] > 100


# --- R6: recompensa ---------------------------------------------------------------------------------------------
@pytest.mark.parametrize('d_ant,d,z,col,ch,esperado', [
    (5.0, 4.0, 2.0, False, False, 0.1),               # 0,1·Δd
    (4.0, 5.0, 2.0, False, False, -0.1),
    (5.0, 4.0, -0.1, False, False, 0.11),             # faixa da superfície: +0,01 no sentido de r
    (4.0, 5.0, -0.1, False, False, -0.11),
    (5.0, 5.0, -0.1, False, False, 0.0),              # r = 0 fica 0
    (5.0, 4.0, -0.8, False, False, -0.1),             # abaixo de -0,75
    (5.0, 4.0, 2.0, True, False, -1.0),               # colisão
    (5.0, 0.3, 2.0, False, True, 1.0),                # chegada
    (5.0, 0.3, 2.0, True, True, 1.0),                 # as duas: chegada por último, como no Dranaju
])
def test_recompensa_dranaju(d_ant, d, z, col, ch, esperado):
    assert recompensa_dranaju(d_ant, d, z, col, ch) == pytest.approx(esperado)


# --- R7: colisão ------------------------------------------------------------------------------------------------
@pytest.mark.parametrize('pos,contato,motivo', [
    ([103.6, 97.4, 2.0], False, None),
    ([103.6, 97.4, 2.0], True, "contato"),
    ([95.5, 100.0, 2.0], False, "parede"),            # 0,5 m da borda
    ([100.0, 100.0, 5.0], False, "altura"),           # acima de 4,8
    ([100.0, 100.0, -1.2], False, "altura"),
    ([99.1, 98.0, 1.0], False, "pilar"),              # 1,1 m do eixo, 0,6 m da superfície
    ([99.2, 98.0, 1.0], False, None),                 # 0,7 m da superfície
    ([99.1, 98.0, 5.5], False, "altura"),             # acima do pilar: altura, não pilar
])
def test_colisao(pos, contato, motivo):
    env = montar()
    env._dynamics = dyn(pos)
    assert env._colisao({'CollisionSensor': np.array([contato])}) == motivo


def test_spawn_colidindo_recusado():
    env = montar()
    env._cena = dict(env._cena, spawn=[98.5, 98.0, 1.0])
    with pytest.raises(ValueError):
        env._validar_spawn()
    for nome in ('pilares', 'dique'):
        montar(nome)._validar_spawn()


def test_colisao_caixa_de_exclusao():
    env = montar()
    env._cena = dict(env._cena, exclusao=[{'min': [100, 100, -5], 'max': [101, 101, 5]}])
    env._dynamics = dyn([101.5, 100.5, 1.0])
    assert env._colisao({}) == "obstaculo"


# --- R6–R8: passo completo --------------------------------------------------------------------------------------
def test_passo_colisao_termina_com_menos_um():
    env = montar()
    env._reset()
    env._env.fila.append(estado([95.3, 100, 2.0]))
    _, r, term, trunc, info = env._step(np.zeros(3, np.float32))
    assert r == -1.0 and term and not trunc and info['termination_reason'] == "parede"


def test_passo_chegada_troca_alvo_sem_terminar():
    env = montar()
    env._reset()
    alvo = env._target.copy()
    env._env.fila.append(estado(alvo + [0.1, 0, 0]))
    _, r, term, _, info = env._step(np.zeros(3, np.float32))
    assert r == 1.0 and not term and info['reached_goals'] == 1
    assert not np.allclose(env._target, alvo)
    assert env._last_norm == pytest.approx(env._distancia())


def test_trunca_em_1000():
    env = montar()
    env._reset()
    env._episode_steps = 999
    env._env.fila.append(estado(env._cena['spawn']))
    _, _, term, trunc, info = env._step(np.zeros(3, np.float32))
    assert trunc and not term and info['termination_reason'] == "timeout"


def test_passo_envia_cmd_vel_yaw():
    env = montar()
    env._reset()
    env._env.fila.append(estado(env._cena['spawn']))
    env._step(np.array([1, 0, 0], np.float32))
    assert np.allclose(env._env.acoes[0], [0.31, 0, 0, 0], atol=1e-6)


# --- R9, R10: observação e registro -----------------------------------------------------------------------------
def test_obs_v0_pose9_mais_acoes():
    env = montar()
    obs, _ = env._reset()
    assert obs.shape == (12,) and env.observation_space.shape == (12,)
    env._target = np.array([100.0, 100.0, 1.0])
    env._dynamics = dyn([98.0, 100.0, 1.0], yaw=math.pi / 2)
    env._acao_ant = np.array([0.5, -0.5, 0.0], np.float32)
    o = env._wrap_state({})
    assert o[0] == pytest.approx(-math.pi / 2)        # alvo em +x, nariz em +y → heading -90°
    assert o[1] == pytest.approx(0.0) and o[2] == pytest.approx(2.0)
    assert np.allclose(o[3:6], [-2, 0, 1]) and np.allclose(o[6:9], [0, 0, 1])
    assert np.allclose(o[9:], [0.5, -0.5, 0.0])
    assert env.action_space.shape == (3,) and np.all(env.action_space.low == -1)


def test_registro_ids():
    import gymnasium as gym
    import register  # noqa: F401
    for nome, cena in (('Pilares', 'pilares'), ('Dique', 'dique')):
        spec = gym.spec(f"HydroneGoto{nome}-v0")
        assert spec.entry_point == "core.goto:GotoEnv"
        assert spec.kwargs['control_abstraction'] == 'cmd_vel_yaw' and spec.kwargs['cenario'] == cena


def test_modulo_sem_simulador():
    assert G.GotoEnv.MAX_PASSOS == 1000 and G.GotoEnv.DIST_COLISAO == 0.625
