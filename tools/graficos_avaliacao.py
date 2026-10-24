"""Gráficos e tabela da avaliação (saídas JSON de tools/avaliar_politica.py), TD3 contra aleatória nos mesmos alvos.

Uso: python tools/graficos_avaliacao.py <pasta_com_json> <pasta_saida>
Gera: motivos.png (motivo de término), distancias.png (distância ao alvo), trajetorias.png (XY), tabela.md
"""
import glob, json, os, sys
import numpy as np

CORES = {'success': '#2a9d3f', 'timeout': '#8d99ae', 'strayed': '#e9c46a', 'tilt': '#d62828',
         'out_of_bounds': '#f77f00', 'hard_landing': '#6a4c93', 'hard_dock': '#6a4c93'}


def nome(env):
    return env.replace('-v0', '').replace('TrajectoryFollower', 'Traj')


def carregar(pasta):
    return sorted((json.load(open(f)) for f in glob.glob(os.path.join(pasta, '*.json'))), key=lambda d: d['env'])


def resumo(eps):
    mot = {}
    for e in eps:
        mot[e['motivo']] = mot.get(e['motivo'], 0) + 1
    fin = lambda k: [e[k] for e in eps if e.get(k) is not None]
    return {'n': len(eps), 'motivos': mot, 'sucesso': mot.get('success', 0) / len(eps),
            'retorno': np.mean(fin('retorno')), 'passos': np.median(fin('passos')),
            'd_ini': np.mean(fin('d_ini')) if fin('d_ini') else None,
            'd_fim': np.mean(fin('d_fim')) if fin('d_fim') else None,
            'd_min': np.mean(fin('d_min')) if fin('d_min') else None,
            'progresso': np.mean(fin('progresso')),
            'desvio_acao_entre_eps': float(np.mean(np.std([e['acao_media'] for e in eps], axis=0))),
            'frac_saturada': np.mean(fin('frac_saturada'))}


def tabela(dados, saida):
    f = lambda x, p=2: '–' if x is None else f'{x:.{p}f}'
    lin = ['| Ambiente | Política | Sucesso | Motivos | Retorno | Passos (med.) | d ini → fim (min) | Progresso | '
           'Ação satur. | Variação da ação entre eps |', '|' + '---|' * 10]
    for d in dados:
        for pol in ('td3', 'aleatoria'):
            r = resumo(d[pol])
            mot = ', '.join(f'{k} {v}' for k, v in sorted(r['motivos'].items(), key=lambda kv: -kv[1]))
            dist = '–' if r['d_ini'] is None else f"{f(r['d_ini'])} → {f(r['d_fim'])} ({f(r['d_min'])})"
            lin.append(f"| {nome(d['env'])} | {pol} | {r['sucesso']:.0%} | {mot} | {f(r['retorno'], 1)} | "
                       f"{r['passos']:.0f} | {dist} | {f(r['progresso'])} | {f(r['frac_saturada'])} | "
                       f"{f(r['desvio_acao_entre_eps'], 3)} |")
    open(os.path.join(saida, 'tabela.md'), 'w').write('\n'.join(lin) + '\n')
    print('\n'.join(lin))


def graf_motivos(dados, saida, plt):
    fig, ax = plt.subplots(figsize=(11, 4))
    motivos = sorted({e['motivo'] for d in dados for p in ('td3', 'aleatoria') for e in d[p]}, key=str)
    xs, rot = [], []
    for i, d in enumerate(dados):
        for j, pol in enumerate(('td3', 'aleatoria')):
            x = i * 3 + j; xs.append(x); rot.append(f"{nome(d['env'])}\n{'TD3' if pol == 'td3' else 'aleat.'}")
            base = 0
            for m in motivos:
                v = sum(e['motivo'] == m for e in d[pol]) / len(d[pol])
                ax.bar(x, v, bottom=base, color=CORES.get(m, '#bbbbbb'), edgecolor='white', lw=.5,
                       label=m if (i == 0 and j == 0) or False else None)
                base += v
    for m in motivos:   # legenda completa
        ax.bar(0, 0, color=CORES.get(m, '#bbbbbb'), label=str(m))
    h, l = ax.get_legend_handles_labels(); u = dict(zip(l, h))
    ax.legend(u.values(), u.keys(), fontsize=7, ncol=len(u), loc='upper center', bbox_to_anchor=(.5, 1.15))
    ax.set_xticks(xs); ax.set_xticklabels(rot, fontsize=6.5); ax.set_ylabel('fração dos episódios')
    ax.set_ylim(0, 1)
    fig.tight_layout(); fig.savefig(os.path.join(saida, 'motivos.png'), dpi=140); plt.close(fig)


def graf_distancias(dados, saida, plt):
    com = [d for d in dados if d['td3'][0].get('d_ini') is not None]
    if not com:
        return
    fig, axs = plt.subplots(1, len(com), figsize=(2.6 * len(com), 3.2), squeeze=False)
    for ax, d in zip(axs[0], com):
        for j, (pol, c) in enumerate((('td3', 'C0'), ('aleatoria', '0.6'))):
            for e in d[pol]:
                ax.plot([0, 1, 2], [e['d_ini'], e['d_min'], e['d_fim']], color=c, alpha=.5, lw=1,
                        marker='o', ms=2.5, label=('TD3' if pol == 'td3' else 'aleatória') if e is d[pol][0] else None)
        ax.set_xticks([0, 1, 2]); ax.set_xticklabels(['início', 'mínima', 'fim'], fontsize=7)
        ax.set_title(nome(d['env']), fontsize=8); ax.tick_params(labelsize=7)
    axs[0, 0].set_ylabel('distância ao alvo (m)', fontsize=8); axs[0, 0].legend(fontsize=7)
    fig.tight_layout(); fig.savefig(os.path.join(saida, 'distancias.png'), dpi=140); plt.close(fig)


def graf_trajetorias(dados, saida, plt):
    fig, axs = plt.subplots(2, len(dados), figsize=(2.6 * len(dados), 5.4), squeeze=False)
    for i, d in enumerate(dados):
        for row, pol in enumerate(('td3', 'aleatoria')):
            ax = axs[row, i]
            lo, hi = np.asarray(d['limites'][0])
            ax.add_patch(plt.Rectangle(lo[:2], *(hi[:2] - lo[:2]), fill=False, ls='--', lw=.6, color='0.5'))
            for k, e in enumerate(d[pol]):
                t = np.asarray(e['traj'])
                c = f'C{k % 10}'
                ax.plot(t[:, 0], t[:, 1], color=c, lw=.9, alpha=.8)
                ax.plot(*t[0, :2], 'o', color=c, ms=2.5)
                if e.get('alvo'):
                    ax.plot(*e['alvo'][:2], 'x', color=c, ms=5, mew=1.3)
            ax.set_aspect('equal'); ax.tick_params(labelsize=6)
            ax.set_title(f"{nome(d['env'])} — {'TD3' if pol == 'td3' else 'aleatória'}", fontsize=7.5)
    fig.suptitle('Trajetórias XY (o = início, x = alvo da mesma cor; tracejado = limites)', fontsize=9)
    fig.tight_layout(); fig.savefig(os.path.join(saida, 'trajetorias.png'), dpi=140); plt.close(fig)


def main():
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    pasta, saida = sys.argv[1], sys.argv[2]
    os.makedirs(saida, exist_ok=True)
    dados = carregar(pasta)
    tabela(dados, saida)
    graf_motivos(dados, saida, plt)
    graf_distancias(dados, saida, plt)
    graf_trajetorias(dados, saida, plt)
    print('gráficos em', saida)


if __name__ == '__main__':
    main()
