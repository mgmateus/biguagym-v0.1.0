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


# --- v1: auxiliares ---------------------------------------------------------------------------------------------
def _shaping(info):
    return sum(v for k, v in info['reward_terms'].items() if k != 'terminal')


def _v1(nome):
    return executar_caso(nome, version='v1')


# --- T4: Hover/Nav (R1, R2, R6) ---------------------------------------------------------------------------------
@pytest.mark.parametrize('tarefa', ['hover', 'nav'])
def test_hover_nav_sucesso_no_proprio_passo(tarefa):
    passos = _v1(f'{tarefa}_sucesso')
    r, term, trunc, info = passos[-1]
    assert term and not trunc
    assert info['termination_reason'] == 'success'
    assert r == pytest.approx(_shaping(info) + 10.0)
    assert info['reward_terms']['terminal'] == pytest.approx(10.0)
    for r_, t_, _, i_ in passos[:-1]:          # antes do alvo: sem término e sem bônus
        assert not t_ and i_['termination_reason'] is None and i_['reward_terms']['terminal'] == 0.0


@pytest.mark.parametrize('tarefa', ['hover', 'nav'])
def test_hover_nav_sucesso_bonus_fixo_com_shaping_negativo(tarefa):
    r, term, _, info = _v1(f'{tarefa}_sucesso_inclinado')[-1]
    assert term and info['termination_reason'] == 'success'
    assert _shaping(info) < 0
    assert r == pytest.approx(_shaping(info) + 10.0)


@pytest.mark.parametrize('tarefa', ['hover', 'nav'])
@pytest.mark.parametrize('falha,motivo', [('tilt', 'tilt'), ('fora', 'out_of_bounds')])
def test_hover_nav_termino_por_falha(tarefa, falha, motivo):
    r, term, _, info = _v1(f'{tarefa}_{falha}')[-1]
    assert term and info['termination_reason'] == motivo
    assert r == pytest.approx(_shaping(info) - 10.0)


@pytest.mark.parametrize('tarefa', ['hover', 'nav'])
def test_hover_nav_timeout_sem_penalidade(tarefa):
    r, term, trunc, info = _v1(f'{tarefa}_timeout')[-1]
    assert trunc and not term and info['termination_reason'] == 'timeout'
    assert r == pytest.approx(_shaping(info))


@pytest.mark.parametrize('tarefa', ['hover', 'nav'])
def test_hover_nav_tombar_rende_menos_que_ficar_parado(tarefa):
    g = 0.99
    ret = lambda ps: sum(g ** k * p[0] for k, p in enumerate(ps))
    tomba, parado = _v1(f'{tarefa}_tilt'), _v1(f'{tarefa}_parado')
    assert ret(tomba) < ret(parado)
    assert sum(p[0] for p in tomba) < sum(p[0] for p in parado)


# --- T5: Land/Dock (R1, R2, R6) ---------------------------------------------------------------------------------
@pytest.mark.parametrize('tarefa', ['land', 'dock'])
def test_land_dock_sucesso_no_proprio_passo(tarefa):
    passos = _v1(f'{tarefa}_sucesso')
    r, term, trunc, info = passos[-1]
    assert term and not trunc and info['termination_reason'] == 'success'
    assert r == pytest.approx(_shaping(info) + 20.0)
    assert all(not t for _, t, _, _ in passos[:-1])


@pytest.mark.parametrize('tarefa,duro', [('land', 'hard_landing'), ('dock', 'hard_docking')])
@pytest.mark.parametrize('falha', ['tilt', 'fora', 'duro'])
def test_land_dock_toda_falha_vale_menos_10(tarefa, duro, falha):
    motivo = {'tilt': 'tilt', 'fora': 'out_of_bounds', 'duro': duro}[falha]
    r, term, _, info = _v1(f'{tarefa}_{falha}')[-1]
    assert term and info['termination_reason'] == motivo
    assert r == pytest.approx(_shaping(info) - 10.0)        # o pouso duro deixa de ser -5 fixo
    assert 'impact' in info['reward_terms'] and 'drift' in info['reward_terms']


@pytest.mark.parametrize('tarefa', ['land', 'dock'])
def test_land_dock_tombar_nao_e_melhor_que_pouso_duro(tarefa):
    tomba = _v1(f'{tarefa}_tilt')[-1]
    duro = _v1(f'{tarefa}_duro')[-1]
    assert tomba[3]['reward_terms']['terminal'] == duro[3]['reward_terms']['terminal'] == -10.0


@pytest.mark.parametrize('tarefa', ['land', 'dock'])
def test_land_dock_tombar_rende_menos_que_ficar_parado(tarefa):
    tomba, parado = _v1(f'{tarefa}_tilt'), _v1(f'{tarefa}_parado')
    assert sum(p[0] for p in tomba) < sum(p[0] for p in parado)
