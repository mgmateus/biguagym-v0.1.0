#!/usr/bin/env bash
# Smoke dos HydroneGoto no cluster2 com medição de memória, antes da fila longa: um ambiente por vez, cada um no seu
# grupo de processos, preso a uma GPU como na fila (CUDA_VISIBLE_DEVICES + nvidia-smi falso, ver fila_cluster.sh).
# A cada 5 s grava a RAM do grupo (soma do RSS: python + simulador), a RAM disponível e a VRAM por GPU; no fim imprime
# o pico. Motivo: no lab o -v2 (sonar) derrubou a memória disponível em ~19 GB (specs/hydrone-goto-dique/log.md,
# 2026-11-19), e o MIN_RAM_MB/WORKERS da fila dependem desse número.
#
# Uso (no cluster2, na raiz do repositório):
#   nohup bash tools/smoke_ram_cluster.sh > ~/smoke_ram.log 2>&1 < /dev/null &
set -uo pipefail

REPO=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
PY=${PY:-$HOME/venv-biguagym/bin/python}
GPU=${GPU:-1}
STEPS=${STEPS:-300}
ENVS=${ENVS:-"HydroneGotoPilares-v2 HydroneGotoPilares-v1 HydroneGotoPilares-v0"}
OUT=${OUT:-$REPO/smoke_results/cluster}
SIM_RE='Binaries/Linux/Holodeck'
REAL_SMI=$(command -v nvidia-smi)

cd "$REPO"
mkdir -p "$OUT/bin"
cat > "$OUT/bin/nvidia-smi" <<EOF
#!/bin/sh
exec "$REAL_SMI" -i $GPU "\$@"
EOF
chmod +x "$OUT/bin/nvidia-smi"

echo "$(date +%T) git $(git --no-pager log --oneline -1 | cut -c1-60) | submódulo $(git -C biguagym --no-pager log --oneline -1 | cut -c1-60)"
echo "$(date +%T) GPU $GPU, $STEPS passos; disponível $(free -m | awk '/^Mem:/{print $7}') MB; simuladores $(pgrep -c -f "$SIM_RE")"
"$REAL_SMI" --query-gpu=index,memory.used,memory.total,utilization.gpu --format=csv,noheader

for env in $ENVS; do
    csv=$OUT/mem_$env.csv
    echo "hora,rss_grupo_mb,disponivel_mb,vram_mib_por_gpu" > "$csv"
    echo "$(date +%T) início $env"
    ini=$(date +%s)
    PATH="$OUT/bin:$PATH" CUDA_VISIBLE_DEVICES=$GPU setsid "$PY" smoke_test.py --env "$env" --steps "$STEPS" \
        --frame-every 100 --out "$OUT" > "$OUT/saida_$env.log" 2>&1 &
    pid=$!
    sleep 1; pg=$(ps -o pgid= -p $pid | tr -d ' ')
    while kill -0 $pid 2>/dev/null; do
        rss=$(ps -o rss= -g "$pg" 2>/dev/null | awk '{s+=$1} END {print int(s/1024)}')
        echo "$(date +%T),$rss,$(free -m | awk '/^Mem:/{print $7}'),$("$REAL_SMI" --query-gpu=memory.used --format=csv,noheader,nounits | tr '\n' ' ' | sed 's/ $//')" >> "$csv"
        sleep 5
    done
    wait $pid; rc=$?
    sleep 5
    sobra=$(pgrep -g "$pg" | wc -l)
    pico=$(tail -n +2 "$csv" | sort -t, -k2 -n | tail -1)
    echo "$(date +%T) fim $env: exit $rc, $(( $(date +%s) - ini )) s, pico (hora,rss_grupo_mb,disponivel_mb,vram) $pico, processos do grupo ao fim $sobra"
    grep -E '"(steps_per_s|hours_per_100k|obs_in_space|nan_obs|inf_obs)"' "$OUT/$env/summary.json" 2>/dev/null | tr -s ' \n' ' '; echo
    tail -3 "$OUT/saida_$env.log"
done
echo "$(date +%T) simuladores no fim: $(pgrep -c -f "$SIM_RE")"
echo FIM_SMOKE_RAM
