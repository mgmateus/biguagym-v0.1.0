"""Figura do artigo: recompensa por episódio ao longo do treino (blocos de 5k passos), um painel por ambiente.
Referência em cada painel: média da fase de ações aleatórias (primeiros learning_starts passos do TD3).

Uso: python tools/figura_recompensa.py <blocos.csv> <saida_sem_extensao> [--aleatorio 25000]
Gera <saida>.png e <saida>.pdf e imprime a variação (média dos últimos 25k − média da fase aleatória).
"""
import argparse
import numpy as np
import pandas as pd

AZUL, TINTA, TINTA2, GRADE, FUNDO_ALEAT = '#2a78d6', '#0b0b0b', '#52514e', '#e4e3df', '#efeeea'


def main():
    p = argparse.ArgumentParser()
    p.add_argument('blocos'); p.add_argument('saida'); p.add_argument('--aleatorio', type=int, default=25000)
    a = p.parse_args()
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt

    df = pd.read_csv(a.blocos)
    df = df[df['bloco'] >= 0]
    linhas = []
    for env, x in df.groupby('env'):
        x = x.sort_values('bloco')
        ale = x[x['bloco'] < a.aleatorio]; fim = x[x['bloco'] >= x['bloco'].max() - a.aleatorio + 1]
        ra = np.average(ale['r_media'], weights=ale['n']); rf = np.average(fim['r_media'], weights=fim['n'])
        linhas.append((env, ra, rf, rf - ra, x))
    linhas.sort(key=lambda t: -t[3] / max(abs(t[1]), 1e-9))   # maior melhora relativa primeiro

    n = len(linhas); cols = 4; rows = int(np.ceil(n / cols))
    plt.rcParams.update({'font.size': 8, 'axes.edgecolor': TINTA2, 'axes.labelcolor': TINTA2,
                         'xtick.color': TINTA2, 'ytick.color': TINTA2})
    fig, axs = plt.subplots(rows, cols, figsize=(7.2, 1.85 * rows + .35), squeeze=False)
    for ax, (env, ra, rf, d, x) in zip(axs.flat, linhas):
        k = x['bloco'] / 1000
        ax.axvspan(0, a.aleatorio / 1000, color=FUNDO_ALEAT, lw=0, zorder=0)
        ax.axhline(ra, color=TINTA2, lw=.8, ls=(0, (3, 2)), zorder=1)
        ax.fill_between(k, x['r_p25'], x['r_p75'], color=AZUL, alpha=.18, lw=0, zorder=2)
        ax.plot(k, x['r_media'], color=AZUL, lw=1.6, zorder=3)
        nome = env.replace('_v0', '').replace('TrajectoryFollower', 'Trajectory')
        ax.set_title(f'{nome}\n{ra:.0f} → {rf:.0f}', fontsize=8, color=TINTA, linespacing=1.3)
        ax.grid(axis='y', color=GRADE, lw=.6); ax.set_axisbelow(True)
        for s in ('top', 'right'):
            ax.spines[s].set_visible(False)
        ax.tick_params(labelsize=7, length=2)
    for ax in axs.flat[n:]:
        ax.axis('off')
    for ax in axs[-1]:
        ax.set_xlabel('passos de treino (mil)')
    for ax in axs[:, 0]:
        ax.set_ylabel('recompensa / episódio')
    fig.tight_layout(h_pad=1.0, w_pad=.8)
    for ext in ('png', 'pdf'):
        fig.savefig(f'{a.saida}.{ext}', dpi=200)
    print('| Ambiente | Fase aleatória (0–25k) | Fim do treino (últimos 25k) | Variação |\n|---|---|---|---|')
    for env, ra, rf, d, _ in linhas:
        print(f'| {env} | {ra:.1f} | {rf:.1f} | {d:+.1f} |')
    print('figura:', a.saida + '.png/.pdf')


if __name__ == '__main__':
    main()
