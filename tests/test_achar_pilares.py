"""tools/achar_pilares.py: pilares achados nas fatias de LiDAR (sem simulador), com o cenário sintético da ferramenta."""
import math
import os
import sys

import numpy as np
import pytest

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(AQUI), 'tools'))

import achar_pilares as A  # noqa: E402

REGIAO = (-5.0, 40.0, -5.0, 30.0)


class Args:
    celula, diam_max, isolamento, raio_grupo = 0.25, 2.5, 1.5, 15.0


@pytest.mark.parametrize('sinal', [1, -1])
def test_sentido_dos_lasers_pela_nitidez(sinal):
    leituras, _, _ = A.sintetico(sinal)
    assert A.escolher_sinal([l for z in leituras for l in leituras[z]])[0] == sinal


@pytest.mark.parametrize('sinal', [1, -1])
def test_acha_os_4_pilares_e_ignora_o_poste_so_no_ar(sinal):
    leituras, pilares, poste = A.sintetico(sinal)
    _, _, por_z, achados, grupos = A.analisar(leituras, REGIAO, Args)
    assert len(achados) == 4
    for px, py in pilares:
        assert min(math.hypot(p['x'] - px, p['y'] - py) for p in achados) < 0.5
    assert all(math.hypot(p['x'] - poste[0], p['y'] - poste[1]) > 2 for p in achados)
    assert any(math.hypot(c[0] - poste[0], c[1] - poste[1]) < 0.5 for c in por_z[2.0])   # visto no ar, só lá
    assert grupos[0]['n'] == 4 and grupos[0]['centro'] == pytest.approx([13.0, 13.0], abs=0.3)


def test_parede_nao_vira_pilar():
    leituras, _, _ = A.sintetico(1)
    cands = A.candidatos(A.nuvem(leituras[-0.7], 1), REGIAO)
    assert all(c[0] > 1.0 for c in cands)                     # nada na parede do cais (x = 0)


def test_agrupar_separa_grupos_distantes():
    pil = [{'x': x, 'y': 0.0} for x in (0, 5, 10, 100, 104)]
    g = A.agrupar(pil, raio=15)
    assert [x['n'] for x in g] == [3, 2]


def test_pontos_lidar_so_na_agua_perto_de_estrutura():
    xs = np.arange(0, 101, 1.0)
    ys = np.arange(0, 101, 1.0)
    agua = np.ones((101, 101), bool)
    agua[:, :10] = False                                       # cais à esquerda
    pts = A.pontos_lidar(agua, xs, ys, 1.0, 10.0)
    assert pts and all(x >= 12 and x - 9.5 <= A.LIDAR_MAX - 5 + 1 for x, _ in pts)
