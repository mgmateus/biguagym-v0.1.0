"""Gera tests/dados/recompensa_v0.json: a recompensa ORIGINAL dos casos fixos de recompensas_util.casos().

Rodar com o código original do biguagym (32698e5, antes da spec recompensas). Depois da mudança, o teste
test_v0_identico_ao_original confere que reward_version="v0" reproduz exatamente estes valores.
"""
import json
import os

import numpy as np

from recompensas_util import casos, executar_caso

AQUI = os.path.dirname(os.path.abspath(__file__))


def main():
    ref = {}
    for nome in sorted(casos()):
        passos = executar_caso(nome, version='v0')
        for r, *_ in passos:
            assert np.isfinite(r), (nome, r)
        ref[nome] = [[r, term, trunc] for r, term, trunc, _ in passos]
    os.makedirs(os.path.join(AQUI, 'dados'), exist_ok=True)
    with open(os.path.join(AQUI, 'dados', 'recompensa_v0.json'), 'w') as f:
        json.dump(ref, f, indent=1, sort_keys=True)
    print(f'{len(ref)} casos, {sum(len(v) for v in ref.values())} passos')


if __name__ == '__main__':
    main()
