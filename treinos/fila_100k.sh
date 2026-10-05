#!/usr/bin/env bash
# Fila de treinos de 100k passos (TD3, 3 seeds) nos ambientes do artigo, sem os do Hydrone.
#
# - Um processo run.py por seed (runs=s+1; o seed vem do CSV da curva, ver logger.seed_curves).
#   Motivo: o close() não encerra o simulador (spec vazamento-simulador), então cada processo acumula
#   treino + avaliação do passo 0 + avaliação final = 3 simuladores (~4 GB). Com runs=3 num processo só,
#   seriam 7 e a VRAM de 6 GB estoura.
# - Ordem: seed 0 de todos os ambientes, depois seed 1, depois seed 2.
# - Retomada: rodar de novo pula os runs com marcador .ok; o seed s só roda se o s-1 terminou.
# - Cada run tem timeout, saída própria, cópia de crash.log/fault.log/run.log (que o logger sobrescreve)
#   e, no fim, encerra o que sobrou no grupo de processos do próprio run.
#
# Uso: nohup setsid bash treinos/fila_100k.sh > treinos/100k/fila.log 2>&1 &
#      parar: kill -TERM -<pgid da fila>   (pgid em treinos/100k/fila.pgid)
set -uo pipefail

REPO=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
PY=${PY:-$HOME/venv-biguagym/bin/python}
OUT=$REPO/treinos/100k
STEPS=${STEPS:-100000}
SEEDS=${SEEDS:-3}
TIMEOUT=${TIMEOUT:-43200}           # 12 h por run (medido ~3,8 passos/s no início do DjiMatriceNav: episódios curtos + reset caro)
ENVS=(
    DjiMatriceNav-v0
    DjiMatriceLand-v0
    DjiMatriceTrajectoryFollower-v0
    BlueBoatNav-v0
    BlueBoatTrajectoryFollower-v0
    BlueROV2Nav-v0
    BlueROV2Dock-v0
    BlueROV2TrajectoryFollower-v0
    BlueBoatNav-v2
    BlueBoatNav-v1                  # pixels: ainda com o bug do np.resize (Etapa 6); por isso fica por último
)
SIM_RE='Binaries/Linux/Holodeck'   # processo do simulador (mesmo padrão de smoke_results/repro_19/monitor.sh)

mkdir -p "$OUT/curves" "$OUT/logs" "$OUT/runs"
cd "$REPO"
echo $$ > "$OUT/fila.pgid"
[ -f "$OUT/estado.csv" ] || echo "ambiente,seed,inicio,fim,duracao_min,exit,sims_ao_fim" > "$OUT/estado.csv"

# Monitor: a cada 60 s, simuladores abertos, VRAM e RAM livre.
[ -f "$OUT/monitor.csv" ] || echo "hora,run,simuladores,vram_mib,ram_livre_mib" > "$OUT/monitor.csv"
(
    while true; do
        printf '%s,%s,%s,%s,%s\n' "$(date +%F_%T)" "$(cat "$OUT/atual" 2>/dev/null)" \
            "$(pgrep -c -f "$SIM_RE" || true)" \
            "$(nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits)" \
            "$(free -m | awk '/^Mem:/{print $7}')" >> "$OUT/monitor.csv"
        sleep 60
    done
) &
MON=$!
trap 'kill $MON 2>/dev/null; rm -f "$OUT/atual"' EXIT

for ((s = 0; s < SEEDS; s++)); do
    for env in "${ENVS[@]}"; do
        tag="${env}_s$s"
        dir=$OUT/runs/$tag
        [ -f "$dir/.ok" ] && continue
        if [ $s -gt 0 ] && [ ! -f "$OUT/runs/${env}_s$((s - 1))/.ok" ]; then
            echo "$(date +%T) pulando $tag: seed $((s - 1)) não terminou"
            continue
        fi
        mkdir -p "$dir"
        echo "$tag" > "$OUT/atual"
        ini=$(date +%s)
        echo "$(date +%T) início $tag"
        rm -f crash.log fault.log
        setsid --wait bash -c 'echo $$ > "$1"; shift; exec "$@"' _ "$dir/pgid" \
            timeout -k 60 "$TIMEOUT" "$PY" run.py hydra/launcher=basic env="$env" agent=td3 \
            num_train_steps="$STEPS" runs=$((s + 1)) \
            curves_path="$OUT/curves" logs_path="$OUT/logs" \
            > "$dir/saida.log" 2>&1
        rc=$?
        pg=$(cat "$dir/pgid")
        sleep 5
        sobra=$(pgrep -g "$pg" | wc -l)
        [ "$sobra" -gt 0 ] && { pkill -TERM -g "$pg"; sleep 10; pkill -KILL -g "$pg" 2>/dev/null; }
        for f in crash.log fault.log run.log; do [ -f "$f" ] && cp "$f" "$dir/"; done
        fim=$(date +%s)
        echo "$env,$s,$(date -d @$ini +%F_%T),$(date -d @$fim +%F_%T),$(( (fim - ini) / 60 )),$rc,$sobra" >> "$OUT/estado.csv"
        echo "$(date +%T) fim $tag exit=$rc processos_restantes=$sobra"
        [ $rc -eq 0 ] && touch "$dir/.ok"
    done
done
echo "$(date +%T) fila concluída"
