"""Diagnóstico da rotação do Hydrone no BiguaSim 1.1.0 (o simulador não aplica a guinada calculada pela dinâmica).

Com control_abstraction='accel' a dinâmica em Python devolve o comando como aceleração, então o que chega ao Unreal é
exatamente o que mandamos. Para cada agente o script mede:
  A. aceleração angular pura de 1 rad/s² em x, y e z (20 ticks) e linear de 1 m/s² em x, para comparar;
  B. set_physics_state com velocidade angular de 30°/s em z, sem aceleração depois (20 ticks);
  C. set_physics_state com velocidade angular de 30°/s em z reimposta a cada tick (20 ticks);
  D. teleporte para guinada de 45° (3 ticks).
Entre os testes o agente volta à pose inicial (atitude zero, parado).

Uso: python tools/diag_rotacao_hydrone.py [agente ...]   (padrão: Hydrone DjiMatrice)
"""
import os
import sys

import numpy as np

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, 'biguagym'))

PONTO = np.array([103.6, 97.4, 2.0])


def rpy(dyn):
    """Roll, pitch, yaw (graus) do quatérnio [x, y, z, w] do DynamicsSensor."""
    from scipy.spatial.transform import Rotation
    return Rotation.from_quat(dyn[15:19]).as_euler('xyz', degrees=True)


def rodar(agente):
    import gymnasium as gym
    import register  # noqa: F401

    env = gym.make('HydroneGotoPilares-v0', control_abstraction='accel', agent_type=agente)
    u = env.unwrapped
    try:
        env.reset()
        sim = u._env
        robo = sim.agents['robot-id0']
        zero = [0.0] * 6

        def passo(cmd):
            st = u._unwrap_state(sim.step(list(cmd), action_repeat=1))
            return np.asarray(st['DynamicsSensor'], dtype=float).ravel()

        def repor():
            robo.set_physics_state(PONTO, [0, 0, 0], [0, 0, 0], [0, 0, 0])
            for _ in range(3):
                d = passo(zero)
            return d

        def linha(rotulo, d0, d1):
            print(f"  {rotulo:<34} rpy {np.round(rpy(d0), 2)} -> {np.round(rpy(d1), 2)}  "
                  f"w {np.round(d1[12:15], 3)}  pos {np.round(d0[6:9], 2)} -> {np.round(d1[6:9], 2)}", flush=True)

        print(f"== {agente}", flush=True)
        for eixo, cmd in (('ang x 1 rad/s²', [0, 0, 0, 1, 0, 0]), ('ang y 1 rad/s²', [0, 0, 0, 0, 1, 0]),
                          ('ang z 1 rad/s²', [0, 0, 0, 0, 0, 1]), ('lin x 1 m/s²', [1, 0, 0, 0, 0, 0])):
            d0 = repor()
            for _ in range(20):
                d1 = passo(cmd)
            linha(f"A {eixo}, 20 ticks", d0, d1)

        d0 = repor()
        robo.set_physics_state(d0[6:9], [0, 0, 0], [0, 0, 0], [0, 0, 30])
        for _ in range(20):
            d1 = passo(zero)
        linha("B w_z 30°/s uma vez, 20 ticks", d0, d1)

        d0 = repor()
        d1 = d0
        for _ in range(20):
            robo.set_physics_state(d1[6:9], rpy(d1), d1[3:6], [0, 0, 30])
            d1 = passo(zero)
        linha("C w_z 30°/s a cada tick, 20 ticks", d0, d1)

        d0 = repor()
        robo.teleport(rotation=[0, 0, 45])
        for _ in range(3):
            d1 = passo(zero)
        linha("D teleporte yaw 45°, 3 ticks", d0, d1)
    finally:
        sim = getattr(u, '_env', None)          # o close() do biguagym só faz del self._env (Etapa 5)
        env.close()
        if sim is not None and hasattr(sim, '__on_exit__'):
            sim.__on_exit__()


if __name__ == '__main__':
    for agente in sys.argv[1:] or ['Hydrone', 'DjiMatrice']:
        rodar(agente)
