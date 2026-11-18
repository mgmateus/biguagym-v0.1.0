"""Spec hydrone-goto-dique T10: análise do tools/conferir_obstaculos.py (sem simulador)."""
import math
import os
import sys

import numpy as np
import pytest

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(AQUI), 'tools'))
sys.path.insert(0, os.path.join(os.path.dirname(AQUI), 'biguagym'))

import conferir_obstaculos as C  # noqa: E402
from core.goto import carregar_agente_obstaculo, carregar_cenario, geometria_obstaculos  # noqa: E402


def geo(nome='pilares'):
    return geometria_obstaculos(carregar_cenario(nome), carregar_agente_obstaculo())


def test_raio_bate_no_feixe_do_pilar():
    g = geo()
    # do lado +x do pilar (129,4; −152), a 1,5 m do eixo: a face do torpedo mais perto fica em 129,52 + 0,095
    t, j = C.raio_capsulas(g, [130.9, -151.88, 1.5], [-1, 0, 0], 40.0)
    assert t == pytest.approx(130.9 - 129.615, abs=2e-3) and g['obstaculo'][j] == 0


def test_raio_sem_obstaculo_e_infinito():
    assert C.raio_capsulas(geo(), [134.0, -146.0, 1.5], [1, 0, 0], 10.0) == (math.inf, -1)


def test_extensao_da_coluna():
    zs = np.arange(-2.6, 6.81, 0.2)
    ds = np.where((zs >= -1.2) & (zs <= 5.4), 1.29, 3.9)
    lo, hi = C.extensao(zs, ds)
    assert lo == pytest.approx(-1.2, abs=0.21) and hi == pytest.approx(5.4, abs=0.21)       # passo da varredura
    assert C.extensao(zs, np.full_like(zs, 3.9)) == (None, None)
    assert C.extensao([0, 1], [0.0, np.nan]) == (None, None)        # leituras inválidas não contam


@pytest.mark.parametrize('ang,psi,esperado', [(0.0, 0.0, 0), (math.pi / 2, 0.0, 90), (0.0, math.pi / 2, 270),
                                              (math.pi, math.pi, 0)])
def test_indice_laser(ang, psi, esperado):
    assert C.indice_laser(ang, psi, 360) == esperado


def test_comparar_anel_com_lidar_perfeito():
    g = geo()
    pos, psi, n = np.array([133.88, -152.6, 2.0]), 0.3, 360
    lidar = np.full(n, 40.0)
    for i in range(n):
        a = psi + 2 * math.pi * i / n
        t, _ = C.raio_capsulas(g, pos, [math.cos(a), math.sin(a), 0], 40.0)
        if np.isfinite(t):
            lidar[i] = t + 0.05
    r = C.comparar_anel(g, lidar, pos, psi, 40.0)
    assert set(r) == {0, 1, 2, 3}                                    # os 4 pilares vistos do spawn
    assert all(v['mediana_dif_m'] == pytest.approx(0.05, abs=1e-3) for v in r.values())
