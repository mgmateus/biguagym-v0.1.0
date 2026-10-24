"""Avaliação de uma política TD3 treinada contra a política aleatória, nos mesmos alvos (um ambiente por processo).
Por episódio: motivo de término, passos, retorno, distância ao alvo (inicial, mínima, final), progresso no caminho
(Trajectory), ação média/desvio e a trajetória XYZ (a cada 2 passos), para os gráficos de tools/graficos_avaliacao.py.

Uso: python tools/avaliar_politica.py <env_id> <actor.pt> <saida.json> [episodios=10] [reward_version=v1] [env_version=v1]
"""
import json, os, sys
import numpy as np
import torch

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO); sys.path.insert(0, os.path.join(REPO, 'biguagym'))


def episodio(env, pol, semente):
    u = env.unwrapped
    u.rng = np.random.default_rng(1000 + semente)        # mesmo alvo para a política e para a aleatória
    env.action_space.seed(1000 + semente)
    obs, _ = env.reset()
    alvo = getattr(u, '_target', None) if getattr(u, '_HAS_TARGET', True) else None
    alvo = None if alvo is None else [round(float(v), 3) for v in alvo]
    traj = [u._dynamics[6:9]]
    ret, k, acoes, dists, prog, cte = 0.0, 0, [], [], 0.0, []
    lo, hi = env.action_space.low, env.action_space.high
    while True:
        a = pol(obs)
        acoes.append(a)
        obs, r, term, trunc, info = env.step(a)
        ret += float(r); k += 1
        p = np.asarray(u._dynamics[6:9], float)
        if k % 2 == 0:
            traj.append(p)
        if alvo is not None:
            dists.append(float(np.linalg.norm(np.asarray(alvo) - p)))
        prog = max(prog, float(info.get('progress', 0.0)))
        if 'cross_track_error' in info:
            cte.append(float(info['cross_track_error']))
        if term or trunc:
            break
    traj.append(np.asarray(u._dynamics[6:9], float))
    A = np.asarray(acoes, float)
    sat = np.mean((A <= lo + 0.05 * (hi - lo)) | (A >= hi - 0.05 * (hi - lo)))
    d0 = float(np.linalg.norm(np.asarray(alvo) - np.asarray(traj[0], float))) if alvo is not None else None
    return {'semente': semente, 'motivo': info.get('termination_reason'), 'passos': k, 'retorno': round(ret, 3),
            'alvo': alvo, 'd_ini': None if d0 is None else round(d0, 3),
            'd_min': round(min(dists), 3) if dists else None, 'd_fim': round(dists[-1], 3) if dists else None,
            'progresso': round(prog, 3), 'cte_media': round(float(np.mean(cte)), 3) if cte else None,
            'acao_media': np.round(A.mean(0), 3).tolist(), 'acao_desvio': np.round(A.std(0), 3).tolist(),
            'frac_saturada': round(float(sat), 3),
            'traj': np.round(np.asarray(traj, float), 2).tolist()}


def main():
    import gymnasium as gym
    import register  # noqa: F401
    from src.agents.td3 import Actor

    env_id, pt, saida = sys.argv[1:4]
    n = int(sys.argv[4]) if len(sys.argv) > 4 else 10
    rv = sys.argv[5] if len(sys.argv) > 5 else 'v1'
    ev = sys.argv[6] if len(sys.argv) > 6 else 'v1'
    env = gym.make(env_id, reward_version=rv, env_version=ev)
    sd = torch.load(pt, map_location='cpu')
    actor = Actor(env.observation_space.shape, env.action_space.shape,
                  (env.action_space.high, env.action_space.low), sd['fc1.weight'].shape[0])
    actor.load_state_dict(sd); actor.eval()

    def td3(obs):
        with torch.no_grad():
            return actor(torch.as_tensor(np.asarray(obs, np.float32)[None]))[0].numpy()

    out = {'env': env_id, 'actor': pt, 'reward_version': rv, 'env_version': ev, 'episodios': n,
           'limites': [np.asarray(env.unwrapped._bounds, float).round(2).tolist()]}
    for nome, pol in (('td3', td3), ('aleatoria', lambda obs: env.action_space.sample())):
        eps = [episodio(env, pol, s) for s in range(n)]
        out[nome] = eps
        mot = {}
        for e in eps:
            mot[e['motivo']] = mot.get(e['motivo'], 0) + 1
        print(nome, json.dumps({'motivos': mot, 'retorno': round(float(np.mean([e['retorno'] for e in eps])), 2),
                                'passos': float(np.median([e['passos'] for e in eps]))}), flush=True)
    env.close()
    with open(saida, 'w') as f:
        json.dump(out, f)
    print('salvo', saida)


if __name__ == '__main__':
    main()
