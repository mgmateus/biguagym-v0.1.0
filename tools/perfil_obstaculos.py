"""Custo dos obstáculos feitos de torpedos no passo do GotoEnv (spec hydrone-goto-dique, T11).

No lab (2026-11-18), 48 torpedos derrubaram o passo para 3,96 passos/s (com câmeras extras) e 66 estouraram o limite de
arquivos abertos. Aqui: passos/s do ``GotoEnv`` (-v0, sem câmeras) com 0, 12 (1 torpedo por nível) e 48 (2 × 2) torpedos,
segurando a cada tick ou a cada ``--segurar-cada`` ticks, e um cProfile do caso mais pesado (tempo no Python × esperando
o motor em ``acquire``).

Uso (no lab):  python tools/perfil_obstaculos.py [--passos 100]
"""
import argparse
import cProfile
import io
import os
import pstats
import resource
import sys
import time

import numpy as np

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
sys.path.insert(0, os.path.join(os.path.dirname(AQUI), 'biguagym'))
import mapear_dique as M  # noqa: E402
from core.goto import GotoEnv, geometria_obstaculos  # noqa: E402

PILARES = [(129.4, -152.0), (129.4, -148.0), (132.6, -152.0), (132.6, -148.0)]


class Perfil(GotoEnv):
    FEIXE = 1
    COM_OBSTACULOS = True
    SEGURAR_CADA = 1

    def _preparar_cenario(self, cenario):
        super()._preparar_cenario(cenario)
        obst = [{'tipo': 'pilar', 'xy': list(p), 'feixe': self.FEIXE, 'niveis': 3, 'base_z': -1.2} for p in PILARES]
        self._cena = dict(self._cena, obstaculos=obst if self.COM_OBSTACULOS else [])
        self._geo = geometria_obstaculos(self._cena, self._agente_obst)
        self._obst_ponto = self._geo['imposto'].copy()
        self._ticks_seg = 0

    def _segurar_obstaculos(self, teleporte=False):
        self._ticks_seg += 1
        if teleporte or self._ticks_seg % self.SEGURAR_CADA == 0:      # no posicionamento, sempre
            super()._segurar_obstaculos(teleporte)


def medir(nome, passos, perfil=False, **attrs):
    cls = type(nome, (Perfil,), attrs)
    t0 = time.time()
    env = cls(seed=0, cenario='pilares')
    abrir = time.time() - t0
    try:
        t0 = time.time()
        env.reset()
        reset = time.time() - t0
        rng = np.random.default_rng(0)
        prof = cProfile.Profile() if perfil else None
        t0 = time.time()
        if prof:
            prof.enable()
        for _ in range(passos):
            _, _, term, trunc, _ = env.step(rng.uniform(-1, 1, 3).astype(np.float32) * [0, 1, 0])
            if term or trunc:
                env.reset()
        if prof:
            prof.disable()
        dt = time.time() - t0
        print(f"{nome}: {len(env._geo['centro'])} torpedos, segurar a cada {cls.SEGURAR_CADA}: "
              f"{passos / dt:.2f} passos/s (abrir {abrir:.0f} s, reset {reset:.1f} s, "
              f"fora do lugar {len(env._fora_do_lugar()) if env._n_obstaculos() else 0})", flush=True)
        if prof:
            s = io.StringIO()
            pstats.Stats(prof, stream=s).sort_stats('tottime').print_stats(18)
            print(s.getvalue()[-4000:], flush=True)
    finally:
        M.fechar(env._env)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--passos', type=int, default=100)
    ap.add_argument('--segurar-cada', type=int, default=10)
    args = ap.parse_args()
    print(f"limite de arquivos abertos: {resource.getrlimit(resource.RLIMIT_NOFILE)}", flush=True)
    medir('sem_obstaculos', args.passos, COM_OBSTACULOS=False)
    medir('finos_12', args.passos, FEIXE=1)
    medir('finos_12_segura_menos', args.passos, FEIXE=1, SEGURAR_CADA=args.segurar_cada)
    medir('grossos_48', args.passos, perfil=True, FEIXE=2)
    medir('grossos_48_segura_menos', args.passos, FEIXE=2, SEGURAR_CADA=args.segurar_cada)


if __name__ == '__main__':
    main()
