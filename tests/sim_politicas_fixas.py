"""T12 (spec recompensas): retorno de políticas fixas COM o simulador, nas recompensas v0 e v1.

Um caso por processo (o close() não encerra o simulador). Sem argumentos, roda todos os casos em subprocessos e
imprime a tabela; com argumentos, roda um caso e imprime uma linha JSON.

Casos:
  BlueBoatTrajectoryFollower-v0, controle cmd_pos_yaw (a ação é um ponto-alvo):
      parado  → o alvo é a posição inicial (fica sobre o começo do caminho)
      segue   → o alvo é o waypoint ~1,5 m à frente no caminho do próprio ambiente
  DjiMatriceHover-v0:
      hover   → cmd_pos_yaw com alvo = posição inicial (o controlador mantém o drone parado no ar)
      tomba   → cmd_motor_speeds com rotores máximos de um lado e mínimos do outro
"""
import json
import os
import subprocess
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CASOS = [('BlueBoatTrajectoryFollower-v0', 'parado'), ('BlueBoatTrajectoryFollower-v0', 'segue'),
         ('DjiMatriceHover-v0', 'hover'), ('DjiMatriceHover-v0', 'tomba')]


def um_caso(env_id, politica, versao, max_passos):
    import numpy as np
    import gymnasium as gym
    sys.path.insert(0, os.path.join(REPO, 'biguagym'))
    import register  # noqa: F401  (registra os ids)

    controle = 'cmd_motor_speeds' if politica == 'tomba' else 'cmd_pos_yaw'
    env = gym.make(env_id, control_abstraction=controle, reward_version=versao)
    env.reset(seed=0)
    u = env.unwrapped
    n = int(np.prod(env.action_space.shape))
    pos0 = np.asarray(u._dynamics[6:9], dtype=float).copy()

    def acao():
        a = np.zeros(n, dtype=np.float32)
        if politica in ('parado', 'hover'):
            a[:3] = pos0[:3] if n >= 3 else 0
            a[:2] = pos0[:2]
        elif politica == 'segue':
            seg = float(np.mean(np.linalg.norm(np.diff(u.trajectory, axis=0), axis=1)))
            k = max(1, int(np.ceil(1.5 / max(seg, 1e-6))))
            alvo = u.trajectory[min(u._wp_idx + k, u.n_wp - 1)]
            a[:2] = alvo[:2]
            if n >= 3:
                a[2] = alvo[2]
        elif politica == 'tomba':
            hi, lo = float(env.action_space.high[0]), float(env.action_space.low[0])
            a[:] = [hi if i < n // 2 else max(lo, 0.0) for i in range(n)]
        return a

    total, passos, info, term, trunc = 0.0, 0, {}, False, False
    termos = {}
    while passos < max_passos and not (term or trunc):
        _, r, term, trunc, info = env.step(acao())
        total += float(r)
        passos += 1
        for k_, v in (info.get('reward_terms') or {}).items():
            termos[k_] = termos.get(k_, 0.0) + float(v)
    pos = np.asarray(u._dynamics[6:9], dtype=float)
    print('RESULTADO ' + json.dumps({
        'env': env_id, 'politica': politica, 'versao': versao, 'controle': controle, 'passos': passos,
        'retorno': round(total, 3), 'terminated': bool(term), 'truncated': bool(trunc),
        'motivo': info.get('termination_reason'), 'tem_reward_terms': 'reward_terms' in info,
        'progresso': round(float(info.get('progress', float('nan'))), 3) if 'progress' in info else None,
        'deslocamento_m': round(float(np.linalg.norm(pos - pos0)), 2),
        'termos': {k_: round(v, 2) for k_, v in termos.items()},
    }))
    # saída normal: o atexit do biguasim (__on_exit__) encerra o simulador deste processo


def main():
    if len(sys.argv) > 1:
        return um_caso(sys.argv[1], sys.argv[2], sys.argv[3], int(sys.argv[4]))
    res = []
    for env_id, pol in CASOS:
        for versao in ('v0', 'v1'):
            p = subprocess.run([sys.executable, os.path.abspath(__file__), env_id, pol, versao, '600'],
                               capture_output=True, text=True, timeout=900, cwd=REPO)
            linha = next((l for l in p.stdout.splitlines() if l.startswith('RESULTADO ')), None)
            if linha is None:
                print(f'ERRO {env_id} {pol} {versao}: exit {p.returncode}\n{(p.stderr or p.stdout)[-1500:]}')
                continue
            r = json.loads(linha[len('RESULTADO '):])
            res.append(r)
            print(f"{r['env']:30s} {r['politica']:7s} {r['versao']} | retorno {r['retorno']:9.2f} | {r['passos']:3d} passos | "
                  f"motivo {r['motivo']} | progresso {r['progresso']} | desloc {r['deslocamento_m']} m | termos {r['termos']}")
    json.dump(res, open(os.path.join(REPO, 'smoke_results', 't12_politicas_fixas.json'), 'w'), indent=1)


if __name__ == '__main__':
    main()
