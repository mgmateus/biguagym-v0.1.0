#!/usr/bin/env bash
# Roda NO NOTEBOOK (na rede da universidade): envia ao cluster2 as curvas e os logs dos runs de seed 0 que a fila do
# notebook (treinos/100k) já concluiu. No cluster, os seeds 1 e 2 desses ambientes ficam esperando essas curvas
# (fila_cluster.sh, curva_externa_pronta).
#
# - Só envia runs com .ok e sem PULADO (os pulados não rodaram no notebook).
# - Nunca sobrescreve no cluster (--ignore-existing): lá, a mesma curva recebe os seeds 1 e 2.
# - Pode ser rodado quantas vezes quiser, por exemplo uma vez por dia.
set -euo pipefail

REPO=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
NB=$REPO/treinos/100k
JUMP=${JUMP:-teteu@10.230.108.173}
DEST=${DEST:-teteu@cluster2}
RDIR=${RDIR:-biguagym-v0.1.0/treinos/cluster/saida}
STEPS=${STEPS:-100000}
SSH="ssh -J $JUMP"

ssh -J "$JUMP" "$DEST" "mkdir -p $RDIR/curves $RDIR/logs/td3-state"
for d in "$NB"/runs/*_s0; do
    [ -e "$d/.ok" ] && [ ! -e "$d/PULADO" ] || continue
    env=$(basename "$d"); env=${env%_s0}
    c="$NB/curves/td3-state-${env//-/_}.csv"
    # confere que a curva termina no seed 0 completo
    tail -1 "$c" | awk -F, -v n="$STEPS" '{ exit !($5 == 0 && $6 + 1 >= n) }' \
        || { echo "pulando $env: curva incompleta ($c)"; continue; }
    rsync -a --ignore-existing -e "$SSH" "$c" "$DEST:$RDIR/curves/"
    rsync -a --ignore-existing -e "$SSH" "$NB/logs/td3-state/$env" "$DEST:$RDIR/logs/td3-state/"
    echo "enviado: $env (seed 0)"
done
