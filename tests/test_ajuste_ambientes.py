"""Testes da spec ajuste-ambientes, sem simulador.

Os ambientes são criados com ``object.__new__`` (sem abrir o Unreal) e os atributos usados por ``_build_params``,
``_reset``, ``_wrap_state`` e ``_tilt_limit`` são injetados. ``_build_params`` só lê os JSON de configuração.
"""
import inspect

import numpy as np
import pytest

import core.environments as E
import recompensas_util  # noqa: F401  (põe o submódulo no sys.path)

CLASSES = [c for _, c in inspect.getmembers(E, inspect.isclass)
           if c.__module__ == 'core.environments' and '__init__' in c.__dict__ and hasattr(c, '_step')]


# --- R5: seleção da versão -------------------------------------------------------------------------------------
def test_versao_em_todos_os_construtores():
    assert len(CLASSES) == 13
    for c in CLASSES:
        p = inspect.signature(c.__init__).parameters
        assert 'env_version' in p, c.__name__
        assert p['env_version'].default == 'v1', c.__name__


def test_versao_invalida():
    with pytest.raises(ValueError):
        E.HoverEnv(seed=0, agent_type='DjiMatrice', control_abstraction='cmd_motor_speeds',
                   location=[0, 0, 0], rotation=[0, 0, 0], env_version='x')


# --- auxiliar: ambiente sem simulador com _build_params ---------------------------------------------------------
def montar(cls, agent_type, location, version):
    env = object.__new__(cls)
    env._env_version = version
    env._reward_version = 'v1'
    env._agent_type = agent_type
    env._location = cls._spawn_location(agent_type, location, version)
    env._rotation = [0, 0, 0]
    env._batch_size = 1
    env._control_abstraction = 'cmd_motor_speeds'
    env._observation_type = 'DynamicsSensor'
    env._build_params()
    return env


# Ambientes do artigo com alvo, como no register.py: (classe, veículo, location)
CASOS_LIMITES = {
    'DjiMatriceLand': (E.LandEnv, 'DjiMatrice', [100, 100, 5]),
    'DjiMatriceHover': (E.HoverEnv, 'DjiMatrice', [100, 100, 5]),
    'DjiMatriceNav': (E.NavEnv, 'DjiMatrice', [100, 100, 5]),
    'BlueROV2Dock': (E.DockEnv, 'BlueROV2', [100, 100, -0.2]),
    'BlueROV2Nav': (E.NavEnv, 'BlueROV2', [100, 100, -0.2]),
}


def teto_piso(env):
    """(teto, piso) em z. No DockEnv o índice 0 de z é o teto e o 1 é o fundo."""
    if isinstance(env, E.DockEnv):
        return float(env._bounds[0, 2]), float(env._bounds[1, 2])
    return float(env._bounds[1, 2]), float(env._bounds[0, 2])


# --- R1: folga entre o spawn e os limites em z --------------------------------------------------------------------
@pytest.mark.parametrize('nome', sorted(CASOS_LIMITES))
def test_limites_folga_v1(nome):
    cls, veiculo, loc = CASOS_LIMITES[nome]
    env = montar(cls, veiculo, loc, 'v1')
    z = float(env._location[2])
    teto, piso = teto_piso(env)
    assert teto - z >= 1.0 and z - piso >= 1.0, (nome, piso, z, teto)
    if veiculo in E.DOMAIN['underwater']:
        assert teto <= -0.1 and z == E.HoverEnv.UNDERWATER_SPAWN_Z
    if veiculo in E.DOMAIN['aereo']:
        assert piso >= 0.0


# Valores de hoje (código fcf4358), para o v0
LIMITES_V0 = {   # nome: (z do spawn, teto, piso)
    'DjiMatriceLand': (5.0, 5.0, 0.1),
    'DjiMatriceHover': (5.0, 5.0, 0.1),
    'DjiMatriceNav': (5.0, 15.0, 0.0),
    'BlueROV2Dock': (-0.2, -0.2, -10.0),
    'BlueROV2Nav': (-0.2, -0.1, -20.0),
}


@pytest.mark.parametrize('nome', sorted(CASOS_LIMITES))
def test_limites_v0_iguais_aos_de_hoje(nome):
    cls, veiculo, loc = CASOS_LIMITES[nome]
    env = montar(cls, veiculo, loc, 'v0')
    z, teto, piso = LIMITES_V0[nome]
    assert float(env._location[2]) == pytest.approx(z)
    assert teto_piso(env) == pytest.approx((teto, piso))
    assert np.allclose(env._bounds[:, :2], [[90, 90], [110, 110]])
