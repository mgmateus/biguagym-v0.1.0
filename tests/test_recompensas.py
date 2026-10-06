"""Testes da spec recompensas, sem simulador (ver tests/recompensas_util.py)."""
import inspect
import json
import os

import numpy as np
import pytest

import core.environments as E
from recompensas_util import casos, executar_caso

AQUI = os.path.dirname(os.path.abspath(__file__))
CLASSES = [c for _, c in inspect.getmembers(E, inspect.isclass)
           if c.__module__ == 'core.environments' and '__init__' in c.__dict__ and hasattr(c, '_step')]


# --- R5: seleção da versão -------------------------------------------------------------------------------------
def test_versao_em_todos_os_construtores():
    assert len(CLASSES) == 13
    for c in CLASSES:
        p = inspect.signature(c.__init__).parameters
        assert 'reward_version' in p, c.__name__
        assert p['reward_version'].default == 'v1', c.__name__


def test_versao_invalida():
    with pytest.raises(ValueError):
        E.HoverEnv(seed=0, agent_type='DjiMatrice', control_abstraction='cmd_motor_speeds',
                   location=[0, 0, 0], rotation=[0, 0, 0], reward_version='x')


def test_v0_identico_ao_original():
    ref = json.load(open(os.path.join(AQUI, 'dados', 'recompensa_v0.json')))
    assert sorted(ref) == sorted(casos())
    for nome, esperado in ref.items():
        obtido = [[r, t, tr] for r, t, tr, _ in executar_caso(nome, version='v0')]
        assert len(obtido) == len(esperado), nome
        for (r, t, tr), (re_, te, tre) in zip(obtido, esperado):
            assert (t, tr) == (te, tre), nome
            assert r == pytest.approx(re_, abs=1e-9), nome
