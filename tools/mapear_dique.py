"""Mapeia o dique inundado do Pier-Harbor e sugere onde pôr os 4 pilares do Goto (spec hydrone-goto-dique, T8).

Usa o BiguaSim direto (sem o biguagym), com o Hydrone teleportado e aceleração zero (``accel``: sem a dinâmica, que só
gastaria tempo, ele fica onde é posto); nada é alterado no simulador nem no
``goto_dique.json`` (a sugestão sai num arquivo à parte).

Fases:
1. **Varredura** (sem câmeras): grade de pontos a ``--z-varredura`` m de altura (acima de tudo; o mapa vai até 35 m) com um
   laser para baixo; cada leitura dá a altura da primeira superfície, ``topo = z do agente − distância``. Uma passada
   grossa (``--passo``) na ``--regiao`` acha a bacia; uma fina (``--passo-fino``) cobre só a bacia e as bordas.
2. **Bacia**: água = ``topo ≤ nível da água + --limiar-agua`` (o laser para na superfície ou passa e acha o fundo). A bacia
   é o maior grupo de células de água cercadas nas 4 direções (±x, ±y) por algo sólido dentro da região: o mar aberto
   não é cercado (o laser chega na borda da região sem achar nada), o dique é (paredes e navio). ``--semente x,y`` escolhe
   a bacia à mão.
3. **Posição**: distância de cada célula da bacia até o sólido mais próximo (transformada de distância); o quadrado da
   área do Goto vai onde a menor folga dentro dele é máxima: o maior retângulo de ``--lado-min`` a ``--lado`` com folga
   de pelo menos ``--folga`` até parede/navio (a 1 m da parede o Hydrone já colidiu no ar); 4 pilares e o spawn nas
   proporções do cenário provisório; o navio (sólido cercado pela bacia) vira caixa de exclusão do cenário ``dique``.
4. **Conferência** (mesmo lançamento): no centro, nos cantos da área e no spawn, o Hydrone é posto na água e no ar e
   mede o obstáculo mais próximo na horizontal (36 lasers), o fundo e se colidiu.
5. **Fotos** (segundo lançamento, ``--sem-fotos`` pula): pilares criados com ``spawn_prop`` nas posições sugeridas, fotos
   de cima (câmera para baixo a 25 e 60 m) e do spawn olhando para o centro, no ar e na água.

Uso (no lab, na raiz do repositório):
    python tools/mapear_dique.py                                   # região padrão em volta do dique
    python tools/mapear_dique.py --regiao 110,200,-275,-95 --passo 3 --passo-fino 1
    python tools/mapear_dique.py --semente 135,-200                # escolhe a bacia à mão
    python tools/mapear_dique.py --dry-run                         # mapa sintético, sem simulador (confere a análise)

Região padrão: pela vista de cima da documentação (``biguasim_docs/packages/SkyDive/Pier-Harbor``), o navio do dique fica
perto do "Moored Vessel" (142, −185) e a bacia em x ≈ 126–177, y ≈ −260 a −114; a região tem folga em volta.

Saída em ``mapear_dique/<data-hora>/``: ``mapa_grosso.png``, ``mapa.png`` (alturas, bacia, área, pilares, spawn, caixas),
``mapa.npz``, ``conferencia.csv``, ``cenario_sugerido.json`` (cenários ``pilares`` e ``dique`` no formato do
``goto_dique.json``), ``resumo.txt`` e as fotos.
"""
import argparse
import csv
import json
import math
import os
import sys
import time
import traceback

import numpy as np

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
STATE_JSON = os.path.join(REPO, 'biguagym', 'config', 'state.json')
GOTO_JSON = os.path.join(REPO, 'biguagym', 'config', 'goto_dique.json')

REGIAO_PADRAO = (110.0, 200.0, -275.0, -95.0)
ZERO = [0.0] * 6           # control_abstraction 'accel': [v̇, ω̇] zero
LASER_FUNDO_MAX = 80.0      # m: da altura da varredura até bem abaixo da água
N_LASERS = 36               # obstáculo mais próximo na conferência: 1 laser a cada 10°
DIST_COLISAO = 0.625        # GotoEnv.DIST_COLISAO
SPAWN_REL = (3.6, -2.6)     # spawn em relação ao centro da área, como no cenário provisório (103,6; 97,4) × (100; 100)


# ----------------------------------------------------------------------------------------------------------------------
# Análise (sem simulador)
# ----------------------------------------------------------------------------------------------------------------------
def grade(regiao, passo):
    x0, x1, y0, y1 = regiao
    return np.arange(x0, x1 + 1e-9, passo), np.arange(y0, y1 + 1e-9, passo)


def indice(xs, ys, x, y):
    return int(round((y - ys[0]) / (ys[1] - ys[0]))), int(round((x - xs[0]) / (xs[1] - xs[0])))


def classificar(topo, nivel_agua, limiar):
    """Água: a primeira superfície vista de cima está no nível da água (ou abaixo, se o laser atravessa a água)."""
    return np.asarray(topo) <= nivel_agua + limiar


def cercado(agua):
    """Quantas das 4 direções (±x, ±y) encontram sólido a partir de cada célula, dentro da região."""
    solido = ~agua
    n = np.zeros(agua.shape, dtype=np.int8)
    for eixo in (0, 1):
        n += np.maximum.accumulate(solido, axis=eixo)                                       # sólido antes (−)
        n += np.flip(np.maximum.accumulate(np.flip(solido, eixo), axis=eixo), eixo)       # sólido depois (+)
    return n


def achar_bacia(agua, xs, ys, semente=None):
    """Máscara da bacia: o grupo de água que contém a semente, ou o maior grupo de água cercado nas 4 direções."""
    from scipy import ndimage
    if semente is not None:
        iy, ix = indice(xs, ys, *semente)
        if not (0 <= iy < agua.shape[0] and 0 <= ix < agua.shape[1]) or not agua[iy, ix]:
            raise ValueError(f"a semente {semente} não cai em água dentro da região")
        rot, _ = ndimage.label(agua)
        comp = rot == rot[iy, ix]
        if not _toca_borda(comp):
            return comp
        # aberto para o mar: fica só a parte cercada que contém a semente
        nucleo = agua & (cercado(agua) == 4)
        rot, _ = ndimage.label(nucleo)
        if rot[iy, ix] == 0:
            raise ValueError(f"a semente {semente} está numa água aberta para fora da região")
        return rot == rot[iy, ix]
    nucleo = agua & (cercado(agua) == 4)
    rot, n = ndimage.label(nucleo)
    if n == 0:
        return None
    tamanhos = ndimage.sum(nucleo, rot, range(1, n + 1))
    return rot == (int(np.argmax(tamanhos)) + 1)


def _toca_borda(m):
    return bool(m[0].any() or m[-1].any() or m[:, 0].any() or m[:, -1].any())


def folga(bacia, passo):
    """Distância (m) de cada célula da bacia até a célula de fora da bacia mais próxima (conservadora: − meio passo)."""
    from scipy import ndimage
    d = ndimage.distance_transform_edt(bacia) * passo - passo / 2.0
    return np.where(bacia, np.maximum(d, 0.0), 0.0)


def posicionar(bacia, xs, ys, passo, lado, lado_min=None, folga_min=0.0, razao_max=2.0):
    """Retângulo da área do Goto: o maior (lados de ``lado_min`` a ``lado``, razão até ``razao_max``) cuja menor folga
    interna até o sólido chega a ``folga_min``, no lugar onde essa folga é máxima. Sem ``lado_min``, só o quadrado de
    ``lado``. Se nenhum tamanho tem a folga pedida, fica o de ``lado_min`` com a maior folga possível.
    Devolve (x, y, menor folga, largura em x, altura em y)."""
    from scipy import ndimage
    f = folga(bacia, passo)
    lados = [lado] if lado_min is None else list(np.arange(lado, lado_min - 1e-9, -passo))
    melhor, reserva = None, None
    for w in lados:
        for h in lados:
            if max(w, h) / min(w, h) > razao_max:
                continue
            kx, ky = 2 * int(round(w / 2.0 / passo)) + 1, 2 * int(round(h / 2.0 / passo)) + 1
            minimo = ndimage.minimum_filter(f, size=(ky, kx), mode='constant', cval=0.0)
            iy, ix = np.unravel_index(int(np.argmax(minimo)), minimo.shape)
            cand = (float(xs[ix]), float(ys[iy]), float(minimo[iy, ix]), (kx - 1) * passo, (ky - 1) * passo)
            if cand[2] >= folga_min and (melhor is None or (cand[3] * cand[4], min(cand[3:]), cand[2]) >
                                         (melhor[3] * melhor[4], min(melhor[3:]), melhor[2])):
                melhor = cand
            if reserva is None or cand[2] > reserva[2]:
                reserva = cand
    return melhor or reserva


def caixas_exclusao(bacia, agua, topo, xs, ys, passo, nivel_agua, margem=0.5, z_min=-5.0):
    """Caixas (formato do goto_dique.json, z relativo à água) dos sólidos dentro do retângulo da bacia: o navio e o que
    mais estiver dentro dele. Ficam fora só as faixas estreitas (até 2 m) que tocam a borda do retângulo, que são parede
    ou degrau: a borda da área já é colisão no GotoEnv. (No dique real o navio encosta na parede sul.)"""
    from scipy import ndimage
    iy, ix = np.nonzero(bacia)
    sub = (slice(iy.min(), iy.max() + 1), slice(ix.min(), ix.max() + 1))
    solido = ~agua[sub]
    rot, n = ndimage.label(solido)
    caixas, fora = [], 0.0
    for k in range(1, n + 1):
        m = rot == k
        ky, kx = np.nonzero(m)
        estreito = min(kx.max() - kx.min(), ky.max() - ky.min()) * passo < 2.0
        if _toca_borda(m) and estreito:
            fora += float(m.sum()) * passo * passo
            continue
        x0, x1 = float(xs[sub[1]][kx.min()]), float(xs[sub[1]][kx.max()])
        y0, y1 = float(ys[sub[0]][ky.min()]), float(ys[sub[0]][ky.max()])
        z_top = float(np.nanmax(topo[sub][m])) - nivel_agua
        caixas.append({'min': [round(x0 - passo / 2 - margem, 2), round(y0 - passo / 2 - margem, 2), z_min],
                       'max': [round(x1 + passo / 2 + margem, 2), round(y1 + passo / 2 + margem, 2), round(z_top + margem, 2)],
                       'area_m2': round(float(m.sum()) * passo * passo, 1)})
    return caixas, fora


def montar_cenarios(bacia, agua, topo, xs, ys, passo, nivel_agua, lado, afastamento=0.2, base=None, lado_min=None,
                    folga_min=0.0):
    """Cenários ``pilares`` e ``dique`` sugeridos, no formato do goto_dique.json (mantém os outros parâmetros de ``base``).
    Os 4 pilares ficam em centro ± ``afastamento``·lado em cada eixo e o spawn em centro + (0,36; −0,26)·lado, as mesmas
    proporções do cenário provisório (área de 10 m, pilares a ± 2 m, spawn em + (3,6; −2,6))."""
    base = base or {}
    cx, cy, f_min, w, h = posicionar(bacia, xs, ys, passo, lado, lado_min, folga_min)
    p0 = base.get('pilares', {})
    pilar = (p0.get('pilares') or [{'raio': 0.5, 'base_z': -3.0, 'altura': 8.0}])[0]
    pilares = [{'xy': [round(cx + sx * afastamento * w, 2), round(cy + sy * afastamento * h, 2)], 'raio': pilar['raio'],
                'base_z': pilar['base_z'], 'altura': pilar['altura']} for sx in (-1, 1) for sy in (-1, 1)]
    spawn = [round(cx + SPAWN_REL[0] / 10.0 * w, 2), round(cy + SPAWN_REL[1] / 10.0 * h, 2),
             (p0.get('spawn') or [0, 0, 2.0])[2]]
    pilares_cfg = {**p0, 'provisorio': False, 'nivel_agua': nivel_agua, 'origem': [round(cx, 2), round(cy, 2)],
                   'area': [[round(cx - w / 2, 2), round(cy - h / 2, 2)], [round(cx + w / 2, 2), round(cy + h / 2, 2)]],
                   'spawn': spawn, 'pilares': pilares, 'exclusao': []}
    iy, ix = np.nonzero(bacia)
    bx0, bx1 = float(xs[ix.min()]) - passo / 2, float(xs[ix.max()]) + passo / 2
    by0, by1 = float(ys[iy.min()]) - passo / 2, float(ys[iy.max()]) + passo / 2
    caixas, fora = caixas_exclusao(bacia, agua, topo, xs, ys, passo, nivel_agua)
    d0 = base.get('dique', {})
    dique_cfg = {**d0, 'provisorio': False, 'nivel_agua': nivel_agua,
                 'origem': [round((bx0 + bx1) / 2, 2), round((by0 + by1) / 2, 2)],
                 'area': [[round(bx0, 2), round(by0, 2)], [round(bx1, 2), round(by1, 2)]],
                 'spawn': spawn, 'pilares': [],
                 'exclusao': [{'min': c['min'], 'max': c['max']} for c in caixas]}
    medidas = {'folga_min_area_m': round(f_min, 2), 'area_lados_m': [w, h], 'bacia_m2': round(float(bacia.sum()) * passo * passo, 1),
               'bacia_retangulo': [[bx0, by0], [bx1, by1]], 'caixas': caixas,
               'solido_nas_bordas_do_retangulo_m2': round(fora, 1), 'passo_m': passo}
    return pilares_cfg, dique_cfg, medidas


def checar_cenario(cfg, dist_colisao=DIST_COLISAO):
    """Problemas que o GotoEnv recusaria ou que atrapalham o treino (lista vazia = ok)."""
    erros = []
    (x0, y0), (x1, y1) = cfg['area']
    sx, sy, sz = cfg['spawn']
    if not (x0 + dist_colisao < sx < x1 - dist_colisao and y0 + dist_colisao < sy < y1 - dist_colisao):
        erros.append(f"spawn {cfg['spawn']} fora da área (ou a menos de {dist_colisao} m da borda)")
    for p in cfg['pilares']:
        px, py = p['xy']
        if not (x0 < px - p['raio'] and px + p['raio'] < x1 and y0 < py - p['raio'] and py + p['raio'] < y1):
            erros.append(f"pilar {p['xy']} sai da área")
        if math.hypot(sx - px, sy - py) - p['raio'] < dist_colisao:
            erros.append(f"spawn a menos de {dist_colisao} m do pilar {p['xy']}")
    return erros


def mapa_sintetico(regiao=REGIAO_PADRAO, passo=1.0):
    """Mapa de teste: cais a 3 m, bacia de 47 × 142 m com fundo a −6 m, navio de 14 × 95 m (10 m) dentro e mar a leste e
    ao sul (o laser não acha nada: topo bem abaixo da água)."""
    xs, ys = grade(regiao, passo)
    X, Y = np.meshgrid(xs, ys)
    topo = np.full(X.shape, 3.0)
    topo[(X > 180) | (Y < -262)] = -60.0
    topo[(X >= 128) & (X <= 175) & (Y >= -258) & (Y <= -116)] = -6.0
    topo[(X >= 143) & (X <= 157) & (Y >= -235) & (Y <= -140)] = 10.0
    return xs, ys, topo


# ----------------------------------------------------------------------------------------------------------------------
# Desenho
# ----------------------------------------------------------------------------------------------------------------------
def desenhar(caminho, topo, xs, ys, agua, nivel_agua, bacia=None, pilares_cfg=None, dique_cfg=None, px_max=1100):
    import cv2
    passo = float(xs[1] - xs[0])
    esc = max(1, int(px_max / max(topo.shape)))
    alt = np.nan_to_num(topo - nivel_agua, nan=-50.0)
    img = np.zeros(topo.shape + (3,), np.uint8)
    seco = np.clip(alt / 15.0, 0, 1)                                        # 0–15 m: cinza claro → marrom
    img[..., 0] = (200 - 150 * seco).astype(np.uint8)
    img[..., 1] = (200 - 110 * seco).astype(np.uint8)
    img[..., 2] = (200 - 40 * seco).astype(np.uint8)
    prof = np.clip(-alt / 10.0, 0, 1)                                       # água: azul, mais escuro mais fundo
    img[agua] = np.stack([235 - 100 * prof, 170 - 120 * prof, 60 - 50 * prof], -1)[agua].astype(np.uint8)
    img = np.flipud(img)                                                    # y para cima
    img = cv2.resize(img, (img.shape[1] * esc, img.shape[0] * esc), interpolation=cv2.INTER_NEAREST)
    m = 60
    tela = np.full((img.shape[0] + 2 * m, img.shape[1] + 2 * m, 3), 255, np.uint8)
    tela[m:m + img.shape[0], m:m + img.shape[1]] = img

    def px(x, y):
        return (int(m + ((x - xs[0]) / passo + 0.5) * esc), int(m + ((ys[-1] - y) / passo + 0.5) * esc))

    if bacia is not None:
        cont = np.flipud(bacia).astype(np.uint8)
        cont = cv2.resize(cont, (cont.shape[1] * esc, cont.shape[0] * esc), interpolation=cv2.INTER_NEAREST)
        cs, _ = cv2.findContours(cont, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        cv2.drawContours(tela[m:m + img.shape[0], m:m + img.shape[1]], cs, -1, (255, 255, 0), 2)
    if dique_cfg is not None:
        for c in dique_cfg['exclusao']:
            cv2.rectangle(tela, px(c['min'][0], c['min'][1]), px(c['max'][0], c['max'][1]), (255, 0, 255), 2)
    if pilares_cfg is not None:
        (x0, y0), (x1, y1) = pilares_cfg['area']
        cv2.rectangle(tela, px(x0, y0), px(x1, y1), (0, 220, 255), 2)
        for p in pilares_cfg['pilares']:
            cv2.circle(tela, px(*p['xy']), max(3, int(p['raio'] / passo * esc)), (0, 0, 255), -1)
        cv2.drawMarker(tela, px(*pilares_cfg['spawn'][:2]), (0, 160, 0), cv2.MARKER_TRIANGLE_UP, 14, 2)
    fonte = cv2.FONT_HERSHEY_SIMPLEX
    passo_eixo = 10 if (xs[-1] - xs[0]) <= 120 else 20
    for x in np.arange(math.ceil(xs[0] / passo_eixo) * passo_eixo, xs[-1] + 1e-9, passo_eixo):
        p = px(x, ys[0])
        cv2.line(tela, (p[0], m + img.shape[0]), (p[0], m + img.shape[0] + 6), (0, 0, 0), 1)
        cv2.putText(tela, f"{x:.0f}", (p[0] - 14, m + img.shape[0] + 22), fonte, 0.4, (0, 0, 0), 1)
    for y in np.arange(math.ceil(ys[0] / passo_eixo) * passo_eixo, ys[-1] + 1e-9, passo_eixo):
        p = px(xs[0], y)
        cv2.line(tela, (m - 6, p[1]), (m, p[1]), (0, 0, 0), 1)
        cv2.putText(tela, f"{y:.0f}", (4, p[1] + 4), fonte, 0.4, (0, 0, 0), 1)
    cv2.putText(tela, "x (m) para a direita, y (m) para cima; azul: agua, ciano: bacia", (m, 18), fonte, 0.4, (0, 0, 0), 1)
    cv2.putText(tela, "amarelo: area, vermelho: pilares, verde: spawn, magenta: exclusao", (m, 36), fonte, 0.4,
                (0, 0, 0), 1)
    cv2.imwrite(caminho, tela)


# ----------------------------------------------------------------------------------------------------------------------
# Simulador
# ----------------------------------------------------------------------------------------------------------------------
def sensores(com_cameras, largura=1024, altura=1024):
    s = [
        {'sensor_type': 'DynamicsSensor', 'socket': 'IMUSocket',
         'configuration': {'UseCOM': True, 'UseRPY': False}, 'location': [0, 0, 0], 'rotation': [0, 0, 0]},
        {'sensor_name': 'RPYDynamicsSensor', 'sensor_type': 'DynamicsSensor', 'socket': 'IMUSocket',
         'configuration': {'UseCOM': False, 'UseRPY': True}, 'location': [0, 0, 0], 'rotation': [0, 0, 0]},
        {'sensor_type': 'CollisionSensor', 'location': [0, 0, 0], 'rotation': [0, 0, 0]},
        {'sensor_name': 'Distancias', 'sensor_type': 'RangeFinderSensor', 'socket': 'IMUSocket',
         'configuration': {'LaserMaxDistance': 30, 'LaserCount': N_LASERS, 'LaserAngle': 0, 'LaserDebug': False}},
        {'sensor_name': 'Fundo', 'sensor_type': 'RangeFinderSensor', 'socket': 'IMUSocket',
         'configuration': {'LaserMaxDistance': LASER_FUNDO_MAX, 'LaserCount': 1, 'LaserAngle': -90, 'LaserDebug': False}},
    ]
    if com_cameras:
        s += [
            {'sensor_name': 'CameraTerceira', 'sensor_type': 'RGBCamera', 'socket': 'Viewport',
             'configuration': {'CaptureWidth': 960, 'CaptureHeight': 540}, 'location': [0, 0, 0], 'rotation': [0, 0, 0]},
            {'sensor_name': 'CameraFrente', 'sensor_type': 'RGBCamera',
             'configuration': {'CaptureWidth': 960, 'CaptureHeight': 540}, 'location': [0.35, 0, 0.05], 'rotation': [0, 0, 0]},
            {'sensor_name': 'CameraBaixo', 'sensor_type': 'RGBCamera',
             'configuration': {'CaptureWidth': largura, 'CaptureHeight': altura}, 'location': [0, 0, -0.1],
             'rotation': [0, 90, 0]},   # pitch +90 olha para baixo (−90 olhou para cima no lab)
        ]
    return s


def abrir(ponto, args, com_cameras):
    import biguasim
    with open(STATE_JSON) as f:
        base = json.load(f)
    cfg = {k: v for k, v in base.items() if k != 'agents'}
    cfg['agents'] = [{
        'agent_name': 'robot', 'agent_type': 'Hydrone', 'control_abstraction': 'accel',
        'dynamics': {'batch_size': 1, 'water_level': float(args.agua)},
        'location': [float(v) for v in ponto], 'rotation': [0.0, 0.0, 0.0],
        'sensors': sensores(com_cameras),
    }]
    env = biguasim.make(scenario_cfg=cfg, show_viewport=False)
    env.reset()
    agente = next(v for k, v in env.agents.items() if k.startswith('robot'))
    return env, agente


def fechar(env):
    from explorar_mapa import processos_simulador
    if hasattr(env, '__on_exit__'):
        env.__on_exit__()
    del env
    time.sleep(2)
    restantes = processos_simulador()
    print(f"processos do simulador depois de fechar: {len(restantes)}", flush=True)
    for ln in restantes:
        print('   ', ln[:160], flush=True)


def ler(s):
    from explorar_mapa import plano
    s = plano(s)
    rpy = np.asarray(s['RPYDynamicsSensor'], dtype=float).ravel()
    out = {'x': rpy[6], 'y': rpy[7], 'z': rpy[8], 'fundo': float(np.asarray(s['Fundo'], dtype=float).ravel()[0]),
           'colisao': bool(np.any(np.asarray(s['CollisionSensor'])))}
    d = np.asarray(s['Distancias'], dtype=float).ravel()
    out['obstaculo'] = float(d.min())
    return out, s


def ir(env, agente, x, y, z, yaw=0.0, ticks=1, tol=0.3, max_ticks=4):
    """Teleporta e avança até a leitura estar no ponto pedido (o teleporte vale no tick seguinte)."""
    agente.set_physics_state([x, y, z], [0.0, 0.0, yaw], [0.0, 0.0, 0.0], [0.0, 0.0, 0.0])
    for t in range(max_ticks):
        m, s = ler(env.step(ZERO))
        if t + 1 >= ticks and abs(m['x'] - x) < tol and abs(m['y'] - y) < tol:
            return m, s, True
    return m, s, False


def varrer(env, agente, xs, ys, z, rotulo):
    topo = np.full((len(ys), len(xs)), np.nan)
    sem_eco = np.zeros(topo.shape, bool)
    fora, t0, n, total = 0, time.time(), 0, topo.size
    for iy, y in enumerate(ys):
        ordem = range(len(xs)) if iy % 2 == 0 else range(len(xs) - 1, -1, -1)
        for ix in ordem:
            m, _, ok = ir(env, agente, float(xs[ix]), float(y), z)
            fora += not ok
            if m['fundo'] >= LASER_FUNDO_MAX - 1e-3:
                sem_eco[iy, ix] = True
                topo[iy, ix] = m['z'] - LASER_FUNDO_MAX
            else:
                topo[iy, ix] = m['z'] - m['fundo']
            n += 1
            if n % 500 == 0:
                v = n / (time.time() - t0)
                print(f"   {rotulo}: {n}/{total} pontos, {v:.1f} pontos/s, faltam ~{(total - n) / v / 60:.1f} min",
                      flush=True)
    print(f"   {rotulo}: {total} pontos em {(time.time() - t0) / 60:.1f} min; {int(sem_eco.sum())} sem eco até "
          f"{LASER_FUNDO_MAX:.0f} m; {fora} leituras fora do ponto pedido", flush=True)
    return topo, sem_eco


def conferir(env, agente, pilares_cfg, folga_mapa, xs, ys, nivel_agua, zs):
    (x0, y0), (x1, y1) = pilares_cfg['area']
    cx, cy = pilares_cfg['origem']
    pontos = [('centro', cx, cy), ('canto_so', x0 + 0.5, y0 + 0.5), ('canto_se', x1 - 0.5, y0 + 0.5),
              ('canto_no', x0 + 0.5, y1 - 0.5), ('canto_ne', x1 - 0.5, y1 - 0.5),
              ('spawn', pilares_cfg['spawn'][0], pilares_cfg['spawn'][1])]
    linhas = []
    for nome, x, y in pontos:
        iy, ix = indice(xs, ys, x, y)
        for zr in zs:
            colidiu = False
            for k in range(10):                          # 0,5 s para assentar
                m, _, _ = ir(env, agente, x, y, nivel_agua + zr) if k == 0 else (*ler(env.step(ZERO)), True)
                colidiu |= m['colisao']
            linhas.append({'ponto': nome, 'x': round(x, 2), 'y': round(y, 2), 'z_rel': zr,
                           'x_med': round(m['x'], 2), 'y_med': round(m['y'], 2), 'z_med': round(m['z'], 2),
                           'obstaculo_horizontal_m': round(m['obstaculo'], 2), 'folga_mapa_m': round(float(folga_mapa[iy, ix]), 2),
                           'abaixo_m': round(m['fundo'], 2), 'fundo_z': round(m['z'] - m['fundo'], 2) if m['fundo'] < LASER_FUNDO_MAX else None,
                           'colidiu': colidiu})
            print('   ', json.dumps(linhas[-1], ensure_ascii=False), flush=True)
    return linhas


LOG_MOTOR = os.path.expanduser('~/.local/share/biguasim/*/worlds/*/Linux/*/Saved/Logs/HolodeckLog.txt')


def spawnprop_recusado(desde: float) -> int:
    """Quantos SpawnProp o motor recusou nos logs escritos desde ``desde`` (o motor renomeia o log da rodada anterior
    para HolodeckLog-backup-*.txt ao abrir; no lab, o mundo SkyDive 1.1.0 não conhece o comando)."""
    import glob
    n = 0
    for log in glob.glob(LOG_MOTOR.replace('HolodeckLog.txt', 'HolodeckLog*.txt')):
        if os.path.getmtime(log) >= desde:
            with open(log, errors='replace') as f:
                n += sum('failed to make command:  SpawnProp' in ln for ln in f)
    return n


def fotos(args, pilares_cfg, saida):
    import cv2
    from explorar_mapa import imagem, plano
    cx, cy = pilares_cfg['origem']
    sx, sy, _ = pilares_cfg['spawn']
    agua = float(args.agua)
    env, agente = abrir([cx, cy, agua + 25.0], args, com_cameras=True)
    try:
        for i, p in enumerate(pilares_cfg['pilares']):
            r, h = float(p['raio']), float(p['altura'])
            env.spawn_prop('cylinder', location=[float(p['xy'][0]), float(p['xy'][1]), agua + float(p['base_z']) + h / 2],
                           rotation=[0.0, 0.0, 0.0], scale=[2 * r, 2 * r, h], material='steel', tag='Pilar',
                           name=f'pilar{i}')
        olhar = math.degrees(math.atan2(cy - sy, cx - sx))
        for nome, (x, y, z, yaw) in (('cima_25m', (cx, cy, agua + 25.0, 0.0)), ('cima_60m', (cx, cy, agua + 60.0, 0.0)),
                                     ('spawn_ar', (sx, sy, agua + 2.0, olhar)), ('spawn_agua', (sx, sy, agua - 0.5, olhar))):
            ir(env, agente, x, y, z, yaw)
            for _ in range(20):
                s = plano(env.step(ZERO))
            for sensor in ('CameraBaixo', 'CameraFrente', 'CameraTerceira'):
                if sensor == 'CameraBaixo' and not nome.startswith('cima'):
                    continue
                img = imagem(s.get(sensor))
                if img is not None:
                    cv2.imwrite(os.path.join(saida, f"foto_{nome}_{sensor}.png"), img)
            print(f"   fotos {nome}: ({x:.1f}, {y:.1f}, {z:.1f}), guinada {yaw:.0f}°", flush=True)
    finally:
        fechar(env)


# ----------------------------------------------------------------------------------------------------------------------
def analisar(topo, xs, ys, args, saida, sufixo='', semente=None):
    agua = classificar(topo, args.agua, args.limiar_agua)
    bacia = achar_bacia(agua, xs, ys, semente)
    desenhar(os.path.join(saida, f'mapa{sufixo}.png'), topo, xs, ys, agua, args.agua, bacia)
    return agua, bacia


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--regiao', default=','.join(str(v) for v in REGIAO_PADRAO), help='x0,x1,y0,y1 da passada grossa')
    ap.add_argument('--passo', type=float, default=3.0, help='passo da passada grossa (m)')
    ap.add_argument('--passo-fino', type=float, default=1.0, help='passo da passada fina na bacia (m); 0 pula')
    ap.add_argument('--z-varredura', type=float, default=40.0, help='altura da varredura (m, acima de tudo no mapa)')
    ap.add_argument('--agua', type=float, default=0.0, help='nível da água (m)')
    ap.add_argument('--limiar-agua', type=float, default=0.5, help='topo até nível + limiar conta como água (m)')
    ap.add_argument('--semente', default=None, help='x,y dentro da bacia (escolhe a bacia à mão)')
    ap.add_argument('--lado', type=float, default=10.0, help='maior lado da área do cenário pilares (m)')
    ap.add_argument('--lado-min', type=float, default=4.0, help='menor lado aceito para a área (m)')
    ap.add_argument('--folga', type=float, default=1.5, help='folga mínima da área até parede/navio (m)')
    ap.add_argument('--afastamento', type=float, default=0.2, help='pilares em centro ± afastamento·lado')
    ap.add_argument('--mapa', default=None, help='pasta de uma rodada anterior: usa o mapa.npz dela (sem varrer)')
    ap.add_argument('--z-conferencia', default='-0.7,2.0,4.5', help='alturas da conferência, relativas à água')
    ap.add_argument('--sem-fotos', action='store_true')
    ap.add_argument('--saida', default=None)
    ap.add_argument('--dry-run', action='store_true', help='mapa sintético, sem simulador')
    args = ap.parse_args()

    regiao = tuple(float(v) for v in args.regiao.split(','))
    semente = tuple(float(v) for v in args.semente.split(',')) if args.semente else None
    saida = args.saida or os.path.join(REPO, 'mapear_dique', time.strftime('%Y%m%d-%H%M%S') + ('_dry' if args.dry_run else ''))
    os.makedirs(saida, exist_ok=True)
    with open(GOTO_JSON) as f:
        base = json.load(f)['cenarios']
    zs = [float(v) for v in args.z_conferencia.split(',')]
    print(f"saída: {saida}", flush=True)

    env = None
    try:
        if args.mapa:
            # mapa de uma rodada anterior: sem varrer de novo; o simulador só abre para a conferência
            d = np.load(os.path.join(args.mapa, 'mapa.npz'))
            xs, ys, topo = d['xs'], d['ys'], d['topo']
            passo = float(xs[1] - xs[0])
            agua = classificar(topo, args.agua, args.limiar_agua)
            bacia = d['bacia'] if semente is None else achar_bacia(agua, xs, ys, semente)
            print(f"mapa de {args.mapa}: {len(xs)} × {len(ys)} pontos, passo {passo} m", flush=True)
            if not args.dry_run:
                env, agente = abrir([float(xs[0]), float(ys[0]), args.z_varredura], args, com_cameras=False)
        else:
            # 1–2. passada grossa e bacia
            if args.dry_run:
                xs, ys, topo = mapa_sintetico(regiao, args.passo)
            else:
                env, agente = abrir([regiao[0], regiao[2], args.z_varredura], args, com_cameras=False)
                print("== passada grossa", flush=True)
                xs, ys, topo = (*grade(regiao, args.passo), None)
                topo, _ = varrer(env, agente, xs, ys, args.z_varredura, 'grossa')
            agua, bacia = analisar(topo, xs, ys, args, saida, '_grosso', semente)
            if bacia is None:
                raise SystemExit(f"nenhuma água cercada nas 4 direções na região {regiao}; veja {saida}/mapa_grosso.png e "
                                 f"passe --semente x,y dentro do dique")
            f = folga(bacia, args.passo)
            iy, ix = np.unravel_index(int(np.argmax(f)), f.shape)
            semente_fina = (float(xs[ix]), float(ys[iy]))
            jy, jx = np.nonzero(bacia)
            print(f"bacia (grossa): {bacia.sum() * args.passo ** 2:.0f} m², x {xs[jx.min()]:.0f}–{xs[jx.max()]:.0f}, "
                  f"y {ys[jy.min()]:.0f}–{ys[jy.max()]:.0f}; ponto mais folgado {semente_fina}", flush=True)

            # passada fina na bacia e bordas
            passo = args.passo
            if args.passo_fino > 0:
                borda = 2 * args.passo
                fina = (xs[jx.min()] - borda, xs[jx.max()] + borda, ys[jy.min()] - borda, ys[jy.max()] + borda)
                if args.dry_run:
                    xs, ys, topo = mapa_sintetico(regiao, args.passo_fino)
                    sel_x = (xs >= fina[0]) & (xs <= fina[1])
                    sel_y = (ys >= fina[2]) & (ys <= fina[3])
                    xs, ys, topo = xs[sel_x], ys[sel_y], topo[np.ix_(sel_y, sel_x)]
                else:
                    print(f"== passada fina em x {fina[0]:.0f}–{fina[1]:.0f}, y {fina[2]:.0f}–{fina[3]:.0f}", flush=True)
                    xs, ys = grade(fina, args.passo_fino)
                    topo, _ = varrer(env, agente, xs, ys, args.z_varredura, 'fina')
                passo = args.passo_fino
                agua = classificar(topo, args.agua, args.limiar_agua)
                bacia = achar_bacia(agua, xs, ys, semente_fina)

        # 3. posição
        pilares_cfg, dique_cfg, medidas = montar_cenarios(bacia, agua, topo, xs, ys, passo, args.agua, args.lado,
                                                          args.afastamento, base, args.lado_min, args.folga)
        folga_mapa = folga(bacia, passo)
        np.savez_compressed(os.path.join(saida, 'mapa.npz'), xs=xs, ys=ys, topo=topo, agua=agua, bacia=bacia,
                            folga=folga_mapa)
        desenhar(os.path.join(saida, 'mapa.png'), topo, xs, ys, agua, args.agua, bacia, pilares_cfg, dique_cfg)
        erros = checar_cenario(pilares_cfg) + [f"dique: {e}" for e in checar_cenario(dique_cfg)]
        if medidas['folga_min_area_m'] < args.folga:
            erros.append(f"nenhuma área de {args.lado_min} a {args.lado} m tem {args.folga} m de folga; a de "
                         f"{medidas['area_lados_m']} m tem {medidas['folga_min_area_m']} m")

        # 4. conferência
        linhas = []
        if env is not None:
            print("== conferência (sem os pilares)", flush=True)
            linhas = conferir(env, agente, pilares_cfg, folga_mapa, xs, ys, args.agua, zs)
            with open(os.path.join(saida, 'conferencia.csv'), 'w', newline='') as fc:
                w = csv.DictWriter(fc, fieldnames=list(linhas[0]))
                w.writeheader()
                w.writerows(linhas)
            for ln in linhas:
                if ln['colidiu']:
                    erros.append(f"conferência: colidiu em {ln['ponto']} z={ln['z_rel']}")
                if ln['obstaculo_horizontal_m'] < 1.0:
                    erros.append(f"conferência: obstáculo a {ln['obstaculo_horizontal_m']} m em {ln['ponto']} z={ln['z_rel']}")
                if ln['z_rel'] < 0 and ln['fundo_z'] is not None and ln['fundo_z'] - args.agua > -1.5:
                    erros.append(f"conferência: fundo raso ({ln['fundo_z']} m) em {ln['ponto']}")
    except Exception:
        traceback.print_exc()
        raise
    finally:
        if env is not None:
            fechar(env)

    sugestao = {'_comentario': f"Gerado por tools/mapear_dique.py em {time.strftime('%Y-%m-%d %H:%M')}; "
                               "conferir as fotos antes de copiar para o goto_dique.json.",
                'cenarios': {'pilares': pilares_cfg, 'dique': dique_cfg}, 'medidas': medidas, 'problemas': erros}
    with open(os.path.join(saida, 'cenario_sugerido.json'), 'w') as fj:
        json.dump(sugestao, fj, indent=2, ensure_ascii=False)
    resumo = [f"bacia: {medidas['bacia_m2']} m², retângulo {medidas['bacia_retangulo']}",
              f"área dos pilares: {pilares_cfg['area']} (centro {pilares_cfg['origem']}), folga mínima "
              f"{medidas['folga_min_area_m']} m até parede/navio",
              f"pilares: {[p['xy'] for p in pilares_cfg['pilares']]}", f"spawn: {pilares_cfg['spawn']}",
              f"caixas de exclusão do dique: {[(c['min'], c['max']) for c in dique_cfg['exclusao']]}",
              f"problemas: {erros or 'nenhum'}"]
    if linhas:
        agua_l = [ln for ln in linhas if ln['z_rel'] < 0]
        ar_l = [ln for ln in linhas if ln['z_rel'] >= 0]
        resumo.append(f"conferência: obstáculo horizontal mínimo {min(ln['obstaculo_horizontal_m'] for ln in agua_l)} m "
                      f"na água e {min(ln['obstaculo_horizontal_m'] for ln in ar_l)} m no ar; fundo em "
                      f"{sorted({ln['fundo_z'] for ln in agua_l if ln['fundo_z'] is not None})} m")
    with open(os.path.join(saida, 'resumo.txt'), 'w') as fr:
        fr.write('\n'.join(resumo) + '\n')
    print('== resumo\n' + '\n'.join(resumo), flush=True)

    # 5. fotos com os pilares
    if not args.dry_run and not args.sem_fotos:
        print("== fotos com os pilares", flush=True)
        t_fotos = time.time()
        fotos(args, pilares_cfg, saida)
        recusados = spawnprop_recusado(t_fotos)
        if recusados:
            print(f"ATENÇÃO: o motor recusou {recusados} SpawnProp no último log ({LOG_MOTOR}): os pilares NÃO foram "
                  "criados no simulador (nem nas fotos, nem no GotoEnv)", flush=True)
    return 1 if erros else 0


if __name__ == '__main__':
    sys.exit(main())
