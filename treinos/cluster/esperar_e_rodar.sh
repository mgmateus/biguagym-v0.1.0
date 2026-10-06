#!/usr/bin/env bash
# PC do laboratório: espera os treinos do TCC liberarem a máquina, verifica e só então inicia a fila de 100k.
#
# 1. Espera: nenhum processo CUDA na GPU (nvidia-smi --query-compute-apps) e RAM disponível >= MIN_RAM_MB,
#    as duas coisas por OCIOSO_S segundos seguidos (padrão 15 min; o TCC pode lançar seeds em sequência).
# 2. Roda treinos/cluster/verificar_cluster.sh (smoke v0/v1/v2 + pilotos TD3 e CUPRL).
# 3. Decide:
#    - algum smoke de v0 ou v2, ou o piloto TD3, falhou → NÃO inicia a fila (veja verificacao/relatorio.txt);
#    - o piloto CUPRL (ou o smoke do v1) falhou → inicia a fila sem os v1 (runs_sem_v1.csv);
#    - WORKERS = min(3, VRAM livre / 5000 MiB, RAM disponível / 11000 MiB), no mínimo 1.
# 4. Inicia a fila_cluster.sh (que já pula o que tem .ok).
# Tudo é registrado em treinos/cluster/saida/espera.log.
#
# Uso (no PC do lab, uma vez):
#   nohup setsid systemd-inhibit --what=sleep:idle:handle-lid-switch --why="treinos 100k" \
#       bash treinos/cluster/esperar_e_rodar.sh > /dev/null 2>&1 < /dev/null &
# Acompanhar: tail -f treinos/cluster/saida/espera.log      Cancelar: kill -TERM -$(cat treinos/cluster/saida/espera.pgid)
set -uo pipefail
export GIT_PAGER=cat PAGER=cat

REPO=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
CL=$REPO/treinos/cluster
OUT=${OUT:-$CL/saida}
MIN_RAM_MB=${MIN_RAM_MB:-20000}
OCIOSO_S=${OCIOSO_S:-900}
INTERVALO=${INTERVALO:-60}
VERIFICAR=${VERIFICAR:-"bash $CL/verificar_cluster.sh"}
FILA=${FILA:-"$CL/fila_cluster.sh"}
REL=${REL:-$CL/verificacao/relatorio.txt}

mkdir -p "$OUT"
LOG=$OUT/espera.log
ps -o pgid= $$ | tr -d ' ' > "$OUT/espera.pgid"
log() { echo "$(date '+%F %T') $*" | tee -a "$LOG"; }

ram_mb() { awk '/^MemAvailable:/{print int($2/1024)}' /proc/meminfo; }
procs_gpu() { nvidia-smi --query-compute-apps=pid --format=csv,noheader 2>/dev/null | grep -c . || true; }
vram_livre() { nvidia-smi --query-gpu=memory.free --format=csv,noheader,nounits | head -1 | tr -d ' '; }

# ---------------------------------------------------------------- 1. espera
log "esperando a GPU sem processos CUDA e RAM >= ${MIN_RAM_MB} MiB por ${OCIOSO_S} s seguidos"
livre_s=0; ultimo=""; ultima_hora=""
while :; do
    n=$(procs_gpu); r=$(ram_mb)
    if [ "$n" -eq 0 ] && [ "$r" -ge "$MIN_RAM_MB" ]; then marca=livre; else marca=ocupado; livre_s=0; fi
    # registra quando muda de estado e uma vez por hora
    if [ "$marca" != "$ultimo" ] || [ "$(date +%H)" != "$ultima_hora" ]; then
        log "$marca (procs_gpu=$n ram_mb=$r, livre há ${livre_s} s de ${OCIOSO_S})"; ultima_hora=$(date +%H)
    fi
    ultimo=$marca
    [ "$marca" = livre ] && [ "$livre_s" -ge "$OCIOSO_S" ] && break
    sleep "$INTERVALO"
    [ "$marca" = livre ] && livre_s=$((livre_s + INTERVALO))
done
log "máquina livre: $(procs_gpu) processos na GPU, RAM $(ram_mb) MiB, VRAM livre $(vram_livre) MiB"

# ---------------------------------------------------------------- 2. verificação
log "rodando a verificação ($VERIFICAR)"
$VERIFICAR > "$OUT/verificacao_stdout.log" 2>&1
log "verificação terminou (exit $?); relatório: $REL"

# ---------------------------------------------------------------- 3. decisão
ok_smoke() { grep -q "^$1: ok " "$REL"; }
ok_piloto() { grep -q "^$1: exit=0 " "$REL"; }
if ! ok_smoke DjiMatriceNav-v0 || ! ok_smoke BlueBoatTrajectoryFollower-v2 || ! ok_piloto "td3 DjiMatriceNav-v2"; then
    log "NÃO iniciei a fila: smoke v0/v2 ou piloto TD3 falhou. Mande $REL para análise."
    grep -E "^(DjiMatriceNav-v0|DjiMatriceNav-v1|BlueBoatTrajectoryFollower-v2):|^(td3|cuprl) " "$REL" | tee -a "$LOG"
    exit 1
fi
RUNS=$CL/runs.csv
if ! ok_smoke DjiMatriceNav-v1 || ! ok_piloto "cuprl DjiMatriceNav-v1"; then
    grep -v -E -- "-v1,cuprl," "$CL/runs.csv" > "$CL/runs_sem_v1.csv"
    RUNS=$CL/runs_sem_v1.csv
    log "CUPRL/v1 falhou na verificação: fila SEM os v1 ($(($(wc -l < "$RUNS") - 1)) runs, $RUNS)"
fi
v=$(vram_livre); r=$(ram_mb)
w=$(( v / 5000 )); [ $(( r / 11000 )) -lt "$w" ] && w=$(( r / 11000 ))
[ "$w" -gt 3 ] && w=3; [ "$w" -lt 1 ] && w=1
WORKERS=${WORKERS:-$w}
log "iniciando a fila: WORKERS=$WORKERS (VRAM livre $v MiB, RAM $r MiB), runs=$RUNS"

# ---------------------------------------------------------------- 4. fila
RUNS=$RUNS WORKERS=$WORKERS bash "$FILA" > "$OUT/fila.log" 2>&1
log "fila terminou (exit $?). Resumo em $OUT/estado.csv"
