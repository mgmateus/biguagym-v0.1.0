"""Spec sensores-goto: -v1 (RGB + profundidade, Dranaju) e -v2 (LiDAR no ar, sonar na água, Ricardo), sem simulador."""
import math
import os
import sys

import numpy as np
import pytest

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
sys.path.insert(0, os.path.join(os.path.dirname(AQUI), 'biguagym'))

from core.goto import GotoPixelEnv, GotoRangeEnv, carregar_cenario, carregar_sensores  # noqa: E402
from test_hydrone_goto import SimFalso, dyn, estado  # noqa: E402


def preparar(cls, cenario='pilares'):
    env = object.__new__(cls)
    env._preparar_cenario(cenario)
    env._agent_type, env._control_abstraction = 'Hydrone', 'cmd_vel_yaw'
    env._location, env._rotation = list(env._cena['spawn']), [0, 0, 0]
    env._batch_size, env._action_repeat, env._on_target_buf = 1, 1, 0
    env._env_version, env._observation_type = 'v2', 'DynamicsSensor'
    env.rng = np.random.default_rng(0)
    env.env_cfg, env.obs_cfg = env._build_params()
    env._env = SimFalso(estado(env._cena['spawn']), len(env._geo['centro']))
    env._acao_ant = np.zeros(3, np.float32)
    env._integrar_dinamica, env._acc = False, np.zeros(6)
    return env


# --- R1: -v1 ---------------------------------------------------------------------------------------------------
def test_v1_sensores_embarcados():
    env = preparar(GotoPixelEnv)
    sens = {s.get('sensor_name'): s for s in env.env_cfg['agents'][0]['sensors']}
    for nome in ('RGBCamera', 'DepthCamera'):
        s = sens[nome]
        assert 'socket' not in s and s['location'][0] > 0 and s['rotation'] == [0, 0, 0]
        assert s['configuration']['CaptureWidth'] == s['configuration']['CaptureHeight']
    assert sens['DepthCamera']['configuration']['Debug'] is True
    assert 'CollisionSensor' in {s['sensor_type'] for s in env.env_cfg['agents'][0]['sensors']}


def test_v1_espacos_e_observacao():
    env = preparar(GotoPixelEnv)
    env._render_channel = None
    env._init_spaces()
    env._setup_pixel(3, (100, 100), True, None)
    sp = env.observation_space
    assert sp['rgb'].shape == (9, 100, 100) and sp['rgb'].dtype == np.uint8
    assert sp['depth'].shape == (9, 100, 100) and sp['depth'].high.max() == 255
    assert sp['state'].shape == (9,)
    inicio = estado(env._cena['spawn'])
    inicio['RGBCamera'] = np.full((256, 256, 4), 200, np.uint8)
    inicio['DepthCamera'] = {'depth_map': np.full((256, 256), 2.5, np.float32)}
    env._env = SimFalso(inicio, len(env._geo['centro']))
    obs, _ = env._reset()
    assert obs['rgb'].shape == (9, 100, 100) and np.all(obs['rgb'] == 200)
    assert np.allclose(obs['depth'], 127.5) and obs['state'].shape == (9,)
    assert sp.contains(obs)


# --- R2, R5: LiDAR e sonar --------------------------------------------------------------------------------------
def test_lidar_indices_20_a_cada_13_5_graus():
    idx = GotoRangeEnv.LIDAR_IDX
    ang = [((i * 2.25 + 180) % 360) - 180 for i in idx]
    assert len(idx) == 20 and ang[0] == pytest.approx(-128.25) and ang[-1] == pytest.approx(128.25)
    assert np.allclose(np.diff(ang), 13.5)


def test_lidar_seleciona_e_trata_invalidas():
    env = object.__new__(GotoRangeEnv)
    raw = np.arange(160, dtype=np.float32) / 20.0          # laser i = i/20 m (0 → inválido)
    raw[3] = np.nan
    d = env._lidar20(raw)
    assert d.shape == (20,)
    esperado = np.array([i / 20.0 for i in GotoRangeEnv.LIDAR_IDX], dtype=np.float32)
    esperado[GotoRangeEnv.LIDAR_IDX.index(3)] = 10.0
    assert np.allclose(d, np.minimum(esperado, 10.0))
    assert np.all(env._lidar20(None) == 10.0)
    with pytest.raises(ValueError):
        env._lidar20(np.ones(10))


def test_sonar_distancia_do_maior_retorno_por_feixe():
    env = object.__new__(GotoRangeEnv)
    img = np.zeros((100, 20), np.float32)
    img[10, 0] = 1.0                                      # feixe 0: bin 10 → 0,5 + 10,5·0,195
    img[99, 5] = 0.3
    img[50, 5] = 0.9                                      # feixe 5: o maior é o bin 50
    d = env._sonar20({'raw': img})
    dr = (20.0 - 0.5) / 100
    assert d[0] == pytest.approx(0.5 + 10.5 * dr) and d[5] == pytest.approx(0.5 + 50.5 * dr)
    assert d[1] == 20.0                                   # sem retorno
    assert np.all(env._sonar20(None) == 20.0)


def test_invalida_vira_maximo():
    d = GotoRangeEnv._validas([np.inf, -1.0, 0.0, 3.0, 50.0], 10.0)
    assert np.allclose(d, [10, 10, 10, 3, 10])


# --- R3, R4: troca por meio e observação de 26 -----------------------------------------------------------------
@pytest.mark.parametrize('z,fonte', [(1.0, 'lidar'), (0.0, 'lidar'), (-0.5, 'sonar')])
def test_meio_escolhe_o_sensor(z, fonte):
    env = preparar(GotoRangeEnv)
    env._init_spaces()
    env._dynamics = dyn([103.6, 97.4, z])
    env._target = np.array([100.0, 100.0, 1.0])
    lidar = np.full(160, 4.0, np.float32)
    img = np.zeros((100, 20), np.float32)
    img[0, :] = 1.0
    o = env._wrap_state({'Lidar': lidar, 'Sonar': {'raw': img}})
    assert o.shape == (26,) and env.observation_space.shape == (26,)
    esperado = 4.0 if fonte == 'lidar' else 0.5 + 0.5 * (19.5 / 100)
    assert np.allclose(o[:20], esperado)


def test_v2_observacao_ordem():
    env = preparar(GotoRangeEnv)
    env._dynamics = dyn([98.0, 100.0, 1.0], yaw=math.pi / 2)
    env._target = np.array([100.0, 100.0, 1.0])
    env._acao_ant = np.array([0.1, 0.2, 0.3], np.float32)
    o = env._wrap_state({'Lidar': np.full(160, 4.0, np.float32)})
    assert np.allclose(o[20:23], [0.1, 0.2, 0.3])
    assert o[23] == pytest.approx(2.0) and o[24] == pytest.approx(-math.pi / 2) and o[25] == pytest.approx(0.0)


def test_v2_sensores_configurados_como_o_ricardo():
    s = {x['sensor_name']: x for x in carregar_sensores('v2')}
    lidar, sonar = s['Lidar']['configuration'], s['Sonar']['configuration']
    assert lidar['LaserCount'] == 160 and lidar['LaserMaxDistance'] == 10 and lidar['LaserAngle'] == 0
    assert (sonar['Azimuth'], sonar['Elevation'], sonar['RangeMax'], sonar['AzimuthBins']) == (90, 15, 20, 20)
    assert sonar['MultiPath'] is False


# --- R6: registro -----------------------------------------------------------------------------------------------
def test_registro_ids_v1_v2():
    import gymnasium as gym
    import register  # noqa: F401
    for nome in ('Pilares', 'Dique'):
        assert gym.spec(f"HydroneGoto{nome}-v1").entry_point == "core.goto:GotoPixelEnv"
        assert gym.spec(f"HydroneGoto{nome}-v2").entry_point == "core.goto:GotoRangeEnv"


# --- kwargs que o run.py manda ao CUPRL (piloto de 2026-11-19: TypeError 'pixel_channels') --------------------------------
def test_v1_aceita_kwargs_do_cuprl(monkeypatch):
    from core import goto
    chamadas = {}
    monkeypatch.setattr(goto.GotoEnv, '__init__', lambda self, seed, **kw: chamadas.setdefault('base', kw))
    monkeypatch.setattr(GotoPixelEnv, '_setup_pixel', lambda self, *a: chamadas.setdefault('pixel', a))
    GotoPixelEnv(42, pixel_channels=['rgb', 'depth'], include_state=True, frame_size=[100, 100], cenario='pilares')
    assert chamadas['base'] == {'cenario': 'pilares'}          # não repassa pixel_channels/include_state ao GotoEnv
    assert list(chamadas['pixel'][1]) == [100, 100]


@pytest.mark.parametrize('kw', [{'pixel_channels': ['rgb']}, {'include_state': False}])
def test_v1_recusa_canais_que_nao_entrega(kw):
    with pytest.raises(ValueError):
        GotoPixelEnv(42, **kw)
