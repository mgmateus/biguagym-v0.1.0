# Treinos de 100k passos no cluster2

72 runs: os 24 ambientes v0/v1/v2 que rodam no BiguaSim 1.0.0, sem Hydrone e sem Torpedo, × 3 seeds. A lista está
em `runs.csv`.

**Recompensa:** o cluster usa a recompensa nova (`reward_version="v1"`, padrão do fork depois da spec `recompensas`):
penalidade de −10 ao terminar por falha, bônus fixo de sucesso (+10 Hover/Nav, +20 Land/Dock) e, na Trajectory, pagamento
por waypoint novo.
- A fila do notebook (`treinos/100k`, TD3, seed 0) roda com a recompensa **original** (`v0`, submódulo `32698e5`). Os
  resultados dela são a linha de base e **não** servem de seed 0 para o cluster.
- Por isso os 8 seeds 0 que estavam no notebook voltaram para cá (DjiMatriceNav-v0, DjiMatriceLand-v0,
  DjiMatriceTrajectoryFollower-v0, BlueBoatNav-v0, BlueBoatTrajectoryFollower-v0, BlueROV2Nav-v0, BlueROV2Dock-v0,
  BlueROV2TrajectoryFollower-v0).
- O `enviar_do_notebook.sh` e a espera por curvas externas da `fila_cluster.sh` continuam no repositório, mas não se
  aplicam a esta lista: nenhum run depende de outra máquina.
- **Use o código da branch que tem a spec `recompensas`** (merge na `testes-ambientes` previsto para quando a fila do
  notebook terminar). Confira antes de iniciar: `grep -c reward_version biguagym/core/environments.py` > 0.

- **Agentes:** TD3 para v0/v2. CUPRL para v1, porque o TD3 do harness não aceita observação `Dict`. O CUPRL nunca rodou
  num ambiente real: o piloto da verificação é o primeiro teste.
- **Ficam de fora:** os 8 `BlueROVHeavy*` (o Unreal cai: o binário do mundo não conhece o agente),
  `TorpedoTrajectoryFollower-v0/-v1` (`TypeError` no `clip()`), `DjiMatriceLand-v2` (API ausente no biguasim 1.0.0) e os
  outros 6 Torpedo: o veículo não se move (posição final = inicial em 200 passos aleatórios, em todos os smokes).
- **Ressalvas que valem para os resultados:**
  - os v1 ainda têm o bug do `np.resize` nos pixels (Etapa 6, spec `pipeline-pixels`);
  - com a recompensa original, o TD3 aprendeu a encerrar o episódio em ~3 passos no `DjiMatriceNav-v0` (sem penalidade
    ao terminar). É o que a recompensa `v1` corrige.

## 0. Acesso
O cluster2 só é acessível pela rede da universidade (ou VPN), pelo host de salto:
```bash
ssh -J teteu@10.230.108.173 teteu@cluster2
```

## 1. Copiar o mundo (do notebook, na rede da universidade)
```bash
ssh -J teteu@10.230.108.173 teteu@cluster2 mkdir -p leva
scp -J teteu@10.230.108.173 ~/leva/SkyDive.tar.zst teteu@cluster2:leva/     # 1,3 GB, md5 bd371b06...
```

## 2. Instalar (no cluster2)
```bash
git clone -b testes-ambientes https://github.com/mgmateus/biguagym-v0.1.0.git ~/biguagym-v0.1.0
cd ~/biguagym-v0.1.0
bash setup/instalar_pc_lab.sh
```
O instalador puxa o submódulo de `ttszin/biguagym` e o biguasim de `ttszin/biguasim`, cria `~/venv-biguagym` e extrai o
mundo. Ele precisa de `git`, `gcc`, `zstd` e Python 3.12 (`python3.12` ou `conda`), sem sudo. Se faltar o Python 3.12,
instale o Miniconda no home.

## 3. (Não se aplica) Seeds 0 do notebook
Com a recompensa nova, o cluster roda todos os seeds. O `enviar_do_notebook.sh` só serviria para uma lista que dependa
dos seeds 0 do notebook com a recompensa original. **Não misture as duas recompensas na mesma curva.**

## 4. Verificar (no cluster2, ~20–40 min)
```bash
cd ~/biguagym-v0.1.0 && bash treinos/cluster/verificar_cluster.sh
```
O script mostra GPUs e VRAM, roda o smoke de um v0, um v1 e um v2 sem tela, e faz pilotos de 2000 passos (TD3 em v2,
CUPRL em v1) presos à última GPU. O relatório fica em `treinos/cluster/verificacao/relatorio.txt`: cole-o na conversa
antes de iniciar a fila. Ele decide quantos workers usar e se o CUPRL funciona.

## 5. Iniciar a fila
```bash
cd ~/biguagym-v0.1.0 && mkdir -p treinos/cluster/saida
WORKERS=2 GPUS=0,1 nohup setsid bash treinos/cluster/fila_cluster.sh > treinos/cluster/saida/fila.log 2>&1 < /dev/null &
```
- **`WORKERS`:** runs em paralelo (padrão: 1 por GPU). Cada run deixa 3 simuladores abertos (~4 GB de VRAM; mais nos v1) por
  causa do vazamento do `close()`. Se a verificação mostrar que o Unreal vai sempre para a GPU 0, escolha `WORKERS` pela
  VRAM da GPU 0.
- **`GPUS`:** quais GPUs usar (por exemplo, para deixar livre uma GPU do TCC).
- **`TIMEOUT`:** limite por run, padrão 120 h. Os v2 com sonar rodaram a ~0,6 passos/s no notebook.
- **Ordem:** seed 0 de todos, depois seed 1, depois seed 2. Dentro de cada seed, os mais lentos (sonar) vão primeiro.
- **Retomada:** rodar de novo pula o que tem `.ok`; os runs interrompidos recomeçam. Um run com erro ganha `.erro` e
  bloqueia os seeds seguintes daquele ambiente: apague o `.erro` para tentar de novo.

## 6. Acompanhar e parar
```bash
column -s, -t < treinos/cluster/saida/estado.csv   # runs concluídos (exit, duração)
tail treinos/cluster/saida/fila.log                  # início e fim de cada run
tail treinos/cluster/saida/monitor.csv               # simuladores, VRAM por GPU, RAM (a cada 60 s)
kill -TERM -$(cat treinos/cluster/saida/fila.pgid)   # parar a fila
cat treinos/cluster/saida/runs/*/pgid                # grupos dos runs em andamento (kill -TERM -<pgid>)
```

## 7. Trazer os resultados (do notebook)
```bash
rsync -avz -e "ssh -J teteu@10.230.108.173" teteu@cluster2:biguagym-v0.1.0/treinos/cluster/saida/ ~/biguagym-v0.1.0/treinos/cluster/saida/
```

## Rodar no PC do laboratório (no lugar do cluster2)
A fila e a verificação funcionam em qualquer Linux com GPU NVIDIA. No PC do lab (RTX 4070 Ti, 12 GB, 32 GB de RAM):

1. **Mundo:** `~/leva/SkyDive.tar.zst` (1,3 GB; por exemplo, pela transferência de arquivos do AnyDesk).
2. **Código com a recompensa nova** (branch `spec/recompensas`, até o merge na `testes-ambientes`):
   ```bash
   git clone -b spec/recompensas https://github.com/mgmateus/biguagym-v0.1.0.git ~/biguagym-v0.1.0
   cd ~/biguagym-v0.1.0 && bash setup/instalar_pc_lab.sh
   grep -c reward_version biguagym/core/environments.py      # > 0: recompensa nova
   ```
   Se já existe um `~/biguagym-v0.1.0` antigo: `cd ~/biguagym-v0.1.0 && git fetch && git checkout spec/recompensas &&
   git pull && bash setup/instalar_pc_lab.sh`.
3. **Verificação (~30 min):** `bash treinos/cluster/verificar_cluster.sh`. Mande o `treinos/cluster/verificacao/relatorio.txt`
   antes de iniciar a fila. Ele diz se cabem 2 ou 3 runs em paralelo.
4. **Fila** (2 runs em paralelo; com bloqueio de suspensão, já que é um desktop com sessão gráfica):
   ```bash
   mkdir -p treinos/cluster/saida
   WORKERS=2 nohup setsid systemd-inhibit --what=sleep:idle:handle-lid-switch --why="treinos 100k" \
       bash treinos/cluster/fila_cluster.sh > treinos/cluster/saida/fila.log 2>&1 < /dev/null &
   ```
5. **Não encerre a sessão (logout):** isso mata a fila. Bloquear a tela pode. Para aguentar até um logout:
   `loginctl enable-linger $USER`. Depois de reiniciar o PC, rode o passo 4 de novo: ele pula o que já tem `.ok`.
6. **Acompanhar e parar:** as mesmas instruções da seção 6 acima. Para trazer os resultados: copie
   `treinos/cluster/saida/`.

### PC do laboratório compartilhado com os treinos do TCC (decisão de 2026-10-06: esperar o TCC terminar)
Em vez dos passos 3 e 4 acima, inicie uma vez:
```bash
cd ~/biguagym-v0.1.0 && git pull
nohup setsid systemd-inhibit --what=sleep:idle:handle-lid-switch --why="treinos 100k" \
    bash treinos/cluster/esperar_e_rodar.sh > /dev/null 2>&1 < /dev/null &
```
O `esperar_e_rodar.sh`:
1. espera a GPU ficar sem processos CUDA e com RAM disponível ≥ 20 GB por 15 min seguidos (uma nova seed do TCC zera
   a contagem);
2. roda o `verificar_cluster.sh`;
3. decide:
   - se o smoke de v0/v2 ou o piloto TD3 falhar, **não inicia** a fila e deixa o motivo no log;
   - se o CUPRL/v1 falhar, inicia sem os v1 (`runs_sem_v1.csv`, 45 runs);
4. inicia a `fila_cluster.sh` com `WORKERS` = min(3, VRAM livre/5 GB, RAM/11 GB).

- Acompanhar: `tail -f treinos/cluster/saida/espera.log`.
- Cancelar antes de começar: `kill -TERM -$(cat treinos/cluster/saida/espera.pgid)`.
- Para não matar os treinos do TCC por falta de RAM, **não** rode o `verificar_cluster.sh` à mão enquanto o TCC estiver
  rodando.
