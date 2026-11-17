"""Exploração do mapa com o Hydrone: spawn configurável e câmeras do veículo salvas em PNG.

Serve para escolher onde ficam os pilares e os alvos do Goto (spec hydrone-goto-dique). Usa o BiguaSim direto (sem o
biguagym), com o Hydrone em ``cmd_vel_yaw`` e comando zero, então ele fica parado no ar ou na água.

Uso:
    python tools/explorar_mapa.py --ponto 100,100,2 --ponto 120,95,1.5,90
    python tools/explorar_mapa.py --grade 80,120,80,120,10,2 --giro
    python tools/explorar_mapa.py --ponto 100,100,2 --viewer          # abre a janela do simulador
    python tools/explorar_mapa.py --ponto 100,100,2 --dry-run         # só confere configuração e dinâmica (sem simulador)

``--ponto x,y,z[,yaw]``: coordenadas do mundo em metros e guinada em graus (repetível).
``--grade x0,x1,y0,y1,passo,z``: todos os pontos da grade, na altura z.
``--giro``: em cada ponto, fotos com a guinada + 0, 90, 180 e 270°.

Saída em ``explorar_mapa/<data-hora>/``:
- ``<ponto>_<yaw>_frente.png`` (câmera do veículo, para a frente), ``_baixo.png`` (para baixo) e ``_terceira.png``
  (terceira pessoa, socket Viewport);
- ``pontos.csv``: ponto pedido, posição medida depois de assentar, colisão, contato com a água, obstáculo mais próximo
  (360°, horizontal) e distância até o que estiver embaixo (chão/fundo);
- ``config.json``: o cenário usado (nível de sensores que o BiguaSim aceitou).

Se o BiguaSim recusar a configuração completa, o script mostra o traceback e tenta de novo com menos sensores
(``completo`` → ``sem_medidas`` → ``minimo``); o nível usado fica no CSV e no ``config.json``.
"""
import argparse
import csv
import json
import math
import os
import subprocess
import sys
import time
import traceback

import numpy as np

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATE_JSON = os.path.join(REPO, 'biguagym', 'config', 'state.json')

N_LASERS = 36   # obstáculo mais próximo: 1 laser a cada 10°


EXTRAS = {
    'colisao': {'sensor_type': 'CollisionSensor', 'location': [0, 0, 0], 'rotation': [0, 0, 0]},
    'agua': {'sensor_type': 'WaterCollisionSensor', 'location': [0, 0, 0], 'rotation': [0, 0, 0]},
    'distancias': {'sensor_name': 'Distancias', 'sensor_type': 'RangeFinderSensor', 'socket': 'IMUSocket',
                   'configuration': {'LaserMaxDistance': 30, 'LaserCount': N_LASERS, 'LaserAngle': 0, 'LaserDebug': False}},
    'fundo': {'sensor_name': 'Fundo', 'sensor_type': 'RangeFinderSensor', 'socket': 'IMUSocket',
              'configuration': {'LaserMaxDistance': 50, 'LaserCount': 1, 'LaserAngle': -90, 'LaserDebug': False}},
}
EXTRAS_PADRAO = 'colisao,distancias,fundo'


def sensores(nivel: str, largura: int, altura: int, extras: str = EXTRAS_PADRAO) -> list:
    """Sensores do Hydrone. ``minimo`` = os do state.json do biguagym (já abriram o Hydrone no lab)."""
    base = [
        {'sensor_type': 'DynamicsSensor', 'socket': 'IMUSocket',
         'configuration': {'UseCOM': True, 'UseRPY': False}, 'location': [0, 0, 0], 'rotation': [0, 0, 0]},
        {'sensor_name': 'RPYDynamicsSensor', 'sensor_type': 'DynamicsSensor', 'socket': 'IMUSocket',
         'configuration': {'UseCOM': False, 'UseRPY': True}, 'location': [0, 0, 0], 'rotation': [0, 0, 0]},
        {'sensor_name': 'CameraTerceira', 'sensor_type': 'RGBCamera', 'socket': 'Viewport',
         'configuration': {'CaptureWidth': largura, 'CaptureHeight': altura}, 'location': [0, 0, 0], 'rotation': [0, 0, 0]},
    ]
    if nivel == 'minimo':
        return base
    # Câmeras presas ao corpo (sem socket: o Hydrone não documenta um socket de câmera; um nome inválido derruba o spawn)
    base += [
        {'sensor_name': 'CameraFrente', 'sensor_type': 'RGBCamera',
         'configuration': {'CaptureWidth': largura, 'CaptureHeight': altura}, 'location': [0.35, 0, 0.05], 'rotation': [0, 0, 0]},
        {'sensor_name': 'CameraBaixo', 'sensor_type': 'RGBCamera',
         'configuration': {'CaptureWidth': largura, 'CaptureHeight': altura}, 'location': [0, 0, -0.1], 'rotation': [0, -90, 0]},
    ]
    if nivel == 'sem_medidas':
        return base
    return base + [EXTRAS[e] for e in extras.split(',') if e]


NIVEIS = ('completo', 'sem_medidas', 'minimo')


def cenario(nivel, ponto, args) -> dict:
    with open(STATE_JSON) as f:
        base = json.load(f)
    cfg = {k: v for k, v in base.items() if k != 'agents'}
    if args.mundo:
        cfg['world'] = args.mundo
    if args.pacote:
        cfg['package_name'] = args.pacote
    cfg['agents'] = [{
        'agent_name': 'robot',
        'agent_type': 'Hydrone',
        'control_abstraction': 'cmd_vel_yaw',
        'dynamics': {'batch_size': 1, 'water_level': float(args.agua)},
        'location': [float(v) for v in ponto[:3]],
        'rotation': [0.0, 0.0, float(ponto[3])],
        'sensors': sensores(nivel, args.largura, args.altura, args.extras),
    }]
    return cfg


def ler_pontos(args) -> list:
    pontos = []
    for p in args.ponto:
        v = [float(x) for x in p.split(',')]
        if len(v) not in (3, 4):
            raise SystemExit(f"--ponto {p!r}: use x,y,z ou x,y,z,yaw")
        pontos.append(v if len(v) == 4 else v + [0.0])
    if args.grade:
        x0, x1, y0, y1, passo, z = [float(x) for x in args.grade.split(',')]
        for x in np.arange(x0, x1 + 1e-9, passo):
            for y in np.arange(y0, y1 + 1e-9, passo):
                pontos.append([float(x), float(y), z, 0.0])
    if not pontos:
        raise SystemExit("informe ao menos um --ponto ou uma --grade")
    return pontos


def plano(state) -> dict:
    """Estado de um agente só, nos formatos da 1.0.0 ({'robot': [ {...} ]}) e da 1.1.0."""
    if isinstance(state, dict):
        for k, v in state.items():
            if k.startswith('robot'):
                if isinstance(v, list) and v and isinstance(v[0], dict):
                    return v[0]
                if isinstance(v, dict):
                    return v
    return state


def imagem(raw):
    if raw is None:
        return None
    a = np.asarray(raw)
    if a.ndim == 4 and a.shape[0] == 1:
        a = a[0]
    if a.ndim != 3 or a.shape[2] < 3:
        return None
    return np.ascontiguousarray(a[:, :, :3]).astype(np.uint8)


def medir(s: dict) -> dict:
    out = {}
    rpy = s.get('RPYDynamicsSensor')
    if rpy is not None:
        d = np.asarray(rpy, dtype=float).ravel()
        out.update(x=d[6], y=d[7], z=d[8], roll=d[15], pitch=d[16], yaw=d[17])
    if s.get('CollisionSensor') is not None:
        out['colisao'] = bool(np.any(np.asarray(s['CollisionSensor'])))
    if s.get('WaterCollisionSensor') is not None:
        out['na_agua'] = bool(np.asarray(s['WaterCollisionSensor']).ravel()[0])
    dist = s.get('Distancias')
    if dist is not None:
        dist = np.asarray(dist, dtype=float).ravel()
        i = int(np.argmin(dist))
        out['obstaculo_m'] = float(dist[i])
        out['obstaculo_dir_deg'] = round(360.0 * i / len(dist), 1)   # 0 = frente; sentido a confirmar no simulador
    fundo = s.get('Fundo')
    if fundo is not None:
        out['abaixo_m'] = float(np.asarray(fundo, dtype=float).ravel()[0])
    return out


def processos_simulador() -> list:
    r = subprocess.run(['ps', 'aux'], capture_output=True, text=True)
    return [ln for ln in r.stdout.splitlines()
            if any(k in ln.lower() for k in ('biguasim', 'holodeck', 'unreal'))
            and 'grep' not in ln and 'explorar_mapa' not in ln]


def dry_run(pontos, args) -> int:
    """Sem simulador: configuração serializável e um passo da dinâmica do Hydrone (cmd_vel_yaw, comando zero) em cada ponto."""
    import torch
    from biguasim.dynamics.agents import ModelsFactory
    modelo = ModelsFactory.build_model('Hydrone')
    for nivel in NIVEIS:
        json.dumps(cenario(nivel, pontos[0], args))
    params = modelo._params.copy()
    params['water_level'] = float(args.agua)
    m = modelo(batch_size=1, device=torch.device('cpu'), control_abstraction='cmd_vel_yaw', params=params)
    m.dt = 1.0 / 20
    erros = 0
    for p in pontos:
        s = np.zeros(19)
        s[6:9] = p[:3]
        s[18] = 1.0
        acc = np.asarray(m.step([s], [[0.0, 0.0, 0.0, 0.0]]), dtype=float)
        ok = bool(np.all(np.isfinite(acc)))
        erros += not ok
        meio = 'água' if p[2] < args.agua else 'ar'
        print(f"ponto {p}: {meio}, aceleração com comando zero = {np.round(acc.ravel(), 3).tolist()} "
              f"{'ok' if ok else 'NaN/inf!'}")
    print(f"dry-run: {len(pontos)} pontos, {erros} com erro; configuração dos níveis {NIVEIS} serializável")
    return 1 if erros else 0


def abrir(pontos, args):
    import biguasim
    for nivel in NIVEIS:
        cfg = cenario(nivel, pontos[0], args)
        try:
            env = biguasim.make(scenario_cfg=cfg, show_viewport=args.viewer)
            env.reset()
            print(f"Hydrone criado com o nível de sensores {nivel!r}", flush=True)
            return env, nivel, cfg
        except Exception:
            print(f"--- o BiguaSim recusou o nível {nivel!r}:", flush=True)
            traceback.print_exc()
            restantes = processos_simulador()
            if restantes:
                print(f"    atenção: {len(restantes)} processo(s) do simulador ainda abertos depois da falha", flush=True)
    raise SystemExit("o Hydrone não abriu em nenhum nível de sensores; veja os tracebacks acima")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--ponto', action='append', default=[], help='x,y,z[,yaw] (repetível)')
    ap.add_argument('--grade', help='x0,x1,y0,y1,passo,z')
    ap.add_argument('--giro', action='store_true', help='4 guinadas por ponto (0, 90, 180, 270° a mais)')
    ap.add_argument('--extras', default=EXTRAS_PADRAO,
                    help=f"sensores de medida do nível completo, entre {sorted(EXTRAS)} (padrão: {EXTRAS_PADRAO}; "
                         "o WaterCollisionSensor ficou fora porque travou o spawn no lab)")
    ap.add_argument('--espera', type=int, default=20, help='ticks para assentar em cada ponto (20 = 1 s)')
    ap.add_argument('--agua', type=float, default=0.0, help='nível da água para a dinâmica (m)')
    ap.add_argument('--largura', type=int, default=640)
    ap.add_argument('--altura', type=int, default=480)
    ap.add_argument('--mundo', default=None, help='padrão: o do state.json (Pier-Harbor)')
    ap.add_argument('--pacote', default=None, help='padrão: o do state.json (SkyDive)')
    ap.add_argument('--saida', default=None)
    ap.add_argument('--viewer', action='store_true', help='abre a janela do simulador')
    ap.add_argument('--dry-run', action='store_true', help='não abre o simulador')
    args = ap.parse_args()

    pontos = ler_pontos(args)
    if args.dry_run:
        sys.exit(dry_run(pontos, args))

    saida = args.saida or os.path.join(REPO, 'explorar_mapa', time.strftime('%Y%m%d-%H%M%S'))
    os.makedirs(saida, exist_ok=True)
    import cv2

    env, nivel, cfg = abrir(pontos, args)
    with open(os.path.join(saida, 'config.json'), 'w') as f:
        json.dump({'nivel_sensores': nivel, 'cenario': cfg}, f, indent=2)
    agente = next(v for k, v in env.agents.items() if k.startswith('robot'))
    zero = [0.0, 0.0, 0.0, 0.0]
    linhas = []
    try:
        for i, p in enumerate(pontos):
            giros = (0, 90, 180, 270) if args.giro else (0,)
            for g in giros:
                yaw = p[3] + g
                agente.set_physics_state(p[:3], [0.0, 0.0, yaw], [0.0, 0.0, 0.0], [0.0, 0.0, 0.0])
                colidiu = False
                for _ in range(max(1, args.espera)):
                    s = plano(env.step(zero))
                    colidiu |= bool(medir(s).get('colisao', False))
                nome = f"p{i:03d}_{p[0]:.1f}_{p[1]:.1f}_{p[2]:.1f}_yaw{yaw:.0f}"
                arquivos = []
                for sensor, sufixo in (('CameraFrente', 'frente'), ('CameraBaixo', 'baixo'), ('CameraTerceira', 'terceira')):
                    img = imagem(s.get(sensor))
                    if img is not None:
                        arq = f"{nome}_{sufixo}.png"
                        cv2.imwrite(os.path.join(saida, arq), img)
                        arquivos.append(arq)
                m = medir(s)
                linha = {'ponto': i, 'x_pedido': p[0], 'y_pedido': p[1], 'z_pedido': p[2], 'yaw_pedido': yaw,
                         **{k: (round(v, 3) if isinstance(v, float) else v) for k, v in m.items()},
                         'colidiu_ao_assentar': colidiu, 'nivel_sensores': nivel, 'arquivos': ' '.join(arquivos)}
                linhas.append(linha)
                print(json.dumps(linha, ensure_ascii=False), flush=True)
    finally:
        if linhas:
            campos = list(dict.fromkeys(k for ln in linhas for k in ln))
            with open(os.path.join(saida, 'pontos.csv'), 'w', newline='') as f:
                w = csv.DictWriter(f, fieldnames=campos)
                w.writeheader()
                w.writerows(linhas)
        if hasattr(env, '__on_exit__'):
            env.__on_exit__()
        del env
        time.sleep(2)
        restantes = processos_simulador()
        print(f"saída: {saida}  ({len(linhas)} fotos/pontos)")
        print(f"processos do simulador depois de fechar: {len(restantes)}")
        for ln in restantes:
            print('   ', ln[:160])


if __name__ == '__main__':
    main()
