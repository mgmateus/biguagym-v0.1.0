"""Confere no simulador os obstáculos feitos de torpedos do GotoEnv (spec hydrone-goto-dique, T10/T11).

Para cada cenário (``--cenario``, padrão os dois):
1. Abre o ``GotoEnv`` com câmeras, LiDAR de 360 lasers e câmera de profundidade a mais no Hydrone e faz o reset (que
   posiciona os torpedos): tempo do reset, torpedos fora do lugar e a diferença medida (centro de massa) − imposto por
   orientação.
2. Varredura vertical do LiDAR a 1,5 m de um pilar: onde o laser na direção do pilar bate dá a extensão real da coluna;
   comparada com a geométrica, sugere ``origem_eixo`` para o ``goto_dique.json``.
3. Fotos (RGB e profundidade) do spawn olhando para o centro, no ar e na água, e uma de cima do centro.
4. Anel do LiDAR no spawn (ar e água): cada laser comparado com a distância esperada aos torpedos (raio traçado em Python
   contra as mesmas cápsulas da colisão); por obstáculo, mediana da diferença.
5. Passos/s com ações aleatórias (``--passos``), contando términos por motivo.

Uso (no lab):  python tools/conferir_obstaculos.py [--cenario pilares] [--passos 200]
Saída em ``conferir_obstaculos/<data-hora>/<cenario>/``: fotos e ``resultado.json``.
"""
import argparse
import json
import math
import os
import sys
import time
from collections import Counter

import numpy as np

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
sys.path.insert(0, os.path.join(os.path.dirname(AQUI), 'biguagym'))
import mapear_dique as M  # noqa: E402
import achar_pilares as A  # noqa: E402
from core.goto import GotoEnv, dist_capsulas  # noqa: E402

DIST_VARREDURA = 1.5        # m do eixo do pilar à posição do Hydrone na varredura vertical
LIMIAR_BATIDA = 2.0         # m: o laser bateu no pilar (a parede atrás fica a > 2 m)
Z_SEGURO = 8.0              # m acima da água: acima dos obstáculos, para mover o Hydrone por cima


def raio_capsulas(geo, origem, direcao, d_max, tol=1e-3):
    """Distância ao longo de ``direcao`` até o primeiro torpedo (sphere tracing nas cápsulas) e o índice dele."""
    p0 = np.asarray(origem, dtype=np.float64)
    u = np.asarray(direcao, dtype=np.float64)
    u = u / np.linalg.norm(u)
    t = 0.0
    while t < d_max:
        d, j = dist_capsulas(p0 + t * u, geo)
        if d < tol:
            return t, j
        t += max(d, 5e-3)
    return math.inf, -1


def extensao(zs, dists, limiar=LIMIAR_BATIDA):
    """Menor e maior z em que o laser bateu (distância < limiar); (None, None) se não bateu."""
    zs, dists = np.asarray(zs, dtype=np.float64), np.asarray(dists, dtype=np.float64)
    bateu = np.isfinite(dists) & (dists > 0) & (dists < limiar)
    if not bateu.any():
        return None, None
    return float(zs[bateu].min()), float(zs[bateu].max())


def indice_laser(ang, psi, n):
    """Laser do anel (sentido +1, 0 = frente) na direção ``ang`` com o nariz em ``psi``."""
    return int(round(((ang - psi) % (2 * math.pi)) / (2 * math.pi) * n)) % n


def comparar_anel(geo, lidar, pos, psi, d_max):
    """Por obstáculo: lasers cujo raio esperado bate nele, mediana e maior |medido − esperado|."""
    n = len(lidar)
    por_obst = {}
    for i in range(n):
        ang = psi + 2 * math.pi * i / n
        esp, j = raio_capsulas(geo, pos, [math.cos(ang), math.sin(ang), 0.0], d_max)
        if j < 0:
            continue
        med = float(lidar[i])
        if not (np.isfinite(med) and med > 0):
            med = d_max
        por_obst.setdefault(int(geo['obstaculo'][j]), []).append(med - esp)
    return {k: {'lasers': len(v), 'mediana_dif_m': round(float(np.median(v)), 3),
                'max_abs_dif_m': round(float(np.max(np.abs(v))), 3)} for k, v in sorted(por_obst.items())}


class Conferir(GotoEnv):
    """GotoEnv com câmeras, LiDAR de 360 lasers e profundidade a mais no Hydrone (só para a conferência)."""

    def _build_params(self):
        env_params, obs_params = super()._build_params()
        _id = self._agent_id(env_params, 'robot')
        extras = [s for s in M.sensores(True, 960, 960) if s.get('sensor_name', '').startswith('Camera')]
        env_params['agents'][_id]['sensors'] += extras + [A.LIDAR, A.PROFUNDIDADE]
        return env_params, obs_params


def tick(env, robo_pose=None):
    """Um tick segurando os obstáculos (e o Hydrone em ``robo_pose`` = (posição, yaw graus), parado)."""
    if robo_pose is not None:
        pos, yaw = robo_pose
        env._env.agents['robot-id0'].set_physics_state(pos, [0.0, 0.0, yaw], [0.0] * 3, [0.0] * 3)
    env._segurar_obstaculos()
    raw = env._env.step(env._cmds([0.0] * 4), action_repeat=1)
    return env._unwrap_state(raw)


def mover(env, x, y, z, yaw, agua, espera=4):
    """Leva o Hydrone por cima (sobe no lugar, vai acima do destino, desce) e espera ``espera`` ticks parado."""
    s = tick(env)
    atual = np.asarray(s['RPYDynamicsSensor'], dtype=np.float64).ravel()[6:9]
    for p in ([atual[0], atual[1], agua + Z_SEGURO], [x, y, agua + Z_SEGURO], [x, y, z]):
        s = tick(env, (p, yaw))
    for _ in range(espera):
        s = tick(env, ([x, y, z], yaw))
    return s


def lidar_de(s):
    return np.asarray(s['Lidar'], dtype=np.float64).ravel()


def conferir(cenario, args, saida):
    import cv2
    from explorar_mapa import imagem

    os.makedirs(saida, exist_ok=True)
    res = {'cenario': cenario}
    t0 = time.time()
    env = Conferir(seed=0, cenario=cenario)
    res['abrir_s'] = round(time.time() - t0, 1)
    try:
        geo, cena = env._geo, env._cena
        agua = float(cena['nivel_agua'])
        res['torpedos'] = len(geo['centro'])

        # 1. reset (posicionamento) e deslocamento da origem por orientação
        t0 = time.time()
        env.reset()
        res['reset_s'] = round(time.time() - t0, 2)
        res['fora_do_lugar'] = env._fora_do_lugar().tolist()
        dif = env._posicoes_obstaculos() - geo['imposto']
        grupos = {}
        for j, e in enumerate(np.round(geo['eixo'], 3)):
            grupos.setdefault(str(e.tolist()), []).append(j)
        res['dif_medido_imposto'] = {
            k: {'n': len(v), 'mediana': np.round(np.median(dif[v], axis=0), 3).tolist(),
                'ao_longo_do_eixo': round(float(np.median(dif[v] @ np.asarray(json.loads(k)))), 3)}
            for k, v in grupos.items()}
        print(f"[{cenario}] reset {res['reset_s']} s; fora do lugar: {res['fora_do_lugar']}; "
              f"medido − imposto: {res['dif_medido_imposto']}", flush=True)

        # 2. varredura vertical junto ao primeiro pilar (Hydrone a +x, nariz para −x)
        pil = next(o for o in cena['obstaculos'] if o['tipo'] == 'pilar')
        px, py = pil['xy']
        hx = px + DIST_VARREDURA
        zs, ds = [], []
        mover(env, hx, py, agua + args.z_min, 180.0, agua)
        for z in np.arange(args.z_min, args.z_max + 1e-9, args.dz):
            s = tick(env, ([hx, py, agua + z], 180.0))
            s = tick(env, ([hx, py, agua + z], 180.0))
            r = np.asarray(s['RPYDynamicsSensor'], dtype=np.float64).ravel()
            lid = lidar_de(s)
            i = indice_laser(math.atan2(py - r[7], px - r[6]), math.radians(r[17]), len(lid))
            janela = [lid[(i + k) % len(lid)] for k in range(-2, 3)]
            zs.append(float(r[8] - agua))
            ds.append(float(np.min(janela)))
        z_lo, z_hi = extensao(zs, ds)
        comp, folga = env._agente_obst['comprimento'], env._agente_obst['folga']
        geo_lo = float(pil['base_z'])
        geo_hi = geo_lo + pil['niveis'] * comp + (pil['niveis'] - 1) * folga
        res['varredura'] = {'pilar': [px, py], 'z': zs, 'lidar': ds, 'extensao_medida': [z_lo, z_hi],
                            'extensao_geometrica': [geo_lo, geo_hi]}
        if z_lo is not None:
            desloc = ((z_lo + z_hi) - (geo_lo + geo_hi)) / 2.0
            res['varredura']['deslocamento_vertical_m'] = round(desloc, 3)
            res['origem_eixo_sugerida'] = round(float(env._agente_obst.get('origem_eixo', 0.0)) - desloc, 3)
        print(f"[{cenario}] varredura vertical: coluna medida {z_lo}–{z_hi} m × geométrica {geo_lo}–{geo_hi} m; "
              f"origem_eixo sugerida: {res.get('origem_eixo_sugerida')}", flush=True)

        # 3 e 4. fotos e anel do LiDAR do spawn, olhando para o centro; foto de cima
        sx, sy = cena['spawn'][:2]
        cx, cy = cena['origem']
        yaw = math.degrees(math.atan2(cy - sy, cx - sx))
        for nome, z in (('ar', 2.0), ('agua', -0.5)):
            s = mover(env, sx, sy, agua + z, yaw, agua)
            for sensor in ('CameraFrente', 'CameraTerceira'):
                img = imagem(s.get(sensor))
                if img is not None:
                    cv2.imwrite(os.path.join(saida, f"{nome}_{sensor}.png"), img)
            A.salvar_profundidade(os.path.join(saida, f"{nome}_profundidade.png"), s.get('DepthCamera'))
            r = np.asarray(s['RPYDynamicsSensor'], dtype=np.float64).ravel()
            res[f'lidar_{nome}'] = comparar_anel(geo, lidar_de(s), r[6:9], math.radians(r[17]), A.LIDAR_MAX)
            print(f"[{cenario}] LiDAR {nome} (obstáculo: lasers, mediana e maior |medido − esperado|): "
                  f"{res[f'lidar_{nome}']}", flush=True)
        s = mover(env, cx, cy, agua + args.z_cima, 0.0, agua)
        img = imagem(s.get('CameraBaixo'))
        if img is not None:
            cv2.imwrite(os.path.join(saida, 'cima_CameraBaixo.png'), img)

        # 5. passos/s com ações aleatórias
        rng = np.random.default_rng(0)
        env.reset()
        motivos, t_passos, t_resets = Counter(), 0.0, 0.0
        for _ in range(args.passos):
            t0 = time.time()
            _, _, term, trunc, info = env.step(rng.uniform(-1, 1, 3).astype(np.float32))
            t_passos += time.time() - t0
            if term or trunc:
                motivos[info.get('termination_reason')] += 1
                t0 = time.time()
                env.reset()
                t_resets += time.time() - t0
        res['passos_por_s'] = round(args.passos / t_passos, 2)
        res['resets'] = {'n': sum(motivos.values()), 'tempo_medio_s': round(t_resets / max(sum(motivos.values()), 1), 2)}
        res['terminos'] = dict(motivos)
        print(f"[{cenario}] passos/s: {res['passos_por_s']}; términos: {dict(motivos)}; "
              f"reset médio {res['resets']['tempo_medio_s']} s", flush=True)
    finally:
        with open(os.path.join(saida, 'resultado.json'), 'w') as f:
            json.dump(res, f, indent=2, default=float)
        M.fechar(env._env)
    return res


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--cenario', action='append', choices=['pilares', 'dique'],
                    help='cenário a conferir (repetível; padrão: os dois)')
    ap.add_argument('--passos', type=int, default=200)
    ap.add_argument('--z-min', type=float, default=-2.6, help='varredura vertical: z inicial (relativo à água)')
    ap.add_argument('--z-max', type=float, default=6.8)
    ap.add_argument('--dz', type=float, default=0.2)
    ap.add_argument('--z-cima', type=float, default=12.0, help='altura da foto de cima do centro')
    ap.add_argument('--saida', default=None)
    args = ap.parse_args()
    saida = args.saida or os.path.join(M.REPO, 'conferir_obstaculos', time.strftime('%Y%m%d-%H%M%S'))
    print(f"saída: {saida}", flush=True)
    for cenario in args.cenario or ['pilares', 'dique']:
        conferir(cenario, args, os.path.join(saida, cenario))       # M.fechar lista os processos que sobraram


if __name__ == '__main__':
    main()
