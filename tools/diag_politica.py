"""Diagnóstico: o que a política TD3 treinada faz (um ambiente por processo, poucos passos).
Uso: python tools/diag_politica.py <env_id> <actor.pt> [passos=600] [reward_version=v0] [env_version=v1]
(use o env_version do treino: o padrão do código é v2 desde a spec colapso-blueboat; os runs anteriores são v1)"""
import collections, json, os, sys
import numpy as np, gymnasium as gym, torch
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO); sys.path.insert(0, os.path.join(REPO, 'biguagym'))
import register  # noqa: F401
from src.agents.td3 import Actor

env_id, pt, N = sys.argv[1], sys.argv[2], int(sys.argv[3]) if len(sys.argv) > 3 else 600
rversao = sys.argv[4] if len(sys.argv) > 4 else 'v0'
eversao = sys.argv[5] if len(sys.argv) > 5 else 'v1'
env = gym.make(env_id, reward_version=rversao, env_version=eversao)
u = env.unwrapped
sd = torch.load(pt, map_location='cpu')
hid = sd['fc1.weight'].shape[0]
actor = Actor(env.observation_space.shape, env.action_space.shape,
              (env.action_space.high, env.action_space.low), hid)
actor.load_state_dict(sd); actor.eval()
obs, _ = env.reset(seed=0)
lo, hi = env.action_space.low, env.action_space.high
meio, meia = (hi + lo) / 2, (hi - lo) / 2


def dist_alvo():
    if getattr(u, '_target', None) is None:
        return None
    return float(np.linalg.norm(np.asarray(u._target) - np.asarray(u._dynamics[6:9])))


d_ini, ep_ini_fim, todos_sat = dist_alvo(), [], []
motivos, compr, termos, k, ret = collections.Counter(), [], collections.defaultdict(float), 0, 0.0
sat, yaw, dist, acoes = [], [], [], []
for _ in range(N):
    with torch.no_grad():
        a = actor(torch.as_tensor(np.asarray(obs, np.float32)[None]))[0].numpy()
    todos_sat.append(bool(np.all(np.abs((a - meio) / meia) >= 0.95)))   # todos os motores a >= 95% do limite
    sat.append(float(np.mean((a <= lo + 0.02 * (hi - lo)) | (a >= hi - 0.02 * (hi - lo)))))
    acoes.append(a)
    obs, r, term, trunc, info = env.step(a); k += 1; ret += r
    for n_, v in (info.get('reward_terms') or {}).items():
        termos[n_] += v
    yaw.append(abs(float(u._dynamics[14])))
    if getattr(u, '_target', None) is not None:
        dist.append(float(np.linalg.norm(np.asarray(u._target) - np.asarray(u._dynamics[6:9]))))
    if term or trunc:
        motivos[info.get('termination_reason')] += 1; compr.append(k); k = 0
        if d_ini is not None:
            ep_ini_fim.append((d_ini, dist_alvo()))
        obs, _ = env.reset(); d_ini = dist_alvo()
A = np.array(acoes)
print('POL ' + json.dumps({
    'env': env_id, 'reward_version': rversao, 'env_version': eversao, 'episodios': len(compr), 'motivos': dict(motivos),
    'passos_med': float(np.median(compr)) if compr else None,
    'recompensa_por_passo': round(ret / N, 4),
    'termos_por_passo': {n_: round(v / N, 4) for n_, v in termos.items()},
    'fracao_acao_saturada': round(float(np.mean(sat)), 3),
    'frac_dois_motores_saturados': round(float(np.mean(todos_sat)), 3),
    'dist_ini_fim_media': (np.round(np.mean(ep_ini_fim, axis=0), 2).tolist() if ep_ini_fim else None),
    'acao_media': np.round(A.mean(0), 1).tolist(), 'acao_desvio': np.round(A.std(0), 1).tolist(),
    'yaw_rate_med': round(float(np.median(yaw)), 3),
    'dist_alvo_ini_fim': [round(dist[0], 2), round(dist[-1], 2)] if dist else None,
    'dist_alvo_min': round(min(dist), 2) if dist else None}))
