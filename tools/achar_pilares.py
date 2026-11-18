"""Procura estruturas parecidas com pilares que já existem no Pier-Harbor (spec hydrone-goto-dique, T8).

Por quê: o motor do mundo SkyDive (1.0.0 e 1.1.0) não conhece o comando ``SpawnProp`` (log: ``CommandFactory failed to make
command:  SpawnProp``), então os pilares do Goto criados por ``spawn_prop`` nunca aparecem. O motor só registra
SpawnAgent, DebugDraw, TeleportCamera, Add/Remove/RotateSensor, RenderViewport, RGBCameraRate, AdjustRenderQuality,
CustomCommand e as mensagens acústica/óptica (``strings`` do binário). Sobra usar o que já está no mapa.

Como (BiguaSim direto, Hydrone em ``accel`` com aceleração zero, teleportado; nada é alterado):
1. **Mapa de alturas** da região com o laser para baixo (como o ``mapear_dique.py``) → onde há água.
2. **Fatias de LiDAR**: o Hydrone é posto em pontos de água perto de alguma estrutura (``--grade``), abaixo e acima da
   água (``--z``), com 360 lasers horizontais; os impactos viram uma nuvem de pontos por altura. O sentido dos lasers
   (horário ou anti-horário a partir da frente) é escolhido pela nuvem mais nítida (paredes vistas de vários pontos
   coincidem só no sentido certo).
3. **Pilares**: grupos de impactos pequenos (até ``--diam-max``) e isolados (nada a menos de ``--isolamento``) que aparecem
   nas duas fatias no mesmo lugar, ou seja, atravessam a superfície. Pilares a menos de ``--raio-grupo`` uns dos outros
   formam grupos; os grupos com 4 ou mais são candidatos ao cenário do Goto.
4. **Fotos** de cada grupo (do ponto de água mais próximo, olhando para ele, no ar e na água) e **teste do DebugDraw**:
   caixas desenhadas nas coordenadas sugeridas no dique, fotografadas com a câmera RGB e a de profundidade, para saber
   se o desenho de depuração aparece nas observações.

Uso (no lab, na raiz do repositório):
    python tools/achar_pilares.py                          # porto inteiro
    python tools/achar_pilares.py --regiao 100,200,-280,-90 --grade 8
    python tools/achar_pilares.py --dry-run                # cenário sintético, sem simulador

Saída em ``achar_pilares/<data-hora>/``: ``mapa.png`` (alturas, nuvens e pilares), ``pilares.csv``, ``grupos.json``,
``leituras.npz``, ``resumo.txt`` e as fotos.
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

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mapear_dique as M  # noqa: E402

REPO = M.REPO
REGIAO_PADRAO = (-170.0, 280.0, -290.0, 50.0)     # o porto inteiro (vista de cima da documentação) e um pouco de mar
N_LIDAR = 360
LIDAR_MAX = 40.0
LIDAR = {'sensor_name': 'Lidar', 'sensor_type': 'RangeFinderSensor', 'socket': 'IMUSocket',
         'configuration': {'LaserMaxDistance': LIDAR_MAX, 'LaserCount': N_LIDAR, 'LaserAngle': 0, 'LaserDebug': False}}
PROFUNDIDADE = {'sensor_name': 'DepthCamera', 'sensor_type': 'DepthCamera',
                'configuration': {'CaptureWidth': 512, 'CaptureHeight': 512}, 'location': [0.35, 0, 0.05],
                'rotation': [0, 0, 0]}
DIQUE_PILARES = [(129.4, -152.0), (129.4, -148.0), (132.6, -152.0), (132.6, -148.0)]   # mapear_dique, 2026-11-18
DIQUE_SPAWN = (133.88, -152.6)


# ----------------------------------------------------------------------------------------------------------------------
# Análise (sem simulador)
# ----------------------------------------------------------------------------------------------------------------------
def nuvem(leituras, sinal, d_min=0.3, d_max=LIDAR_MAX):
    """Pontos [x, y] dos impactos. ``leituras``: lista de (x, y, guinada em rad, distâncias). O laser i aponta para
    guinada + sinal·2πi/N (i = 0 é a frente)."""
    pts = []
    for x, y, psi, d in leituras:
        d = np.asarray(d, dtype=float)
        ang = psi + sinal * 2.0 * np.pi * np.arange(len(d)) / len(d)
        ok = (d > d_min) & (d < d_max - 1e-3)
        pts.append(np.stack([x + d[ok] * np.cos(ang[ok]), y + d[ok] * np.sin(ang[ok])], -1))
    return np.concatenate(pts) if pts else np.zeros((0, 2))


def nitidez(pts, cel=0.25):
    """Células ocupadas pela nuvem (menos = mais nítida: as mesmas paredes vistas de vários pontos coincidem)."""
    return len(np.unique(np.floor(pts / cel).astype(np.int64), axis=0)) if len(pts) else 0


def escolher_sinal(leituras):
    n = {s: nitidez(nuvem(leituras, s)) for s in (1, -1)}
    return min(n, key=n.get), n


def ocupacao(pts, regiao, cel):
    x0, x1, y0, y1 = regiao
    nx, ny = int(math.ceil((x1 - x0) / cel)), int(math.ceil((y1 - y0) / cel))
    g = np.zeros((ny, nx), dtype=np.int32)
    ix = np.floor((pts[:, 0] - x0) / cel).astype(int)
    iy = np.floor((pts[:, 1] - y0) / cel).astype(int)
    ok = (ix >= 0) & (ix < nx) & (iy >= 0) & (iy < ny)
    np.add.at(g, (iy[ok], ix[ok]), 1)
    return g


def candidatos(pts, regiao, cel=0.25, diam_max=2.5, isolamento=1.5, min_pts=3):
    """Grupos de impactos pequenos e isolados: [(x, y, diâmetro aparente, n impactos)]."""
    from scipy import ndimage
    g = ocupacao(pts, regiao, cel)
    occ = g > 0
    rot, n = ndimage.label(occ, structure=np.ones((3, 3)))
    if n == 0:
        return []
    r_iso = int(math.ceil(isolamento / cel))
    disco = np.hypot(*np.mgrid[-r_iso:r_iso + 1, -r_iso:r_iso + 1]) <= r_iso
    saida = []
    for k, sl in enumerate(ndimage.find_objects(rot), start=1):
        m = rot[sl] == k
        hy, hx = (sl[0].stop - sl[0].start) * cel, (sl[1].stop - sl[1].start) * cel
        npts = int(g[sl][m].sum())
        if math.hypot(hx, hy) > diam_max or npts < min_pts:
            continue
        y0, x0 = max(sl[0].start - r_iso, 0), max(sl[1].start - r_iso, 0)
        y1, x1 = min(sl[0].stop + r_iso, occ.shape[0]), min(sl[1].stop + r_iso, occ.shape[1])
        janela = rot[y0:y1, x0:x1]
        perto = ndimage.binary_dilation(janela == k, structure=disco)
        if np.any(perto & (janela != k) & (janela > 0)):
            continue                                          # outra estrutura perto: parede, casco, cais
        ky, kx = np.nonzero(m)
        cx = regiao[0] + (sl[1].start + kx.mean() + 0.5) * cel
        cy = regiao[2] + (sl[0].start + ky.mean() + 0.5) * cel
        saida.append((round(float(cx), 2), round(float(cy), 2), round(math.hypot(hx, hy), 2), npts))
    return saida


def casar(agua, ar, tol=0.75):
    """Candidatos que aparecem abaixo e acima da água no mesmo lugar (atravessam a superfície)."""
    pilares = []
    for xa, ya, da, na in agua:
        dist = [math.hypot(xa - xb, ya - yb) for xb, yb, _, _ in ar]
        if dist and min(dist) <= tol:
            xb, yb, db, nb = ar[int(np.argmin(dist))]
            pilares.append({'x': round((xa + xb) / 2, 2), 'y': round((ya + yb) / 2, 2),
                            'diam_agua': da, 'diam_ar': db, 'impactos': na + nb})
    return pilares


def agrupar(pilares, raio=15.0):
    """Grupos de pilares ligados por distâncias até ``raio``, do maior para o menor."""
    n = len(pilares)
    pai = list(range(n))

    def raiz(i):
        while pai[i] != i:
            pai[i] = pai[pai[i]]
            i = pai[i]
        return i
    for i in range(n):
        for j in range(i + 1, n):
            if math.hypot(pilares[i]['x'] - pilares[j]['x'], pilares[i]['y'] - pilares[j]['y']) <= raio:
                pai[raiz(i)] = raiz(j)
    grupos = {}
    for i in range(n):
        grupos.setdefault(raiz(i), []).append(pilares[i])
    saida = []
    for g in sorted(grupos.values(), key=len, reverse=True):
        xs, ys = [p['x'] for p in g], [p['y'] for p in g]
        saida.append({'n': len(g), 'centro': [round(float(np.mean(xs)), 2), round(float(np.mean(ys)), 2)],
                      'caixa': [[min(xs), min(ys)], [max(xs), max(ys)]], 'pilares': g})
    return saida


def pontos_lidar(agua, xs, ys, passo, grade, dist_min=2.0, dist_max=LIDAR_MAX - 5):
    """Pontos de água numa grade de ``grade`` m, a pelo menos ``dist_min`` e no máximo ``dist_max`` do sólido mais
    próximo (no mar aberto longe de tudo os lasers não veem nada)."""
    from scipy import ndimage
    d = ndimage.distance_transform_edt(agua) * passo
    k = max(1, int(round(grade / passo)))
    pts = []
    for iy in range(0, len(ys), k):
        for ix in range(0, len(xs), k):
            if agua[iy, ix] and dist_min <= d[iy, ix] <= dist_max:
                pts.append((float(xs[ix]), float(ys[iy])))
    return pts


def sintetico(sinal=1):
    """Cenário de teste: cais (x < 0), 4 pilares de 0,6 m em água aberta e um poste isolado só acima da água; leituras
    de LiDAR geradas por traçado de raios simples."""
    pilares = [(10.0, 10.0), (10.0, 16.0), (16.0, 10.0), (16.0, 16.0)]
    poste_ar = (25.0, 5.0)

    def ler(x, y, ar):
        d = np.full(N_LIDAR, LIDAR_MAX)
        ang = sinal * 2 * np.pi * np.arange(N_LIDAR) / N_LIDAR
        c, s = np.cos(ang), np.sin(ang)
        with np.errstate(divide='ignore', invalid='ignore'):
            t = np.where(c < 0, (0.0 - x) / c, np.inf)        # parede do cais em x = 0
        d = np.minimum(d, np.where(t > 0, t, np.inf))
        for px, py in pilares + ([poste_ar] if ar else []):
            fx, fy = px - x, py - y
            b = fx * c + fy * s
            disc = b * b - (fx * fx + fy * fy - 0.3 ** 2)
            tt = np.where((disc >= 0) & (b > 0), b - np.sqrt(np.maximum(disc, 0)), np.inf)
            d = np.minimum(d, tt)
        return d
    locais = [(x, y) for x in (4.0, 13.0, 22.0, 30.0) for y in (2.0, 13.0, 24.0)]
    return ({z: [(x, y, 0.0, ler(x, y, z > 0)) for x, y in locais] for z in (-0.7, 2.0)}, pilares, poste_ar)


# ----------------------------------------------------------------------------------------------------------------------
# Simulador
# ----------------------------------------------------------------------------------------------------------------------
def fatias(env, agente, pontos, zs, nivel_agua):
    leituras = {z: [] for z in zs}
    t0 = time.time()
    for i, (x, y) in enumerate(pontos):
        for z in zs:
            _, s, _ = M.ir(env, agente, x, y, nivel_agua + z, ticks=2)
            rpy = np.asarray(s['RPYDynamicsSensor'], dtype=float).ravel()
            leituras[z].append((float(rpy[6]), float(rpy[7]), math.radians(float(rpy[17])),
                                np.asarray(s['Lidar'], dtype=float).ravel()))
        if (i + 1) % 50 == 0:
            print(f"   LiDAR: {i + 1}/{len(pontos)} pontos, {(i + 1) / (time.time() - t0):.1f} pontos/s", flush=True)
    return leituras


def salvar_profundidade(caminho, raw):
    import cv2
    if raw is None:
        return
    d = np.asarray(raw['depth_map'] if isinstance(raw, dict) else raw, dtype=np.float32)
    d = np.squeeze(d)
    if d.ndim == 3:
        d = d[..., 0]
    d = np.where(np.isfinite(d), d, 20.0)
    cv2.imwrite(caminho, (np.clip(d, 0, 20.0) * (255 / 20.0)).astype(np.uint8))


def fotos(args, grupos, pontos, saida):
    """Fotos de cada grupo (do ponto de água mais próximo) e o teste do DebugDraw no dique."""
    import cv2
    from explorar_mapa import imagem, plano
    agua = float(args.agua)
    env, agente = M.abrir([DIQUE_SPAWN[0], DIQUE_SPAWN[1], agua + 2.0], args, com_cameras=True, extras=[PROFUNDIDADE])
    try:
        def foto(nome, x, y, z, alvo):
            yaw = math.degrees(math.atan2(alvo[1] - y, alvo[0] - x))
            M.ir(env, agente, x, y, z, yaw)
            for _ in range(15):
                s = plano(env.step(M.ZERO))
            for sensor in ('CameraFrente', 'CameraTerceira'):
                img = imagem(s.get(sensor))
                if img is not None:
                    cv2.imwrite(os.path.join(saida, f"{nome}_{sensor}.png"), img)
            salvar_profundidade(os.path.join(saida, f"{nome}_profundidade.png"), s.get('DepthCamera'))

        # DebugDraw: caixas de 1 × 1 × 8 m nos pilares sugeridos do dique, persistentes
        for px, py in DIQUE_PILARES:
            env.draw_box([px, py, agua + 1.0], [0.5, 0.5, 4.0], color=[255, 60, 0], thickness=30.0, lifetime=0)
        centro = (sum(p[0] for p in DIQUE_PILARES) / 4, sum(p[1] for p in DIQUE_PILARES) / 4)
        foto('debugdraw_dique_ar', DIQUE_SPAWN[0] + 3, DIQUE_SPAWN[1] - 2, agua + 2.0, centro)
        foto('debugdraw_dique_agua', DIQUE_SPAWN[0] + 3, DIQUE_SPAWN[1] - 2, agua - 0.5, centro)
        print("   fotos do teste do DebugDraw no dique", flush=True)

        for k, g in enumerate(grupos[:args.fotos_grupos]):
            cx, cy = g['centro']
            px, py = min(pontos, key=lambda p: math.hypot(p[0] - cx, p[1] - cy))
            if math.hypot(px - cx, py - cy) < 4.0:              # perto demais: recua 8 m na direção do ponto
                ang = math.atan2(py - cy, px - cx)
                px, py = cx + 8.0 * math.cos(ang), cy + 8.0 * math.sin(ang)
            foto(f"grupo{k}_ar", px, py, agua + 2.0, (cx, cy))
            foto(f"grupo{k}_agua", px, py, agua - 0.5, (cx, cy))
            print(f"   fotos do grupo {k} ({g['n']} pilares em {g['centro']}) a partir de ({px:.1f}, {py:.1f})", flush=True)
    finally:
        M.fechar(env)


def desenhar(caminho, topo, xs, ys, agua, nivel_agua, nuvens, pilares, grupos, regiao, px_por_m=2.0):
    import cv2
    M.desenhar(caminho, topo, xs, ys, agua, nivel_agua, px_max=int((regiao[3] - regiao[2]) * px_por_m))
    img = cv2.imread(caminho)
    passo = float(xs[1] - xs[0])
    esc = max(1, int(int((regiao[3] - regiao[2]) * px_por_m) / max(topo.shape)))
    m = 60

    def px(x, y):
        return (int(m + ((x - xs[0]) / passo + 0.5) * esc), int(m + ((ys[-1] - y) / passo + 0.5) * esc))
    for z, pts, cor in nuvens:
        for x, y in pts[::max(1, len(pts) // 60000)]:
            p = px(x, y)
            if 0 <= p[0] < img.shape[1] and 0 <= p[1] < img.shape[0]:
                img[p[1], p[0]] = cor
    for p in pilares:
        cv2.circle(img, px(p['x'], p['y']), 6, (0, 200, 0), 2)
    for k, g in enumerate(grupos):
        if g['n'] >= 4:
            (x0, y0), (x1, y1) = g['caixa']
            cv2.rectangle(img, px(x0 - 2, y0 - 2), px(x1 + 2, y1 + 2), (0, 220, 255), 2)
            cv2.putText(img, f"g{k}:{g['n']}", px(x0 - 2, y1 + 3), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 1)
    cv2.putText(img, "pontos LiDAR: azul = abaixo da agua, vermelho = acima; verde: pilares; amarelo: grupos >= 4",
                (m, img.shape[0] - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 0, 0), 1)
    cv2.imwrite(caminho, img)


# ----------------------------------------------------------------------------------------------------------------------
def analisar(leituras, regiao, args):
    sinal, notas = escolher_sinal([l for z in leituras for l in leituras[z]])
    por_z = {z: candidatos(nuvem(leituras[z], sinal), regiao, args.celula, args.diam_max, args.isolamento)
             for z in leituras}
    z_agua = [z for z in leituras if z < 0]
    z_ar = [z for z in leituras if z >= 0]
    pilares = casar(por_z[z_agua[0]], por_z[z_ar[0]]) if z_agua and z_ar else []
    return sinal, notas, por_z, pilares, agrupar(pilares, args.raio_grupo)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--regiao', default=','.join(str(v) for v in REGIAO_PADRAO), help='x0,x1,y0,y1')
    ap.add_argument('--passo', type=float, default=6.0, help='passo do mapa de alturas (m)')
    ap.add_argument('--grade', type=float, default=12.0, help='espaçamento dos pontos de LiDAR na água (m)')
    ap.add_argument('--z', default='-0.7,2.0', help='alturas das fatias, relativas à água (uma abaixo e uma acima)')
    ap.add_argument('--z-varredura', type=float, default=40.0)
    ap.add_argument('--agua', type=float, default=0.0)
    ap.add_argument('--limiar-agua', type=float, default=0.5)
    ap.add_argument('--celula', type=float, default=0.25, help='célula da grade de ocupação (m)')
    ap.add_argument('--diam-max', type=float, default=2.5, help='maior diâmetro aparente de um pilar (m)')
    ap.add_argument('--isolamento', type=float, default=1.5, help='nada a menos disto em volta de um pilar (m)')
    ap.add_argument('--raio-grupo', type=float, default=15.0)
    ap.add_argument('--fotos-grupos', type=int, default=6, help='quantos grupos fotografar')
    ap.add_argument('--sem-fotos', action='store_true')
    ap.add_argument('--saida', default=None)
    ap.add_argument('--dry-run', action='store_true')
    args = ap.parse_args()

    regiao = tuple(float(v) for v in args.regiao.split(','))
    zs = [float(v) for v in args.z.split(',')]
    saida = args.saida or os.path.join(REPO, 'achar_pilares', time.strftime('%Y%m%d-%H%M%S') + ('_dry' if args.dry_run else ''))
    os.makedirs(saida, exist_ok=True)
    print(f"saída: {saida}", flush=True)

    if args.dry_run:
        leituras, _, _ = sintetico(sinal=-1)
        reg = (-5.0, 40.0, -5.0, 30.0)
        sinal, notas, por_z, pilares, grupos = analisar(leituras, reg, args)
        print(f"sentido dos lasers: {sinal:+d} (células ocupadas por sentido: {notas})")
        print(f"candidatos por altura: { {z: len(c) for z, c in por_z.items()} }; pilares: {pilares}")
        print(f"grupos: {[(g['n'], g['centro']) for g in grupos]}")
        return 0

    env = None
    try:
        env, agente = M.abrir([regiao[0], regiao[2], args.z_varredura], args, com_cameras=False, extras=[LIDAR])
        print("== mapa de alturas", flush=True)
        xs, ys = M.grade(regiao, args.passo)
        topo, _ = M.varrer(env, agente, xs, ys, args.z_varredura, 'alturas')
        agua = M.classificar(topo, args.agua, args.limiar_agua)
        pontos = pontos_lidar(agua, xs, ys, args.passo, args.grade)
        print(f"== fatias de LiDAR em {len(pontos)} pontos de água, z = {zs}", flush=True)
        leituras = fatias(env, agente, pontos, zs, args.agua)
    except Exception:
        traceback.print_exc()
        raise
    finally:
        if env is not None:
            M.fechar(env)

    np.savez_compressed(os.path.join(saida, 'leituras.npz'), xs=xs, ys=ys, topo=topo, pontos=np.asarray(pontos),
                        **{f"z{z:+.1f}": np.asarray([np.concatenate([[x, y, p], d]) for x, y, p, d in leituras[z]])
                           for z in zs})
    sinal, notas, por_z, pilares, grupos = analisar(leituras, regiao, args)
    nuvens = [(z, nuvem(leituras[z], sinal), (200, 80, 0) if z < 0 else (0, 0, 220)) for z in zs]
    desenhar(os.path.join(saida, 'mapa.png'), topo, xs, ys, agua, args.agua, nuvens, pilares, grupos, regiao)
    with open(os.path.join(saida, 'pilares.csv'), 'w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=['x', 'y', 'diam_agua', 'diam_ar', 'impactos'])
        w.writeheader()
        w.writerows(pilares)
    with open(os.path.join(saida, 'grupos.json'), 'w') as f:
        json.dump({'sentido_lasers': sinal, 'celulas_por_sentido': notas, 'grupos': grupos}, f, indent=2)
    resumo = [f"sentido dos lasers: {sinal:+d} (células ocupadas: {notas})",
              f"pontos de LiDAR: {len(pontos)}; candidatos por altura: { {z: len(c) for z, c in por_z.items()} }",
              f"pilares (abaixo e acima da água): {len(pilares)}",
              *[f"grupo {k}: {g['n']} pilares, centro {g['centro']}, caixa {g['caixa']}" for k, g in enumerate(grupos[:12])]]
    with open(os.path.join(saida, 'resumo.txt'), 'w') as f:
        f.write('\n'.join(resumo) + '\n')
    print('== resumo\n' + '\n'.join(resumo), flush=True)

    if not args.sem_fotos:
        print("== fotos", flush=True)
        fotos(args, grupos, pontos, saida)
    return 0


if __name__ == '__main__':
    sys.exit(main())
