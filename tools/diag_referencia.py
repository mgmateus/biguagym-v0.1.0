"""Diagnóstico: retorno de políticas fixas de referência (um ambiente por processo, limitado por episódios).
Políticas: parado, girar (motores opostos no limite), aleatória e um controlador "aponta e acelera".
As 4 veem os mesmos alvos (o rng do alvo é refeito com a semente do episódio antes de cada reset).
Uso: python tools/diag_referencia.py <env_id> [episodios=6] [env_version=v1]"""
import collections, json, os, sys
import numpy as np

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def controlador(pos, yaw, alvo, lo, hi):
    """'Aponta e acelera' em rad/s (motor 1 = bombordo, y > 0; motor 2 = boreste).
    Guinada positiva (esquerda) pede o motor de boreste mais forte que o de bombordo."""
    d = np.asarray(alvo[:2], float) - np.asarray(pos[:2], float)
    erro = np.arctan2(d[1], d[0]) - yaw
    erro = (erro + np.pi) % (2 * np.pi) - np.pi
    frente = np.clip(40.0 * np.linalg.norm(d), 0, 150) * max(np.cos(erro), 0.0)  # freia perto e desalinhado
    giro = np.clip(120.0 * erro, -150, 150)
    return np.clip([frente - giro, frente + giro], lo, hi).astype(np.float32)


def main():
    sys.path.insert(0, os.path.join(REPO, 'biguagym'))
    import gymnasium as gym
    import register  # noqa: F401

    env_id = sys.argv[1]
    n_ep = int(sys.argv[2]) if len(sys.argv) > 2 else 6
    versao = sys.argv[3] if len(sys.argv) > 3 else 'v1'
    env = gym.make(env_id, reward_version='v1', env_version=versao)
    u = env.unwrapped
    # Limites reais dos motores (rad/s), mesmo quando o espaço de ação é normalizado.
    dyn = u._env._dynamics_dict['robot'].params
    lo, hi = float(dyn['rotor_speed_min']), float(dyn['rotor_speed_max'])
    normalizada = float(env.action_space.high[0]) == 1.0 and hi != 1.0

    def acao(rad_s):
        a = np.asarray(rad_s, np.float32)
        if normalizada:  # inverso do _to_motor_speeds da v2
            a = np.where(a >= 0, a / hi, -a / lo).astype(np.float32)
        return a

    politicas = {
        'parado': lambda: acao([0.0, 0.0]),
        'girar': lambda: acao([hi, lo]),
        'aleatoria': lambda: env.action_space.sample(),
        'controlador': lambda: acao(controlador(u._dynamics[6:9], float(u._dynamics[17]), u._target, lo, hi)),
    }
    out = {'env': env_id, 'env_version': versao, 'episodios': n_ep, 'motores_rad_s': [lo, hi],
           'acao_normalizada': normalizada}
    for nome, pol in politicas.items():
        rets, motivos, passos, d0s, dfs, alvos = [], collections.Counter(), [], [], [], []
        for s in range(n_ep):
            u.rng = np.random.default_rng(1000 + s)
            env.action_space.seed(1000 + s)
            env.reset()
            alvos.append([round(float(v), 2) for v in u._target])
            d0s.append(float(np.linalg.norm(np.asarray(u._target) - np.asarray(u._dynamics[6:9]))))
            ret, k = 0.0, 0
            while True:
                _, r, term, trunc, info = env.step(pol())
                ret += float(r); k += 1
                if term or trunc:
                    break
            rets.append(ret); passos.append(k); motivos[info.get('termination_reason')] += 1
            dfs.append(float(np.linalg.norm(np.asarray(u._target) - np.asarray(u._dynamics[6:9]))))
        out[nome] = {'retorno_medio': round(float(np.mean(rets)), 2), 'retornos': [round(x, 1) for x in rets],
                     'motivos': dict(motivos), 'passos_med': float(np.median(passos)),
                     'dist_ini_media': round(float(np.mean(d0s)), 2), 'dist_fim_media': round(float(np.mean(dfs)), 2)}
        if nome == 'parado':
            out['alvos'] = alvos
        print(f"{nome}: {json.dumps(out[nome])}", flush=True)
    env.close()
    print('REF ' + json.dumps(out))


if __name__ == '__main__':
    main()
