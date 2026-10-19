"""Testes da spec ajuste-ambientes, sem simulador.

Os ambientes são criados com ``object.__new__`` (sem abrir o Unreal) e os atributos usados por ``_build_params``,
``_reset``, ``_wrap_state`` e ``_tilt_limit`` são injetados. ``_build_params`` só lê os JSON de configuração.
"""
import inspect

import numpy as np
import pytest

import core.environments as E
import recompensas_util  # noqa: F401  (põe o submódulo no sys.path)

CLASSES = [c for _, c in inspect.getmembers(E, inspect.isclass)
           if c.__module__ == 'core.environments' and '__init__' in c.__dict__ and hasattr(c, '_step')]


# --- R5: seleção da versão -------------------------------------------------------------------------------------
def test_versao_em_todos_os_construtores():
    assert len(CLASSES) == 13
    for c in CLASSES:
        p = inspect.signature(c.__init__).parameters
        assert 'env_version' in p, c.__name__
        assert p['env_version'].default == 'v1', c.__name__


def test_versao_invalida():
    with pytest.raises(ValueError):
        E.HoverEnv(seed=0, agent_type='DjiMatrice', control_abstraction='cmd_motor_speeds',
                   location=[0, 0, 0], rotation=[0, 0, 0], env_version='x')
