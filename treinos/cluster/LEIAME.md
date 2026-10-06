# Treinos de 100k passos no cluster2

82 runs: os 30 ambientes v0/v1/v2 que rodam no BiguaSim 1.0.0, sem Hydrone, × 3 seeds, menos os 8 seeds 0 da fila do
notebook. A lista está em `runs.csv`.

**Divisão com o notebook:**
- A fila do notebook (`treinos/100k`, TD3, seed 0) faz DjiMatriceNav-v0 (pronto), DjiMatriceLand-v0,
  DjiMatriceTrajectoryFollower-v0, BlueBoatNav-v0, BlueBoatTrajectoryFollower-v0, BlueROV2Nav-v0, BlueROV2Dock-v0 e
  BlueROV2TrajectoryFollower-v0.
- O notebook pula BlueBoatNav-v1 e BlueBoatNav-v2 (marcador `PULADO`): o v1 precisa do CUPRL, e o v2 (sonar) não cabe no
  timeout de 48 h. Esses dois rodam aqui, com todos os seeds.
- No cluster, os seeds 1 e 2 dos 8 ambientes do notebook **esperam** a curva do seed 0 chegar completa em
  `saida/curves` (passo 3). Enquanto isso, a fila segue com o resto.

- **Agentes:** TD3 para v0/v2. CUPRL para v1, porque o TD3 do harness não aceita observação `Dict`. O CUPRL nunca rodou
  num ambiente real: o piloto da verificação é o primeiro teste.
- **Ficam de fora:** os 8 `BlueROVHeavy*` (o Unreal cai: o binário do mundo não conhece o agente),
  `TorpedoTrajectoryFollower-v0/-v1` (`TypeError` no `clip()`) e `DjiMatriceLand-v2` (API ausente no biguasim 1.0.0).
- **Ressalvas que valem para os resultados:**
  - os v1 ainda têm o bug do `np.resize` nos pixels (Etapa 6, spec `pipeline-pixels`);
  - no `DjiMatriceNav-v0` o TD3 aprendeu a encerrar o episódio em ~3 passos, porque a recompensa do `HoverEnv` não tem
    bônus de vida nem penalidade ao terminar. Os outros ambientes aéreos (Hover/Land/Trajectory) herdam essa recompensa.

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

## 3. Enviar os seeds 0 do notebook (do notebook, sempre que um terminar)
```bash
cd ~/biguagym-v0.1.0 && bash treinos/cluster/enviar_do_notebook.sh
```
O script envia só as curvas e os logs dos runs concluídos (`.ok`, curva completa). Ele nunca sobrescreve no cluster, onde
a mesma curva recebe os seeds 1 e 2. Rode-o depois de cada seed 0 do notebook terminar (dá para ver em
`treinos/100k/estado.csv`). Não copie curvas à mão: uma curva parcial ou uma cópia tardia corrompe a do cluster.

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
