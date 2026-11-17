"""Diagnóstico da guinada do Hydrone no BiguaSim 1.1.0 (spec hydrone-goto-dique, T7).

No lab, cmd_vel_yaw com desvio fixo de 20° não girou o Hydrone (Δyaw ≈ 0 em 100 ticks), embora a dinâmica, fora do
simulador, devolva ~22 rad/s² de aceleração angular. Este script registra, dentro do simulador, o que a dinâmica
devolve a cada tick (aceleração linear e angular) e o estado do DynamicsSensor, e testa cmd_pos_yaw com guinada de 90°.

Uso: python tools/diag_guinada_hydrone.py [agente ...]   (padrão: Hydrone; ex.: DjiMatrice para comparar)
"""
import os
import sys

import numpy as np

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, 'biguagym'))


def rodar(abstracao, comando, ticks=60, agente='Hydrone'):
    import gymnasium as gym
    import register  # noqa: F401

    env = gym.make('HydroneGotoPilares-v0', control_abstraction=abstracao, agent_type=agente)
    u = env.unwrapped
    try:
        env.reset()
        modelo = u._env._dynamics_dict['robot']
        saidas = []
        original = modelo.step

        def gravar(*a, **k):
            r = original(*a, **k)
            saidas.append(np.asarray(r, dtype=float).ravel())
            return r

        modelo.step = gravar
        print(f"== {agente} {abstracao} {comando}", flush=True)
        for i in range(ticks):
            st = u._unwrap_state(u._env.step(list(comando), action_repeat=1))
            u._set_dynamics(st)
            if i % 10 == 0 or i == ticks - 1:
                dyn = np.asarray(st['DynamicsSensor'], dtype=float).ravel()
                acc = saidas[-1] if saidas else np.zeros(6)
                print(f"  tick {i:3d}: yaw {np.degrees(u._dynamics[17]):+8.2f}°  pos {np.round(u._dynamics[6:9], 2)}  "
                      f"acc_lin {np.round(acc[:3], 2)}  acc_ang {np.round(acc[3:6], 2)}  "
                      f"w_sensor {np.round(dyn[12:15], 3)}  q {np.round(dyn[15:19], 3)}", flush=True)
    finally:
        sim = getattr(u, '_env', None)          # o close() do biguagym só faz del self._env (Etapa 5)
        env.close()
        if sim is not None and hasattr(sim, '__on_exit__'):
            sim.__on_exit__()


if __name__ == '__main__':
    agentes = sys.argv[1:] or ['Hydrone']
    for agente in agentes:
        rodar('cmd_vel_yaw', [0.0, 0.0, 0.0, 20.0], agente=agente)
        rodar('cmd_pos_yaw', [103.6, 97.4, 2.0, 90.0], agente=agente)
