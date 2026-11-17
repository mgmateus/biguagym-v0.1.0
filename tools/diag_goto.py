"""Diagnóstico do Goto do Hydrone no simulador (spec hydrone-goto-dique, T7).

Uso: python tools/diag_goto.py [env_id] [segundos]
     (padrão: HydroneGotoPilares-v0, 5 s)

1. Guinada: ω = +0,3 rad/s por N segundos e depois -0,3 rad/s, com a menor velocidade para a frente e vz = 0.
   Esperado: a guinada muda ~±0,3·N rad em cada fase (sinal e taxa do cmd_vel_yaw com a referência integrada).
2. Altura: vz = +0,3 m/s por N segundos (esperado: z sobe ~0,3·N m).
Imprime também os motivos de término e os alvos atingidos.
"""
import math
import os
import sys

import numpy as np

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, 'biguagym'))


def fase(env, acao, passos, rastro=0):
    u = env.unwrapped
    yaw0, z0 = float(u._dynamics[17]), float(u._dynamics[8])
    yaw_acc, yaw_ant, motivo = 0.0, yaw0, None
    for i in range(passos):
        _, _, term, trunc, info = env.step(np.asarray(acao, dtype=np.float32))
        yaw = float(u._dynamics[17])
        if i < rastro and i % 5 == 0:
            desvio = (u._yaw_ref - yaw + math.pi) % (2 * math.pi) - math.pi
            print(f"   passo {i:3d}: yaw_ref {u._yaw_ref:+.3f}  yaw {yaw:+.3f}  desvio {math.degrees(desvio):+6.1f}°  "
                  f"w_z {float(u._dynamics[14]):+.3f}", flush=True)
        yaw_acc += (yaw - yaw_ant + math.pi) % (2 * math.pi) - math.pi
        yaw_ant = yaw
        if term or trunc:
            motivo = info['termination_reason']
            break
    return yaw_acc, float(u._dynamics[8]) - z0, motivo


def main():
    import gymnasium as gym
    import register  # noqa: F401

    env_id = sys.argv[1] if len(sys.argv) > 1 else 'HydroneGotoPilares-v0'
    seg = float(sys.argv[2]) if len(sys.argv) > 2 else 5.0
    passos = int(seg * 20)
    env = gym.make(env_id)
    try:
        env.reset()
        for nome, acao, esperado in (('guinada +', [-1, 1, 0], ('yaw', 0.3 * seg)),
                                     ('guinada -', [-1, -1, 0], ('yaw', -0.3 * seg)),
                                     ('subida', [-1, 0, 1], ('z', 0.3 * seg))):
            dyaw, dz, motivo = fase(env, acao, passos, rastro=40 if nome == 'guinada +' else 0)
            medido = dyaw if esperado[0] == 'yaw' else dz
            print(f"{nome:10s} Δyaw = {dyaw:+.3f} rad  Δz = {dz:+.3f} m  "
                  f"(esperado {esperado[0]} ≈ {esperado[1]:+.2f}; medido {medido:+.3f}; término: {motivo})", flush=True)
            if motivo is not None:
                env.reset()
        # Sem o GotoEnv: desvio fixo de 20° direto no cmd_vel_yaw do BiguaSim (separa simulador e wrapper)
        u = env.unwrapped
        env.reset()
        yaw_ant, acc = float(u._dynamics[17]), 0.0
        for i in range(passos):
            st = u._unwrap_state(u._env.step([0.0, 0.0, 0.0, 20.0], action_repeat=1))
            u._set_dynamics(st)
            yaw = float(u._dynamics[17])
            acc += (yaw - yaw_ant + math.pi) % (2 * math.pi) - math.pi
            yaw_ant = yaw
            if i % 10 == 0:
                print(f"   direto passo {i:3d}: yaw {yaw:+.3f}  w_z {float(u._dynamics[14]):+.3f}  z {float(u._dynamics[8]):+.3f}",
                      flush=True)
        print(f"direto desvio 20°: Δyaw = {acc:+.3f} rad em {passos} ticks", flush=True)
    finally:
        env.close()


if __name__ == '__main__':
    main()
