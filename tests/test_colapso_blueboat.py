"""Testes da spec colapso-blueboat, sem simulador."""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'tools'))
from diag_referencia import controlador  # noqa: E402

LO, HI = -295.75, 288.08


# --- T2: controlador de referência -----------------------------------------------------------------------------
def test_controlador_alvo_a_frente():
    a = controlador([0, 0, 0], 0.0, [5, 0, 0], LO, HI)
    assert a[0] > 0 and a[1] > 0 and abs(a[0] - a[1]) < 1e-6


def test_controlador_alvo_a_esquerda():
    # guinada positiva (esquerda): motor de boreste (2) mais forte que o de bombordo (1)
    a = controlador([0, 0, 0], 0.0, [3, 3, 0], LO, HI)
    assert a[1] > a[0]


def test_controlador_alvo_atras_gira_sem_avancar():
    a = controlador([0, 0, 0], 0.0, [-5, 0.1, 0], LO, HI)
    assert abs(a[0] + a[1]) < 1e-6 and a[1] > 0


def test_controlador_respeita_limites():
    a = controlador([0, 0, 0], 0.0, [100, 0, 0], LO, HI)
    assert np.all(a >= LO) and np.all(a <= HI)
