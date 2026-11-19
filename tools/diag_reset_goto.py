"""Onde o Hydrone fica logo depois do reset do GotoEnv com os obstáculos (spec hydrone-goto-dique, T11).

No lab (2026-11-18, posicionamento com teleport), o cenário ``pilares`` terminou por "parede" no 1º passo depois de cada
reset (100 de 100), e o ``dique`` não. Aqui: 3 resets por cenário, a posição do robô, a distância a cada borda da área e
o motivo do término em 3 passos parados.

Uso (no lab):  python tools/diag_reset_goto.py [--cenario pilares]
"""
import argparse
import os
import sys

import numpy as np

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
sys.path.insert(0, os.path.join(os.path.dirname(AQUI), 'biguagym'))
import mapear_dique as M  # noqa: E402
from core.goto import GotoEnv  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--cenario', action='append', choices=['pilares', 'dique'])
    ap.add_argument('--resets', type=int, default=3)
    args = ap.parse_args()
    parado = np.array([-1.0, 0.0, 0.0], np.float32)          # v = 0,01 m/s, sem guinada nem subida
    for cenario in args.cenario or ['pilares', 'dique']:
        env = GotoEnv(seed=0, cenario=cenario)
        try:
            lo, hi = env._bounds
            for r in range(args.resets):
                env.reset()
                pos = np.asarray(env._dynamics[6:9])
                bordas = {'x0': pos[0] - lo[0], 'x1': hi[0] - pos[0], 'y0': pos[1] - lo[1], 'y1': hi[1] - pos[1]}
                print(f"[{cenario}] reset {r}: pos {np.round(pos, 2).tolist()}, bordas "
                      f"{ {k: round(float(v), 2) for k, v in bordas.items()} }, fora do lugar {len(env._fora_do_lugar())}",
                      flush=True)
                for p in range(3):
                    _, _, term, trunc, info = env.step(parado)
                    pos = np.asarray(env._dynamics[6:9])
                    print(f"    passo {p}: pos {np.round(pos, 2).tolist()}, término {info['termination_reason']}",
                          flush=True)
                    if term or trunc:
                        break
        finally:
            M.fechar(env._env)


if __name__ == '__main__':
    main()
