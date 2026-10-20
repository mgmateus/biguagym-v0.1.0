"""Testes da spec colapso-blueboat, sem simulador."""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'tools'))
from diag_referencia import controlador  # noqa: E402

LO, HI = -295.75, 288.08


# --- T2: controlador de referência -----------------------------------------------------------------------------
def test_controlador_alvo_a_frente():
    a = controlador([0, 0, 0], 0.0, [5, 0, 0], LO, HI)
    assert a[0] > 0 and a[1] > 0 and abs(a[0] - a[1]) < 1e-6


def test_controlador_alvo_a_esquerda():
    # guinada positiva (esquerda): motor de boreste (2) mais forte que o de bombordo (1)
    a = controlador([0, 0, 0], 0.0, [3, 3, 0], LO, HI)
    assert a[1] > a[0]


def test_controlador_alvo_atras_gira_sem_avancar():
    a = controlador([0, 0, 0], 0.0, [-5, 0.1, 0], LO, HI)
    assert abs(a[0] + a[1]) < 1e-6 and a[1] > 0


def test_controlador_respeita_limites():
    a = controlador([0, 0, 0], 0.0, [100, 0, 0], LO, HI)
    assert np.all(a >= LO) and np.all(a <= HI)


# --- T4–T7: env_version="v2" ----------------------------------------------------------------------------------
import inspect  # noqa: E402

import pytest  # noqa: E402

import core.environments as E  # noqa: E402
import test_ajuste_ambientes as TA  # noqa: E402  (auxiliares montar/sortear_alvos/dim_obs; os testes de lá não são recoletados aqui)
from recompensas_util import dyn, make  # noqa: E402

BARCO = ('BlueBoat', [100, 100, 0])
PARAMS_BARCO = {'rotor_pos': {'r1': [-0.5475, 0.285, -0.276], 'r2': [-0.5475, -0.285, -0.276]},
                'rotor_speed_min': LO, 'rotor_speed_max': HI}


def test_versao_padrao_v2_e_invalida():
    for c in TA.CLASSES:
        assert inspect.signature(c.__init__).parameters['env_version'].default == 'v2', c.__name__
    with pytest.raises(ValueError):
        E.HoverEnv(seed=0, agent_type='BlueBoat', control_abstraction='cmd_motor_speeds',
                   location=[0, 0, 0], rotation=[0, 0, 0], env_version='v3')


def test_versao_boat_nav_v2_so_no_blueboatnav():
    assert TA.montar(E.NavEnv, *BARCO, 'v2')._boat_nav_v2()
    assert not TA.montar(E.NavEnv, *BARCO, 'v1')._boat_nav_v2()
    assert not TA.montar(E.NavEnv, 'DjiMatrice', [100, 100, 5], 'v2')._boat_nav_v2()
    assert not TA.montar(E.NavEnv, 'BlueROV2', [100, 100, -0.2], 'v2')._boat_nav_v2()
    traj = object.__new__(E.TrajectoryEnv)
    traj._env_version, traj._agent_type = 'v2', 'BlueBoat'
    assert not traj._boat_nav_v2()


@pytest.mark.parametrize('nome', sorted(TA.CASOS_LIMITES))
def test_versao_v2_igual_v1_fora_do_barco(nome):
    cls, veiculo, loc = TA.CASOS_LIMITES[nome]
    v1, v2 = TA.montar(cls, veiculo, loc, 'v1'), TA.montar(cls, veiculo, loc, 'v2')
    assert v1._location == v2._location and np.array_equal(v1._bounds, v2._bounds)
    assert v1._tilt_limit() == v2._tilt_limit()
    assert TA.dim_obs(cls, veiculo, loc, 'v1') == TA.dim_obs(cls, veiculo, loc, 'v2')


@pytest.mark.parametrize('veiculo,loc', [('DjiMatrice', [100, 100, 5]), ('BlueROV2', [100, 100, -0.2])])
def test_versao_v2_alvos_iguais_v1_fora_do_barco(veiculo, loc):
    assert np.array_equal(TA.sortear_alvos(veiculo, loc, 'v1', 200), TA.sortear_alvos(veiculo, loc, 'v2', 200))


def test_versao_v2_barco_limites_e_observacao_iguais_v1():
    v1, v2 = TA.montar(E.NavEnv, *BARCO, 'v1'), TA.montar(E.NavEnv, *BARCO, 'v2')
    assert np.array_equal(v1._bounds, v2._bounds) and v1._tilt_limit() == v2._tilt_limit()
    assert TA.dim_obs(E.NavEnv, *BARCO, 'v2') == 19 + 3
    assert TA.dim_obs(E.TrajectoryEnv, *BARCO, 'v2') == 19


# --- T5: alvo longe da borda ------------------------------------------------------------------------------------
def test_margem_alvo_barco_v2():
    alvos = TA.sortear_alvos(*BARCO, 'v2')
    assert np.all(alvos[:, 2] == 0.0)
    assert np.all((alvos[:, :2] >= 93) & (alvos[:, :2] <= 107))
    assert alvos[:, :2].min() < 93.5 and alvos[:, :2].max() > 106.5     # usa a faixa toda


def test_margem_alvo_barco_v1_continua_na_area_toda():
    alvos = TA.sortear_alvos(*BARCO, 'v1')
    assert alvos[:, :2].min() < 91 and alvos[:, :2].max() > 109


# --- T6: raio de sucesso de superfície --------------------------------------------------------------------------
def sucesso_a(dist, veiculo, version, z=0.0):
    env = make(E.NavEnv, version='v1', bounds=[[90, 90, -20], [110, 110, 15]], target=[100 + dist, 100, z])
    env._env_version, env._agent_type = version, veiculo
    env._dynamics = dyn([100, 100, z])
    E.HoverEnv._reward(env)
    return env._on_target


def test_raio_sucesso_barco_v2():
    assert sucesso_a(0.9, 'BlueBoat', 'v2')
    assert not sucesso_a(1.1, 'BlueBoat', 'v2')
    assert not sucesso_a(0.9, 'BlueBoat', 'v1')
    assert sucesso_a(0.1, 'BlueBoat', 'v1')


@pytest.mark.parametrize('veiculo,z', [('DjiMatrice', 5.0), ('BlueROV2', -1.5)])
def test_raio_sucesso_outros_continua_015(veiculo, z):
    assert not sucesso_a(0.9, veiculo, 'v2', z) and sucesso_a(0.1, veiculo, 'v2', z)


# --- T7: ação normalizada ---------------------------------------------------------------------------------------
class _Robo:
    params = PARAMS_BARCO


class _SimBarco:
    _dynamics_dict = {'robot': _Robo()}


def espaco_acao(veiculo, loc, version, params=PARAMS_BARCO):
    env = TA.montar(E.NavEnv, veiculo, loc, version)
    _, env.obs_cfg = env._build_params()
    env._env = _SimBarco()
    _Robo.params = params
    E.HoverEnv._init_spaces(env)
    _Robo.params = PARAMS_BARCO
    return env


def test_acao_espaco_barco_v2_normalizado():
    sp = espaco_acao(*BARCO, 'v2').action_space
    assert sp.shape == (2,) and np.all(sp.low == -1) and np.all(sp.high == 1)
    sp1 = espaco_acao(*BARCO, 'v1').action_space
    assert np.allclose(sp1.low, LO) and np.allclose(sp1.high, HI)


def test_acao_espaco_drone_v2_igual_v1():
    p = {'rotor_pos': {f'r{i}': [0, 0, 0] for i in range(4)}, 'rotor_speed_min': 0.0, 'rotor_speed_max': 592.4}
    for version in ('v1', 'v2'):
        sp = espaco_acao('DjiMatrice', [100, 100, 5], version, p).action_space
        assert sp.shape == (4,) and np.allclose(sp.low, 0.0) and np.allclose(sp.high, 592.4)


def test_acao_conversao_para_rad_s():
    env = espaco_acao(*BARCO, 'v2')
    assert np.allclose(env._to_motor_speeds([1, -1]), [HI, LO])
    assert np.allclose(env._to_motor_speeds([0, 0]), [0, 0])
    assert np.allclose(env._to_motor_speeds([0.5, -0.5]), [HI / 2, LO / 2])
    assert np.allclose(env._to_motor_speeds([3, -3]), [HI, LO])        # fora do Box: satura


class _SimGravaAcao:
    def __init__(self):
        self.acoes = []

    def step(self, action, action_repeat=1):
        self.acoes.append(action)
        return dyn([100, 100, 0])

    def draw_point(self, *a, **k):
        pass


@pytest.mark.parametrize('version,esperado', [('v2', [HI, LO]), ('v1', [1.0, -1.0])])
def test_acao_step_envia_rad_s_ao_simulador(version, esperado):
    env = make(E.NavEnv, version='v1', bounds=[[90, 90, -1], [110, 110, 0.1]], target=[105, 105, 0])
    env._env_version, env._agent_type = version, 'BlueBoat'
    env._motor_lo, env._motor_hi = LO, HI
    env._env = _SimGravaAcao()
    env._step(np.array([1.0, -1.0], dtype=np.float32))
    assert np.allclose(env._env.acoes[0], esperado)
