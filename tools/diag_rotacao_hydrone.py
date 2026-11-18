"""Diagnóstico da rotação do Hydrone no BiguaSim 1.1.0 (o simulador não aplica a guinada calculada pela dinâmica).

Com control_abstraction='accel' a dinâmica em Python devolve o comando como aceleração, então o que chega ao Unreal é
exatamente o que mandamos. Para cada agente o script mede:
  A. aceleração angular pura de 1 rad/s² em x, y e z (20 ticks) e linear de 1 m/s² em x, para comparar;
  B. set_physics_state com velocidade angular de 30°/s em z, sem aceleração depois (20 ticks);
  C. set_physics_state com velocidade angular de 30°/s em z reimposta a cada tick (20 ticks);
  D. teleporte para guinada de 45° (3 ticks);
  E. aceleração angular em z de 1, 3,35 e 10 rad/s² (20 ticks cada);
  F. cmd_vel_yaw com desvio de 20° (30 ticks), gravando o que a dinâmica manda, e depois as mesmas acelerações
     reenviadas em modo accel a partir da pose inicial;
  G. roll e pitch: ω de 30°/s em x e em y reimposta a cada tick (20 ticks) e teleporte para roll/pitch de 10° (3 ticks).
Entre os testes o agente volta à pose inicial (atitude zero, parado).

Uso: python tools/diag_rotacao_hydrone.py [agente ...]   (padrão: Hydrone DjiMatrice)
     python tools/diag_rotacao_hydrone.py goto            (com a integração angular do GotoEnv, spec rotacao-hydrone:
                                                           ω medido × previsto e guinada no ar e na água)
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

        for nome, w in (('x', [30, 0, 0]), ('y', [0, 30, 0])):
            d0 = repor()
            d1 = d0
            for _ in range(20):
                robo.set_physics_state(d1[6:9], rpy(d1), d1[3:6], w)
                d1 = passo(zero)
            linha(f"G w_{nome} 30°/s a cada tick, 20 ticks", d0, d1)
        for nome, rot in (('roll', [10, 0, 0]), ('pitch', [0, 10, 0])):
            d0 = repor()
            robo.teleport(rotation=rot)
            for _ in range(3):
                d1 = passo(zero)
            linha(f"G teleporte {nome} 10°, 3 ticks", d0, d1)

        for mag in (1.0, 3.35, 10.0):
            d0 = repor()
            for _ in range(20):
                d1 = passo([0, 0, 0, 0, 0, mag])
            linha(f"E ang z {mag} rad/s², 20 ticks", d0, d1)

        modelo = sim._dynamics_dict['robot']
        saidas = []
        original = modelo.step

        def gravar(*a, **k):
            r = original(*a, **k)
            saidas.append(list(np.asarray(r, dtype=float).ravel()))
            return r

        def abstracao(nome):
            modelo.control_abstraction = nome
            if hasattr(modelo, '_control_abstraction'):
                modelo._control_abstraction = nome

        d0 = repor()
        abstracao('cmd_vel_yaw')
        modelo.step = gravar
        d1 = d0
        for _ in range(30):
            d1 = passo([0, 0, 0, 20])
        modelo.step = original
        abstracao('accel')
        linha("F1 cmd_vel_yaw 20°, 30 ticks", d0, d1)
        print(f"     acelerações enviadas (ticks 0, 1, 2, 15, 29): "
              f"{[np.round(saidas[i], 2).tolist() for i in (0, 1, 2, 15, 29)]}", flush=True)
        d0 = repor()
        for cmd in saidas:
            d1 = passo(cmd)
        linha("F2 as mesmas em accel, 30 ticks", d0, d1)
    finally:
        sim = getattr(u, '_env', None)          # o close() do biguagym só faz del self._env (Etapa 5)
        env.close()
        if sim is not None and hasattr(sim, '__on_exit__'):
            sim.__on_exit__()


def rodar_goto(ticks=60):
    """cmd_vel_yaw de 20° pela integração do GotoEnv, no ar (z = 2) e na água (z = -0,5).

    A cada tick compara a ω medida com a prevista pela dinâmica (ω anterior + ω̇·dt): a razão perto de 1 confirma o
    amortecimento do motor usado na compensação (AMORTECIMENTO_ANGULAR_MOTOR).
    """
    import gymnasium as gym
    import register  # noqa: F401

    env = gym.make('HydroneGotoPilares-v0')
    u = env.unwrapped
    try:
        for meio, z in (('ar', 2.0), ('água', -0.5)):
            env.reset()
            robo = u._env.agents['robot-id0']
            robo.set_physics_state([PONTO[0], PONTO[1], z], [0, 0, 0], [0, 0, 0], [0, 0, 0])
            for _ in range(20):                                   # assenta (no ar, segura a altura; na água, a profundidade)
                st = u._unwrap_state(u._passo_sim([0.0, 0.0, 0.0, 0.0]))
            d0 = np.asarray(st['DynamicsSensor'], dtype=float).ravel()
            u._set_dynamics(st)
            yaw0, yaw_ant, acc = float(u._dynamics[17]), float(u._dynamics[17]), 0.0
            w_ant, wd_ant, razoes = d0[12:15].copy(), u._w_dot.copy(), []
            print(f"== goto, {meio}: z0 = {d0[8]:+.2f}", flush=True)
            for i in range(ticks):
                st = u._unwrap_state(u._passo_sim([0.0, 0.0, 0.0, 20.0]))
                d = np.asarray(st['DynamicsSensor'], dtype=float).ravel()
                u._set_dynamics(st)
                previsto = w_ant[2] + wd_ant[2] / u.TICKS_POR_S
                if abs(previsto) > 1e-3:
                    razoes.append(d[14] / previsto)
                yaw = float(u._dynamics[17])
                acc += (yaw - yaw_ant + np.pi) % (2 * np.pi) - np.pi
                yaw_ant = yaw
                if i % 10 == 0 or i == ticks - 1:
                    print(f"  tick {i:3d}: yaw {np.degrees(yaw):+8.2f}°  w_z medido {d[14]:+.3f} previsto {previsto:+.3f}  "
                          f"ω̇ {np.round(u._w_dot, 2)}  rpy {np.round(rpy(d), 1)}  pos {np.round(d[6:9], 2)}", flush=True)
                w_ant, wd_ant = d[12:15].copy(), u._w_dot.copy()
            r = np.asarray(razoes)
            print(f"  {meio}: Δyaw = {np.degrees(acc):+.1f}° em {ticks} ticks; w medido/previsto: mediana "
                  f"{np.median(r) if r.size else float('nan'):.3f} (min {r.min() if r.size else float('nan'):.3f}, "
                  f"max {r.max() if r.size else float('nan'):.3f})", flush=True)
    finally:
        sim = getattr(u, '_env', None)
        env.close()
        if sim is not None and hasattr(sim, '__on_exit__'):
            sim.__on_exit__()


if __name__ == '__main__':
    if sys.argv[1:] == ['goto']:
        rodar_goto()
    else:
        for agente in sys.argv[1:] or ['Hydrone', 'DjiMatrice']:
            rodar(agente)
