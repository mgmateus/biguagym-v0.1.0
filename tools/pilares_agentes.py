"""Pilares feitos de agentes parados (spec hydrone-goto-dique, T8): teste de viabilidade no simulador.

Por quê: o motor do mundo não cria objetos (sem ``SpawnProp``), o DebugDraw só aparece na câmera RGB e o Pier-Harbor não
tem pilares nem blocos em água aberta (``tools/achar_pilares.py``). Agentes têm geometria de verdade (câmeras, profundidade,
LiDAR e sonar os veem). Aqui cada pilar é uma coluna de ``--empilhar`` agentes ``--tipo`` em pé (pitch 90°), em
``accel`` com aceleração zero (o motor não aplica gravidade a quem recebe aceleração zero: ficam onde são postos).

O teste:
1. Hydrone + 4 × ``--empilhar`` agentes nos pilares sugeridos do dique (``mapear_dique``, 2026-11-18).
2. ``--ticks`` passos parados: deriva de posição e de atitude de cada agente-pilar.
3. Fotos do spawn olhando para o centro (RGB e profundidade, no ar e na água) e o LiDAR horizontal (360 lasers): a menor
   distância na direção de cada pilar, comparada com a distância geométrica.
4. Passos/s com os agentes extras.

Uso (no lab):  python tools/pilares_agentes.py [--tipo TorpedoAUV] [--empilhar 3]
Saída em ``pilares_agentes/<data-hora>/``: fotos, ``resultado.json``.
"""
import argparse
import json
import math
import os
import sys
import time

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mapear_dique as M  # noqa: E402
import achar_pilares as A  # noqa: E402

COMPRIMENTO = {'TorpedoAUV': 2.1}


def din():
    return [{'sensor_type': 'DynamicsSensor', 'socket': 'IMUSocket',
             'configuration': {'UseCOM': True, 'UseRPY': False}, 'location': [0, 0, 0], 'rotation': [0, 0, 0]},
            {'sensor_name': 'RPYDynamicsSensor', 'sensor_type': 'DynamicsSensor', 'socket': 'IMUSocket',
             'configuration': {'UseCOM': False, 'UseRPY': True}, 'location': [0, 0, 0], 'rotation': [0, 0, 0]}]


def estado_clone(estado, j):
    """Estado do clone j do lote 'pilar', em qualquer dos formatos do BiguaSim (por nome, lista ou dicionário)."""
    if f'pilar-id{j}' in estado:
        return estado[f'pilar-id{j}']
    lote = estado.get('pilar')
    if isinstance(lote, list):
        return lote[j]
    if isinstance(lote, dict):
        if f'pilar-id{j}' in lote:
            return lote[f'pilar-id{j}']
        if 'RPYDynamicsSensor' in lote:                      # sensores empilhados no lote: linha j
            return {k: np.asarray(v)[j] for k, v in lote.items()}
    raise KeyError(f"estado do pilar {j} não encontrado; chaves: {list(estado)}")


def niveis(empilhar, comprimento, z_baixo=-1.2):
    """Centros (z relativo à água) de ``empilhar`` agentes em pé, encostados, a partir de ``z_baixo``."""
    return [z_baixo + comprimento * (k + 0.5) for k in range(empilhar)]


def main():
    import cv2
    import biguasim
    from explorar_mapa import imagem, plano

    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--tipo', default='TorpedoAUV')
    ap.add_argument('--empilhar', type=int, default=3)
    ap.add_argument('--comprimento', type=float, default=None, help='comprimento do agente (m); padrão pelo tipo')
    ap.add_argument('--ticks', type=int, default=100)
    ap.add_argument('--agua', type=float, default=0.0)
    ap.add_argument('--saida', default=None)
    args = ap.parse_args()
    comp = args.comprimento or COMPRIMENTO.get(args.tipo, 2.0)
    saida = args.saida or os.path.join(M.REPO, 'pilares_agentes', time.strftime('%Y%m%d-%H%M%S'))
    os.makedirs(saida, exist_ok=True)
    print(f"saída: {saida}", flush=True)

    pilares = A.DIQUE_PILARES
    sx, sy = A.DIQUE_SPAWN
    zs = niveis(args.empilhar, comp)
    alvos = [(px, py, args.agua + z) for px, py in pilares for z in zs]
    n = len(alvos)

    with open(M.STATE_JSON) as f:
        base = json.load(f)
    cfg = {k: v for k, v in base.items() if k != 'agents'}
    cfg['agents'] = [
        {'agent_name': 'robot', 'agent_type': 'Hydrone', 'control_abstraction': 'accel',
         'dynamics': {'batch_size': 1, 'water_level': args.agua}, 'location': [sx, sy, args.agua + 2.0],
         'rotation': [0.0, 0.0, 0.0],
         'sensors': M.sensores(True, extras=[A.LIDAR, A.PROFUNDIDADE])},
        # os clones nascem todos no mesmo ponto e são teleportados depois; nascem alto para não colidirem com nada
        {'agent_name': 'pilar', 'agent_type': args.tipo, 'control_abstraction': 'accel',
         'dynamics': {'batch_size': n, 'water_level': args.agua}, 'location': [sx, sy, args.agua + 30.0],
         'rotation': [0.0, 90.0, 0.0], 'sensors': din()},
    ]
    zero = {'robot': [0.0] * 6, 'pilar': [[0.0] * 6 for _ in range(n)]}
    resultado = {'tipo': args.tipo, 'empilhar': args.empilhar, 'comprimento': comp, 'agentes_pilar': n}
    env = biguasim.make(scenario_cfg=cfg, show_viewport=False)
    try:
        env.reset()
        robo = env.agents['robot-id0']
        clones = [env.agents[f'pilar-id{j}'] for j in range(n)]
        for c, (x, y, z) in zip(clones, alvos):
            c.set_physics_state([x, y, z], [0.0, 90.0, 0.0], [0.0, 0.0, 0.0], [0.0, 0.0, 0.0])
        t0 = time.time()
        for _ in range(args.ticks):
            estado = env.step(zero)
        resultado['passos_por_s'] = round(args.ticks / (time.time() - t0), 2)

        # deriva de cada agente-pilar (RPYDynamicsSensor: posição [6:9], atitude em graus [15:18])
        print(f"chaves do estado: {list(estado)[:6]} ... ({len(estado)}); "
              f"'pilar': {type(estado.get('pilar')).__name__}", flush=True)
        derivas = []
        for j, (x, y, z) in enumerate(alvos):
            s = estado_clone(estado, j)
            rpy = np.asarray(s['RPYDynamicsSensor'], dtype=float).ravel()
            derivas.append({'agente': j, 'alvo': [x, y, z], 'pos': np.round(rpy[6:9], 2).tolist(),
                            'erro_m': round(float(np.linalg.norm(rpy[6:9] - [x, y, z])), 3),
                            'rpy_graus': np.round(rpy[15:18], 1).tolist()})
        resultado['derivas'] = derivas
        print(f"passos/s: {resultado['passos_por_s']}; maior deriva: {max(d['erro_m'] for d in derivas)} m", flush=True)
        for d in derivas:
            print('   ', json.dumps(d), flush=True)

        # fotos e LiDAR do spawn olhando para o centro dos pilares
        cx, cy = sum(p[0] for p in pilares) / 4, sum(p[1] for p in pilares) / 4
        yaw = math.degrees(math.atan2(cy - sy, cx - sx))
        for nome, z in (('ar', 2.0), ('agua', -0.5)):
            robo.set_physics_state([sx, sy, args.agua + z], [0.0, 0.0, yaw], [0.0] * 3, [0.0] * 3)
            for _ in range(15):
                estado = env.step(zero)
            s = plano(estado)
            for sensor in ('CameraFrente', 'CameraTerceira'):
                img = imagem(s.get(sensor))
                if img is not None:
                    cv2.imwrite(os.path.join(saida, f"{nome}_{sensor}.png"), img)
            A.salvar_profundidade(os.path.join(saida, f"{nome}_profundidade.png"), s.get('DepthCamera'))
            rpy = np.asarray(s['RPYDynamicsSensor'], dtype=float).ravel()
            lid = np.asarray(s['Lidar'], dtype=float).ravel()
            psi = math.radians(float(rpy[17]))
            vistos = []
            for px, py in pilares:
                ang = math.atan2(py - rpy[7], px - rpy[6])
                i = int(round(((ang - psi) % (2 * math.pi)) / (2 * math.pi) * len(lid))) % len(lid)
                janela = [lid[(i + k) % len(lid)] for k in range(-3, 4)]
                vistos.append({'pilar': [px, py], 'dist_geometrica': round(math.hypot(px - rpy[6], py - rpy[7]), 2),
                               'lidar_min_na_direcao': round(float(min(janela)), 2)})
            resultado[f'lidar_{nome}'] = vistos
            print(f"LiDAR {nome}: {vistos}", flush=True)
    finally:
        with open(os.path.join(saida, 'resultado.json'), 'w') as f:
            json.dump(resultado, f, indent=2)
        M.fechar(env)


if __name__ == '__main__':
    main()
