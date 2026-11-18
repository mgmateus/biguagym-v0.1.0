"""tools/mapear_dique.py: análise do mapa do dique (sem simulador), com o mapa sintético da ferramenta."""
import math
import os
import sys

import numpy as np
import pytest

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(AQUI), 'tools'))

import mapear_dique as M  # noqa: E402

NAVIO = (143, 157, -235, -140)        # x0, x1, y0, y1 do navio no mapa sintético
BACIA = (128, 175, -258, -116)


def analisar(topo=None, passo=1.0, semente=None):
    xs, ys, t = M.mapa_sintetico(passo=passo)
    topo = t if topo is None else topo(xs, ys, t)
    agua = M.classificar(topo, 0.0, 0.5)
    bacia = M.achar_bacia(agua, xs, ys, semente)
    return xs, ys, topo, agua, bacia


def test_cercado_conta_as_4_direcoes():
    agua = np.ones((5, 5), bool)
    agua[0, :] = agua[-1, :] = agua[:, 0] = False         # aberto só para +x
    n = M.cercado(agua)
    assert n[2, 2] == 3 and n[2, 4] == 3


def test_bacia_e_o_dique_e_nao_o_mar():
    xs, ys, _, _, bacia = analisar()
    X, Y = np.meshgrid(xs, ys)
    dentro = (X >= BACIA[0]) & (X <= BACIA[1]) & (Y >= BACIA[2]) & (Y <= BACIA[3])
    navio = (X >= NAVIO[0]) & (X <= NAVIO[1]) & (Y >= NAVIO[2]) & (Y <= NAVIO[3])
    assert np.array_equal(bacia, dentro & ~navio)


def test_area_dos_pilares_longe_do_navio_e_das_paredes():
    xs, ys, topo, agua, bacia = analisar()
    pil, dique, med = M.montar_cenarios(bacia, agua, topo, xs, ys, 1.0, 0.0, 10.0, 0.2)
    (x0, y0), (x1, y1) = pil['area']
    assert x1 - x0 == pytest.approx(10) and y1 - y0 == pytest.approx(10)
    assert BACIA[0] < x0 and x1 < BACIA[1] and BACIA[2] < y0 and y1 < BACIA[3]
    dx = max(NAVIO[0] - x1, x0 - NAVIO[1], 0)
    dy = max(NAVIO[2] - y1, y0 - NAVIO[3], 0)
    assert math.hypot(dx, dy) >= med['folga_min_area_m'] >= 5.0
    assert M.checar_cenario(pil) == [] and M.checar_cenario(dique) == []
    assert len(pil['pilares']) == 4 and pil['provisorio'] is False
    for p in pil['pilares']:
        assert x0 < p['xy'][0] < x1 and y0 < p['xy'][1] < y1


def test_navio_vira_caixa_de_exclusao_do_dique():
    xs, ys, topo, agua, bacia = analisar()
    _, dique, _ = M.montar_cenarios(bacia, agua, topo, xs, ys, 1.0, 0.0, 10.0, 0.2)
    (c,) = dique['exclusao']
    assert c['min'][0] <= NAVIO[0] and c['max'][0] >= NAVIO[1] and c['min'][1] <= NAVIO[2] and c['max'][1] >= NAVIO[3]
    assert c['max'][2] >= 10.0
    (bx0, by0), (bx1, by1) = dique['area']
    assert bx0 == pytest.approx(BACIA[0] - 0.5) and by1 == pytest.approx(BACIA[3] + 0.5)


def test_dique_aberto_para_o_mar():
    def portao_aberto(xs, ys, t):
        t = t.copy()
        X, Y = np.meshgrid(xs, ys)
        t[(X >= 140) & (X <= 165) & (Y < -258)] = -60.0       # sem a parede sul: a bacia encosta no mar
        return t
    xs, ys, _, _, bacia = analisar(portao_aberto)
    X, Y = np.meshgrid(xs, ys)
    assert not bacia[X > 180].any()                           # o mar a leste não entra
    assert bacia[(X == 135) & (Y == -200)].all()


def test_semente_escolhe_e_recusa():
    xs, ys, _, _, bacia = analisar(semente=(135, -200))
    assert bacia[ys.tolist().index(-200), xs.tolist().index(135)]
    with pytest.raises(ValueError):
        analisar(semente=(150, -200))                         # em cima do navio


def test_sem_bacia_devolve_none():
    xs, ys, t = M.mapa_sintetico(passo=3.0)
    assert M.achar_bacia(M.classificar(np.full_like(t, -60.0), 0.0, 0.5), xs, ys) is None


def test_bacia_estreita_encolhe_a_area_para_ter_a_folga():
    def estreita(xs, ys, t):                                  # navio largo: canais de 9 m e 23 m nas pontas
        t = t.copy()
        X, Y = np.meshgrid(xs, ys)
        t[(X >= 137) & (X <= 166) & (Y >= -235) & (Y <= -140)] = 10.0
        t[(X >= 128) & (X <= 175) & (Y >= -258) & (Y <= -116) & ((Y > -132) | (Y < -245))] = 3.0   # pontas fechadas
        return t
    xs, ys, topo, agua, bacia = analisar(estreita)
    pil, _, med = M.montar_cenarios(bacia, agua, topo, xs, ys, 1.0, 0.0, 10.0, 0.2, lado_min=4.0, folga_min=1.5)
    w, h = med['area_lados_m']
    assert med['folga_min_area_m'] >= 1.5 and 4.0 <= min(w, h) <= max(w, h) <= 10.0
    assert min(w, h) < 10.0                                   # o quadrado de 10 m não cabe com 1,5 m de folga
    assert M.checar_cenario(pil) == []
    (x0, y0), (x1, y1) = pil['area']
    assert x1 - x0 == pytest.approx(w) and y1 - y0 == pytest.approx(h)
