"""Spec hydrone-goto-dique: Goto do Hydrone (ação, cenário, alvos, colisão, recompensa do Dranaju) sem simulador."""
import math
import os
import sys

import numpy as np
import pytest

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(AQUI), 'biguagym'))

import core.goto as G  # noqa: E402
from core.goto import (GotoEnv, carregar_agente_obstaculo, carregar_cenario, dist_capsulas,  # noqa: E402
                       geometria_obstaculos, recompensa_dranaju)


def dyn(pos, yaw=0.0):
    d = np.zeros(18)
    d[6:9], d[17] = pos, yaw
    return d


def estado(pos, yaw=0.0, contato=False):
    # o RPYDynamicsSensor chega em graus (o _set_dynamics converte)
    d = dyn(pos, math.degrees(yaw))
    return {'RPYDynamicsSensor': d, 'CollisionSensor': np.array([contato])}


class Clone:
    """Torpedo dos obstáculos: guarda cada set_physics_state (o último antes do tick é o que vale no BiguaSim)."""

    def __init__(self):
        self.locais, self.comandos = [], []

    def set_physics_state(self, location, rotation, velocity, angular_velocity):
        self.locais.append(np.array(location, dtype=np.float64))
        self.comandos.append('fisica')

    def teleport(self, location=None, rotation=None):
        self.locais.append(np.array(location, dtype=np.float64))
        self.comandos.append('teleporte')


class SimFalso:
    """Devolve o estado do robô da fila (ou o inicial); com obstáculos, o estado vem por agente e cada torpedo é medido
    onde foi posto no tick (``medir(j, local, tick)`` muda isso)."""

    def __init__(self, inicio, n_obst=0, medir=None):
        self.inicio = inicio
        self.fila, self.acoes, self.resets = [], [], 0
        self.clones = [Clone() for _ in range(n_obst)]
        self.agents = {f'obstaculo-id{j}': c for j, c in enumerate(self.clones)}
        self.medir = medir
        self.locais_por_tick = []

    def reset(self):
        self.resets += 1
        return self.inicio

    def step(self, action, action_repeat=1):
        self.acoes.append(action)
        robo = self.fila.pop(0) if self.fila else self.inicio
        if not self.clones:
            return robo
        assert isinstance(action, dict) and len(action['obstaculo']) == len(self.clones)
        locais = [c.locais[-1] if c.locais else np.zeros(3) for c in self.clones]
        self.locais_por_tick.append(np.array(locais))
        tick = len(self.locais_por_tick) - 1
        medidos = [self.medir(j, l, tick) if self.medir else l for j, l in enumerate(locais)]
        # formato do _get_full_state do BiguaSim: por agente, cada sensor numa lista (um elemento por clone)
        return {'robot': {k: [v] for k, v in robo.items()},
                'obstaculo': {'DynamicsSensor': [dyn(m) for m in medidos]}, 't': 0.0}

    def draw_point(self, *a, **k):
        pass


def montar(cenario='pilares', inicio=None, seed=0, obstaculos=True, medir=None):
    env = object.__new__(GotoEnv)
    env._preparar_cenario(cenario)
    if not obstaculos:
        env._cena = dict(env._cena, obstaculos=[])
        env._geo = geometria_obstaculos(env._cena, env._agente_obst)
    env._action_repeat = 1
    env._batch_size = 1
    env._on_target_buf = 0
    env._integrar_dinamica = False                   # o SimFalso não tem dinâmica (integração: test_rotacao_hydrone.py)
    env._acc = np.zeros(6)
    env.rng = np.random.default_rng(seed)
    (x0, y0), (x1, y1) = env._cena['area']
    z0, z1 = env._cena['z_limites']
    agua = env._cena['nivel_agua']
    env._bounds = np.array([[x0, y0, agua + z0], [x1, y1, agua + z1]], dtype=np.float64)
    env._env = SimFalso(inicio if inicio is not None else estado(env._cena['spawn']), len(env._geo['centro']), medir)
    env._init_spaces()
    return env


# --- R3: cenário ----------------------------------------------------------------------------------------------
@pytest.mark.parametrize('nome', ['pilares', 'dique'])
def test_cenario_lido(nome):
    c = carregar_cenario(nome)
    for chave in ('nivel_agua', 'origem', 'area', 'z_limites', 'spawn', 'obstaculos', 'exclusao',
                  'alvo_z_ar', 'alvo_z_agua', 'p_alvo_agua', 'folga_alvo', 'dist_min_alvo'):
        assert chave in c
    assert c['provisorio'] is False
    assert sum(o['tipo'] == 'pilar' for o in carregar_cenario('pilares')['obstaculos']) == 4


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


# --- R4: obstáculos feitos de torpedos ------------------------------------------------------------------------
def test_geometria_pilares_2x2_tres_niveis():
    geo = geometria_obstaculos(carregar_cenario('pilares'), carregar_agente_obstaculo())
    assert len(geo['centro']) == 48 and set(geo['tipo']) == {'pilar'}
    sel = geo['obstaculo'] == 0                                   # pilar em (129,4; −152)
    c = geo['centro'][sel]
    assert np.allclose(sorted(set(np.round(c[:, 0], 3))), [129.24, 129.56])        # ±(0,19 + 0,13)/2: aletas livres
    assert np.allclose(sorted(set(np.round(c[:, 1], 3))), [-152.16, -151.84])
    assert np.allclose(sorted(set(np.round(c[:, 2], 3))), [-0.15, 2.1, 4.35])      # −1,2 + 1,05; + 2,25 por nível
    assert np.allclose(geo['rotacao'][sel], [0, 90, 0]) and np.allclose(geo['eixo'][sel], [0, 0, 1])
    assert np.allclose(geo['imposto'], geo['centro'])                               # origem_eixo = 0


def test_geometria_vigas_e_total_do_dique():
    geo = geometria_obstaculos(carregar_cenario('dique'), carregar_agente_obstaculo())
    assert len(geo['centro']) == 66                                                 # 5 pilares × 12 + 2 + 2 + 1 + 1
    norte = geo['centro'][geo['obstaculo'] == 5]                                    # viga de x 127,9 a 132,25
    assert np.allclose(norte, [[128.95, -146.3, -0.05], [131.2, -146.3, -0.05]])
    assert np.allclose(geo['rotacao'][geo['obstaculo'] == 5], [0, 0, 0])
    travessa = geo['obstaculo'] == 7                                                # de y −151 a −149, z 2,5
    assert np.allclose(geo['centro'][travessa], [[129.4, -150.0, 2.5]])
    assert np.allclose(geo['rotacao'][travessa], [0, 0, 90]) and np.allclose(geo['eixo'][travessa], [0, 1, 0])


def test_origem_do_ator_deslocada_ao_longo_do_eixo():
    agente = dict(carregar_agente_obstaculo(), origem_eixo=0.861)
    geo = geometria_obstaculos(carregar_cenario('dique'), agente)
    assert np.allclose(geo['imposto'] - geo['centro'], 0.861 * geo['eixo'])


def test_viga_inclinada_e_tipo_desconhecido_recusados():
    agente = carregar_agente_obstaculo()
    with pytest.raises(ValueError):
        geometria_obstaculos({'nivel_agua': 0, 'obstaculos': [{'tipo': 'viga', 'de': [0, 0, 0], 'ate': [3, 0, 1]}]}, agente)
    with pytest.raises(ValueError):
        geometria_obstaculos({'nivel_agua': 0, 'obstaculos': [{'tipo': 'caixa'}]}, agente)


def test_dist_capsulas():
    geo = geometria_obstaculos({'nivel_agua': 0, 'obstaculos': [{'tipo': 'viga', 'de': [0, 0, 0], 'ate': [2.1, 0, 0]}]},
                               carregar_agente_obstaculo())
    assert dist_capsulas([1.05, 1.0, 0.0], geo) == (pytest.approx(1.0 - 0.095), 0)   # de lado
    assert dist_capsulas([3.1, 0.0, 0.0], geo)[0] == pytest.approx(1.0)              # pela ponta: 3,1 − 2,1
    assert dist_capsulas([0, 0, 0], {'centro': np.zeros((0, 3))}) == (math.inf, -1)


@pytest.mark.parametrize('nome', ['pilares', 'dique'])
def test_obstaculos_nao_se_tocam_e_ficam_na_area(nome):
    cena, agente = carregar_cenario(nome), carregar_agente_obstaculo()
    geo = geometria_obstaculos(cena, agente)
    (x0, y0), (x1, y1) = cena['area']
    for j in range(len(geo['centro'])):
        outros = {k: (v[np.arange(len(geo['centro'])) != j] if isinstance(v, np.ndarray) and v.ndim and
                      len(v) == len(geo['centro']) else v) for k, v in geo.items()}
        for t in np.linspace(-1.0, 1.0, 9):
            p = geo['centro'][j] + t * agente['comprimento'] / 2 * geo['eixo'][j]
            assert dist_capsulas(p, outros)[0] > agente['diametro'] / 2, (j, t)   # o eixo de um fora dos outros
            assert x0 < p[0] < x1 and y0 < p[1] < y1


@pytest.mark.parametrize('nome', ['pilares', 'dique'])
def test_pilares_cobrem_a_faixa_de_voo(nome):
    cena = carregar_cenario(nome)
    env = montar(nome)
    lo, hi = cena['z_limites']
    for ob in cena['obstaculos']:
        if ob['tipo'] != 'pilar':
            continue
        for z in np.linspace(lo, hi, 60):
            # junto à face do feixe (0,3 m do eixo): colide em qualquer altura da faixa de voo
            assert env._dist_obstaculo([ob['xy'][0] + 0.3, ob['xy'][1], z])[0] < env.DIST_COLISAO


def test_agente_obstaculo_no_cenario_do_simulador():
    env = object.__new__(GotoEnv)
    env._preparar_cenario('pilares')
    env._agent_type, env._control_abstraction = 'Hydrone', 'cmd_vel_yaw'
    env._location, env._rotation, env._batch_size = [133.88, -152.6, 2.0], [0, 0, 0], 1
    env._env_version, env._observation_type = 'v2', 'DynamicsSensor'
    env_params, _ = env._build_params()
    assert env_params['agents'][0]['agent_name'] == 'robot'
    ob = env_params['agents'][-1]
    assert ob['agent_name'] == 'obstaculo' and ob['agent_type'] == 'TorpedoAUV'
    assert ob['control_abstraction'] == 'accel' and ob['dynamics']['batch_size'] == 48
    assert ob['location'] == [133.88, -152.6, GotoEnv.ALTURA_ESPERA]
    (sensor,) = ob['sensors']                                     # só o que a dinâmica exige, no centro de massa
    assert sensor['sensor_type'] == 'DynamicsSensor' and sensor['configuration']['UseCOM'] is True


def test_reset_desce_um_nivel_por_tick_e_termina_no_lugar():
    env = montar()
    env._reset()
    ticks = env._env.locais_por_tick
    geo = env._geo
    agua = env._cena['nivel_agua']
    espera = ticks[0]
    assert np.allclose(espera[:, :2], geo['imposto'][:, :2])                       # acima do lugar
    assert np.allclose(sorted(set(np.round(espera[:, 2], 3))),
                       [agua + GotoEnv.ALTURA_ESPERA + GotoEnv.PASSO_ESPERA * k for k in range(3)])
    nivel0 = np.isclose(geo['centro'][:, 2], agua - 0.15)
    assert np.allclose(ticks[1][nivel0], geo['imposto'][nivel0])                    # 1º tick: só o nível de baixo
    assert np.allclose(ticks[1][~nivel0], espera[~nivel0])
    assert np.allclose(ticks[3], geo['imposto']) and len(ticks) == 5                # 3 níveis + espera + medição
    assert env._env.resets == 1


def test_posiciona_com_teleporte_e_segura_com_fisica():
    env = montar()
    env._reset()
    cmds = env._env.clones[0].comandos
    assert cmds == ['teleporte'] * 4 + ['fisica']                 # espera + 3 níveis; o último zera a velocidade
    env._env.fila.append(estado(env._cena['spawn']))
    env._step(np.zeros(3, np.float32))
    assert cmds[-1] == 'fisica'


def test_reset_repete_quem_nao_chegou():
    deslocado = 7

    def medir(j, local, tick):                    # o torpedo 7 fica preso na 1ª tentativa; os outros têm 0,861 m em z
        if j == deslocado and tick < 5:
            return local + [0.0, 6.9, 0.0]
        return local + [0.0, 0.0, 0.861]
    env = montar(medir=medir)
    import warnings as w
    with w.catch_warnings():
        w.simplefilter('error')
        env._reset()
    ticks = env._env.locais_por_tick
    assert len(ticks) == 8                     # 1ª tentativa: espera + 3 níveis + medição; 2ª: só ele (1 nível)
    assert ticks[5][deslocado][2] > 25 and np.allclose(ticks[5][0], env._geo['imposto'][0])   # só ele sobe de novo
    assert np.allclose(env._obst_ponto, env._geo['imposto'])


def test_reset_avisa_se_nao_chegar():
    env = montar(medir=lambda j, local, tick: local + ([0.0, 6.9, 0.0] if j == 3 else [0.0, 0.0, 0.0]))
    with pytest.warns(UserWarning, match='fora do lugar'):
        env._reset()


def test_deslocamento_por_orientacao_nao_e_fora_do_lugar():
    # vigas deitadas e pilares em pé: o deslocamento da origem vai ao longo do eixo de cada um
    env = montar('dique', medir=None)
    env._env.medir = lambda j, local, tick: local + 0.861 * env._geo['eixo'][j]
    env._reset()
    n_niveis = len(np.unique(np.round(env._geo['centro'][:, 2], 3)))                 # 6: 3 dos pilares + 3 das vigas
    assert len(env._env.locais_por_tick) == n_niveis + 2 and not len(env._fora_do_lugar())


def test_estado_por_agente_tira_o_robo_da_lista():
    env = montar()
    prof = {'depth_map': np.ones((4, 4))}
    st = env._unwrap_state({'robot': {'DepthCamera': [prof], 'RPYDynamicsSensor': [dyn([1, 2, 3])]},
                            'obstaculo': {'DynamicsSensor': [dyn([0, 0, 0])] * 48}, 't': 0.0})
    assert st['DepthCamera'] is prof and np.allclose(st['RPYDynamicsSensor'][6:9], [1, 2, 3])
    assert len(env._estado_obst['DynamicsSensor']) == 48


def test_sobe_limite_de_arquivos(monkeypatch):
    chamadas = []
    monkeypatch.setattr(G.resource, 'getrlimit', lambda r: (1024, 1048576))
    monkeypatch.setattr(G.resource, 'setrlimit', lambda r, lim: chamadas.append(lim))
    GotoEnv._subir_limite_arquivos()
    assert chamadas == [(GotoEnv.LIMITE_ARQUIVOS, 1048576)]
    monkeypatch.setattr(G.resource, 'getrlimit', lambda r: (1024, 4096))
    GotoEnv._subir_limite_arquivos()
    assert chamadas[-1] == (4096, 4096)                           # nunca acima do rígido
    monkeypatch.setattr(G.resource, 'getrlimit', lambda r: (100000, 1048576))
    GotoEnv._subir_limite_arquivos()
    assert len(chamadas) == 2                                     # já basta: não mexe


def test_dinamica_dos_obstaculos_devolve_zero():
    env = montar()

    class Modelo:
        def step(self, estados, cmds):
            raise AssertionError("a dinâmica original não deve rodar")
    env._env._dynamics_dict = {'obstaculo': Modelo()}
    env._dinamica_parada()
    assert env._env._dynamics_dict['obstaculo'].step([None] * 48, [[1.0] * 6] * 48) == [[0.0] * 6] * 48


def test_passo_segura_obstaculos_e_manda_aceleracao_zero():
    env = montar()
    env._reset()
    n_antes = len(env._env.clones[0].locais)
    env._action_repeat = 3
    env._env.fila += [estado(env._cena['spawn'])] * 3
    env._step(np.zeros(3, np.float32))
    assert len(env._env.clones[0].locais) == n_antes + 3                            # reimposto antes de cada tick
    assert np.allclose(env._env.locais_por_tick[-1], env._geo['imposto'])
    cmd = env._env.acoes[-1]
    assert cmd['obstaculo'] == [[0.0] * 6] * 48 and len(cmd['robot']) == 4


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
        assert env._dist_obstaculo(a)[0] >= folga
        assert np.linalg.norm(a - pos) >= c['dist_min_alvo']
    assert 350 < n_agua < 650                         # p_alvo_agua = 0,5


def test_alvos_fora_da_exclusao():
    env = montar()
    env._cena = dict(env._cena, exclusao=[{'min': [127, -155, -5], 'max': [131, -145, 5]}])
    for _ in range(300):
        a = env._sortear_alvo()
        assert env._dist_exclusao(a) >= env._cena['folga_alvo'] and a[0] > 131


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
@pytest.mark.parametrize('cena,pos,contato,motivo', [
    ('pilares', [133.88, -152.6, 2.0], False, None),
    ('pilares', [133.88, -152.6, 2.0], True, "contato"),
    ('pilares', [127.5, -150.0, 2.0], False, "parede"),       # 0,5 m da borda
    ('pilares', [134.0, -146.0, 5.0], False, "altura"),       # acima de 4,8
    ('pilares', [134.0, -146.0, -1.2], False, "altura"),
    ('pilares', [133.45, -152.0, 1.5], False, "pilar"),       # 0,605 m do torpedo mais perto do feixe (132,76; −152±0,16)
    ('pilares', [133.55, -152.0, 1.5], False, None),          # 0,701 m
    ('pilares', [133.45, -152.0, 5.5], False, "altura"),      # acima do pilar: altura
    ('dique', [129.0, -153.7, 0.55], False, "viga"),          # 0,505 m acima da viga sul (eixo em −0,05, raio 0,095)
    ('dique', [129.0, -153.7, 0.75], False, None),            # 0,705 m
    ('pilares', [129.0, -153.7, 0.55], False, None),          # sem vigas no cenário dos 4 pilares
])
def test_colisao(cena, pos, contato, motivo):
    env = montar(cena)
    env._dynamics = dyn(pos)
    assert env._colisao({'CollisionSensor': np.array([contato])}) == motivo


def test_spawn_colidindo_recusado():
    env = montar()
    env._cena = dict(env._cena, spawn=[133.3, -152.0, 1.0])
    with pytest.raises(ValueError):
        env._validar_spawn()
    for nome in ('pilares', 'dique'):
        montar(nome)._validar_spawn()


def test_colisao_caixa_de_exclusao():
    env = montar()
    env._cena = dict(env._cena, exclusao=[{'min': [130.5, -150.5, -5], 'max': [131, -150, 5]}])
    env._dynamics = dyn([131.5, -150.0, 1.0])
    assert env._colisao({}) == "obstaculo"


# --- R6–R8: passo completo --------------------------------------------------------------------------------------
def test_passo_colisao_termina_com_menos_um():
    env = montar()
    env._reset()
    env._env.fila.append(estado([127.3, -150.0, 2.0]))
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
    assert np.allclose(env._env.acoes[-1]['robot'], [0.31, 0, 0, 0], atol=1e-6)


# --- R9, R10: observação e registro -----------------------------------------------------------------------------
def test_obs_v0_pose9_mais_acoes():
    env = montar()
    obs, _ = env._reset()
    assert obs.shape == (12,) and env.observation_space.shape == (12,)
    env._target = np.array([131.0, -150.0, 1.0])                  # a origem do cenário
    env._dynamics = dyn([129.0, -150.0, 1.0], yaw=math.pi / 2)
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


def test_nivel_da_agua_vai_para_a_dinamica(monkeypatch):
    import core.environments as E
    env = object.__new__(GotoEnv)
    env._preparar_cenario('pilares')
    env._cena = dict(env._cena, nivel_agua=-0.4)
    env._agent_type, env._control_abstraction = 'Hydrone', 'cmd_vel_yaw'
    env._location, env._rotation, env._batch_size = [133.88, -152.6, 2.0], [0, 0, 0], 1
    env._env_version, env._observation_type = 'v2', 'DynamicsSensor'
    env_params, _ = env._build_params()
    robo = env_params['agents'][0]
    assert robo['dynamics']['water_level'] == -0.4
    assert any(s['sensor_type'] == 'CollisionSensor' for s in robo['sensors'])
    assert env._bounds[0, 2] == pytest.approx(-0.4 - 1.1)
    obst = env_params['agents'][-1]
    assert obst['dynamics']['water_level'] == -0.4 and obst['location'][2] == pytest.approx(-0.4 + GotoEnv.ALTURA_ESPERA)


def test_modulo_sem_simulador():
    assert G.GotoEnv.MAX_PASSOS == 1000 and G.GotoEnv.DIST_COLISAO == 0.625
