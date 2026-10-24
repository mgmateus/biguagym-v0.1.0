"""Curvas de aprendizado dos treinos (recompensa por episódio e tamanho do episódio), em blocos de passos.
Mostra se a política sai do patamar da fase aleatória (os primeiros learning_starts passos do TD3 são ações aleatórias).

Uso:
  python tools/curvas_aprendizado.py <pasta_saida> [--bloco 5000] [--aleatorio 25000] [--png fig.png]
      <pasta_saida> tem curves/*.csv e, opcionalmente, logs/*/*/run_0/eval.log (ex.: treinos/cluster/saida_250k)
  python tools/curvas_aprendizado.py <pasta_saida> --exportar blocos.csv   # só o resumo por bloco (arquivo pequeno)
  python tools/curvas_aprendizado.py --blocos blocos.csv [--png fig.png]    # gráfico a partir do resumo
"""
import argparse, glob, json, os
import numpy as np
import pandas as pd


def blocos_de_curvas(pasta, bloco):
    linhas = []
    for c in sorted(glob.glob(os.path.join(pasta, 'curves', '*.csv'))):
        d = pd.read_csv(c)
        d = d[(d['episode'] > 0) & np.isfinite(d['episode_reward'])].copy()
        if d.empty:
            continue
        env = os.path.basename(c).split('-', 2)[2][:-4]
        d['passos'] = d['frame'].diff().fillna(d['frame'])
        d['bloco'] = (d['frame'] // bloco) * bloco
        g = d.groupby('bloco')
        for b, x in g:
            linhas.append({'env': env, 'bloco': int(b), 'n': len(x),
                           'r_media': x['episode_reward'].mean(), 'r_p25': x['episode_reward'].quantile(.25),
                           'r_p75': x['episode_reward'].quantile(.75), 'passos_media': x['passos'].mean()})
    for e in sorted(glob.glob(os.path.join(pasta, 'logs', '*', '*', '*', 'eval.log'))):
        env = e.split(os.sep)[-3].replace('-', '_')
        for line in open(e):
            j = json.loads(line)
            linhas.append({'env': env, 'bloco': -1, 'n': int(j['step']), 'r_media': j['mean_ep_reward'],
                           'r_p25': np.nan, 'r_p75': j['best_ep_reward'], 'passos_media': np.nan})
    return pd.DataFrame(linhas)


def tabela(df, aleatorio):
    out = []
    for env, x in df[df['bloco'] >= 0].groupby('env'):
        fim = x['bloco'].max()
        a = x[x['bloco'] < aleatorio]
        u = x[x['bloco'] >= fim - aleatorio + 1]
        ra = np.average(a['r_media'], weights=a['n']); ru = np.average(u['r_media'], weights=u['n'])
        la = np.average(a['passos_media'], weights=a['n']); lu = np.average(u['passos_media'], weights=u['n'])
        ev = df[(df['env'] == env) & (df['bloco'] == -1)].sort_values('n')['r_media'].tolist()
        out.append({'env': env, 'passos': int(fim + x['bloco'].diff().median()),
                    'R_aleatoria': ra, 'R_final': ru, 'melhora': ru - ra,
                    'passos_ep_aleatoria': la, 'passos_ep_final': lu,
                    'eval_ini': ev[0] if ev else np.nan, 'eval_fim': ev[-1] if len(ev) > 1 else np.nan})
    return pd.DataFrame(out)


def grafico(df, aleatorio, png):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    envs = sorted(df.loc[df['bloco'] >= 0, 'env'].unique())
    fig, axs = plt.subplots(2, len(envs), figsize=(3.2 * len(envs), 5.6), squeeze=False)
    for i, env in enumerate(envs):
        x = df[(df['env'] == env) & (df['bloco'] >= 0)].sort_values('bloco')
        k = x['bloco'] / 1000
        for ax in axs[:, i]:
            ax.axvspan(0, aleatorio / 1000, color='0.9', lw=0)
        axs[0, i].fill_between(k, x['r_p25'], x['r_p75'], alpha=.25)
        axs[0, i].plot(k, x['r_media'], lw=1.4)
        axs[0, i].set_title(env.replace('_v0', '').replace('_', ' '), fontsize=9)
        axs[1, i].plot(k, x['passos_media'], color='C1', lw=1.4)
        axs[1, i].set_xlabel('passos (mil)', fontsize=8)
        for ax in axs[:, i]:
            ax.tick_params(labelsize=7)
            ax.ticklabel_format(axis='y', useOffset=False)
    axs[0, 0].set_ylabel('recompensa por episódio\n(média e p25–p75)', fontsize=8)
    axs[1, 0].set_ylabel('passos por episódio', fontsize=8)
    fig.suptitle(f'TD3, seed 0 — faixa cinza: ações aleatórias (primeiros {aleatorio // 1000}k passos)', fontsize=10)
    fig.tight_layout()
    fig.savefig(png, dpi=130)
    print('figura:', png)


def main():
    p = argparse.ArgumentParser()
    p.add_argument('pasta', nargs='?')
    p.add_argument('--bloco', type=int, default=5000)
    p.add_argument('--aleatorio', type=int, default=25000)
    p.add_argument('--exportar')
    p.add_argument('--blocos')
    p.add_argument('--png')
    a = p.parse_args()
    df = pd.read_csv(a.blocos) if a.blocos else blocos_de_curvas(a.pasta, a.bloco)
    if a.exportar:
        df.to_csv(a.exportar, index=False, float_format='%.5g')
        print('blocos:', a.exportar, len(df), 'linhas')
        return
    with pd.option_context('display.width', 200, 'display.float_format', '{:.3g}'.format):
        print(tabela(df, a.aleatorio).to_string(index=False))
    if a.png:
        grafico(df, a.aleatorio, a.png)


if __name__ == '__main__':
    main()
