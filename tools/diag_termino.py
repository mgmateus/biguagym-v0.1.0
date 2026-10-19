"""Diagnóstico: motivo de término e altura com ação zero e aleatória (um ambiente por processo, < 5k passos).
Uso: python tools/diag_termino.py <env_id> [passos_por_politica=300] [env_version=v1]"""
import json, os, sys, collections
import numpy as np, gymnasium as gym
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, 'biguagym'))
import register  # noqa: F401

env_id, N = sys.argv[1], int(sys.argv[2]) if len(sys.argv) > 2 else 300
versao = sys.argv[3] if len(sys.argv) > 3 else 'v1'
env = gym.make(env_id, reward_version='v1', env_version=versao)
u = env.unwrapped
out = {'env': env_id, 'env_version': versao, 'z_spawn': float(u._location[2]), 'bounds_z': [float(u._bounds[0, 2]), float(u._bounds[1, 2])],
       'acao': [float(env.action_space.low[0]), float(env.action_space.high[0])]}
for pol in ('zero', 'aleatoria'):
    env.reset(seed=0)
    motivos, compr, z0s, zfs, tilts, passos, k = collections.Counter(), [], [], [], [], 0, 0
    z0s.append(float(u._dynamics[8]))
    while passos < N:
        a = np.zeros(env.action_space.shape, np.float32) if pol == 'zero' else env.action_space.sample()
        _, r, term, trunc, info = env.step(a); passos += 1; k += 1
        if term or trunc:
            motivos[info.get('termination_reason')] += 1; compr.append(k); zfs.append(float(u._dynamics[8]))
            rpy = np.degrees(np.asarray(u._dynamics[15:18], float)); tilts.append(round(float(max(abs(rpy[0]), abs(rpy[1]))), 1))
            env.reset(); k = 0; z0s.append(float(u._dynamics[8]))
    out[pol] = {'episodios': len(compr), 'motivos': dict(motivos), 'passos_med': float(np.median(compr)) if compr else None,
                'z_inicio': round(float(np.mean(z0s)), 3), 'z_fim_med': round(float(np.median(zfs)), 3) if zfs else None,
                'tilt_fim_med_graus': float(np.median(tilts)) if tilts else None}
print('DIAG ' + json.dumps(out))
