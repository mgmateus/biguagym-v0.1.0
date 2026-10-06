#!/usr/bin/env bash
# Fila de treinos de 100k passos para o cluster2: todos os ambientes v0/v1/v2 que rodam, sem Hydrone
# (lista em treinos/cluster/runs.csv). Ver treinos/cluster/LEIAME.md.
#
# - WORKERS runs em paralelo (padrão: 1 por GPU). Cada worker:
#     * fica preso a uma GPU (CUDA_VISIBLE_DEVICES) e recebe um nvidia-smi falso no PATH que só mostra essa GPU.
#       Motivo: o gpu() do harness (utils.py) e o do biguasim leem o índice do nvidia-smi, que ignora o
#       CUDA_VISIBLE_DEVICES, e ainda escolhem a GPU com MENOS VRAM livre;
#     * roda num diretório próprio, porque o logger grava crash.log/fault.log no diretório atual.
#   O Unreal não recebe parâmetro de GPU: com várias GPUs, os simuladores podem ir todos para a GPU padrão.
#   Confira com o verificar_cluster.sh antes de usar WORKERS > 1.
# - Um processo run.py por seed (runs=s+1): o close() vaza o simulador (spec vazamento-simulador), então cada
#   processo fica com 3 simuladores abertos (treino + avaliação do passo 0 + avaliação final).
# - Agente: td3 para v0/v2; cuprl para v1 (o TD3 do harness não aceita observação Dict).
# - Um ambiente nunca roda dois seeds ao mesmo tempo (o seed sai do CSV da curva); o seed s só começa
#   depois do s-1 ter .ok (ou se o s-1 não está no runs.csv, ou seja, foi feito em outra máquina).
# - Antes de cada run, confere se o seed que o run.py vai escolher (logger.seed_curves) é o esperado.
#   Se não for, marca erro e não roda (evita rodar dois seeds no mesmo processo).
# - Retomada: rodar de novo pula o que tem .ok. Um run que terminou com erro tem .erro: apague-o para tentar de novo.
#
# Uso:   nohup setsid bash treinos/cluster/fila_cluster.sh > treinos/cluster/saida/fila.log 2>&1 &
# Parar: kill -TERM -$(cat treinos/cluster/saida/fila.pgid)
set -uo pipefail

REPO=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
PY=${PY:-$HOME/venv-biguagym/bin/python}
CL=$REPO/treinos/cluster
OUT=${OUT:-$CL/saida}
RUNS=${RUNS:-$CL/runs.csv}
STEPS=${STEPS:-100000}
TIMEOUT=${TIMEOUT:-432000}          # 120 h por run (sonar: ~0,6 passos/s no notebook → ~48 h só de passos)
NGPU=$(nvidia-smi -L | wc -l)
WORKERS=${WORKERS:-$NGPU}
GPUS=${GPUS:-$(seq -s, 0 $((NGPU - 1)))}   # GPUs usadas, em rodízio entre os workers (ex.: GPUS=1,2)
SIM_RE='Binaries/Linux/Holodeck'
REAL_SMI=$(command -v nvidia-smi)

mkdir -p "$OUT/curves" "$OUT/logs" "$OUT/runs" "$OUT/workers"
cd "$REPO"
ps -o pgid= $$ | tr -d ' ' > "$OUT/fila.pgid"
[ -f "$OUT/estado.csv" ] || echo "ambiente,agente,seed,worker,gpu,inicio,fim,duracao_min,exit,sims_ao_fim" > "$OUT/estado.csv"
LOCK=$OUT/.lock

# Monitor: a cada 60 s, simuladores, VRAM por GPU e RAM livre.
[ -f "$OUT/monitor.csv" ] || echo "hora,simuladores,vram_mib_por_gpu,ram_livre_mib" > "$OUT/monitor.csv"
(
    while true; do
        printf '%s,%s,%s,%s\n' "$(date +%F_%T)" "$(pgrep -c -f "$SIM_RE" || true)" \
            "$("$REAL_SMI" --query-gpu=memory.used --format=csv,noheader,nounits | tr '\n' ' ' | sed 's/ $//')" \
            "$(free -m | awk '/^Mem:/{print $7}')" >> "$OUT/monitor.csv"
        sleep 60
    done
) &
MON=$!
trap 'kill $MON 2>/dev/null; pkill -P $$ 2>/dev/null' EXIT

# Seed que o run.py vai usar para este ambiente/agente (mesma lógica de logger.seed_curves).
seed_previsto() {  # $1=ambiente $2=agente
    "$PY" - "$OUT/curves" "$1" "$2" "$STEPS" <<'EOF'
import os, sys
import pandas as pd
curves, env, agent, steps = sys.argv[1], sys.argv[2], sys.argv[3], int(sys.argv[4])
obs = 'pixel' if env.endswith('-v1') else 'range' if env.endswith('-v2') else 'state'
p = os.path.join(curves, f"{agent.replace('-', '_')}-{obs}-{env.replace('-', '_')}.csv")
if not os.path.isfile(p):
    print(0); sys.exit()
df = pd.read_csv(p)
if len(df) == 0:
    print(0); sys.exit()
last_frame, last_seed = df['frame'].iloc[-1], int(df['seed'].iloc[-1])
print(last_seed if last_frame + 1 < steps else last_seed + 1)
EOF
}

# A curva tem o seed $3 completo como última linha? (frame + 1 >= STEPS, como em logger.seed_curves)
curva_externa_pronta() {  # $1=ambiente $2=agente $3=seed
    local obs=state
    case $1 in *-v1) obs=pixel ;; *-v2) obs=range ;; esac
    local c="$OUT/curves/${2//-/_}-$obs-${1//-/_}.csv"
    [ -f "$c" ] || return 1
    tail -1 "$c" | awk -F, -v s="$3" -v n="$STEPS" '{ exit !($5 == s && $6 + 1 >= n) }'
}

# Escolhe o próximo run livre (com o lock já tomado). Imprime "ambiente,agente,seed" ou nada.
proximo() {
    tail -n +2 "$RUNS" | while IFS=, read -r env agent s; do
        tag="${env}_s$s"; d=$OUT/runs/$tag
        [ -e "$d/.ok" ] || [ -e "$d/.erro" ] || [ -e "$d/.rodando" ] && continue
        ls "$OUT/runs/${env}"_s*/.rodando >/dev/null 2>&1 && continue          # mesmo ambiente em andamento
        if [ "$s" -gt 0 ]; then
            prev="${env},${agent},$((s - 1))"
            if grep -qx "$prev" "$RUNS"; then
                [ -e "$OUT/runs/${env}_s$((s - 1))/.ok" ] || continue
            else
                # Seed anterior feito em outra máquina (fila do notebook): espera a curva dele chegar completa
                # em $OUT/curves (copiada com o rsync do LEIAME).
                curva_externa_pronta "$env" "$agent" $((s - 1)) || continue
            fi
        fi
        echo "$env,$agent,$s"; break
    done
}

worker() {  # $1=id do worker
    local w=$1 gpu
    gpu=$(echo "$GPUS" | cut -d, -f$(( (w % $(echo "$GPUS" | tr , '\n' | wc -l)) + 1 )))
    local wd=$OUT/workers/w$w
    mkdir -p "$wd/bin"
    # nvidia-smi falso: mostra só a GPU deste worker, para o gpu() devolver "0" (= CUDA_VISIBLE_DEVICES).
    cat > "$wd/bin/nvidia-smi" <<EOF
#!/bin/sh
exec "$REAL_SMI" -i $gpu "\$@"
EOF
    chmod +x "$wd/bin/nvidia-smi"
    while true; do
        local linha
        linha=$(flock "$LOCK" bash -c "$(declare -f proximo curva_externa_pronta); OUT='$OUT' RUNS='$RUNS' STEPS='$STEPS'; r=\$(proximo); \
            [ -n \"\$r\" ] && { IFS=, read -r e a s <<< \"\$r\"; mkdir -p \"\$OUT/runs/\${e}_s\$s\"; touch \"\$OUT/runs/\${e}_s\$s/.rodando\"; echo \"\$r\"; }")
        if [ -z "$linha" ]; then
            # Nada livre agora: termina se não há mais nada pendente; senão espera outro worker liberar.
            pend=$(tail -n +2 "$RUNS" | while IFS=, read -r e a s; do
                d=$OUT/runs/${e}_s$s; [ -e "$d/.ok" ] || [ -e "$d/.erro" ] || echo x; done | wc -l)
            rod=$(ls "$OUT"/runs/*/.rodando 2>/dev/null | wc -l)
            [ "$pend" -eq 0 ] && break
            if [ "$rod" -eq 0 ]; then
                # Nada rodando: ou falta a curva de um seed feito no notebook (espera), ou só sobrou bloqueio por erro (sai).
                ext=$(tail -n +2 "$RUNS" | while IFS=, read -r e a s; do
                    d=$OUT/runs/${e}_s$s; [ -e "$d/.ok" ] || [ -e "$d/.erro" ] && continue
                    [ "$s" -gt 0 ] && ! grep -qx "$e,$a,$((s - 1))" "$RUNS" && echo x; done | wc -l)
                if [ "$ext" -eq 0 ]; then
                    echo "$(date +%T) w$w: $pend pendentes bloqueados por seeds anteriores com erro"; break
                fi
                [ $(( $(date +%s) / 60 % 60 )) -eq 0 ] && \
                    echo "$(date +%T) w$w: esperando curvas do notebook em $OUT/curves ($ext runs)"
            fi
            sleep 60; continue
        fi
        IFS=, read -r env agent s <<< "$linha"
        local tag="${env}_s$s" d=$OUT/runs/${env}_s$s
        local prev; prev=$(seed_previsto "$env" "$agent")
        if [ "$prev" != "$s" ]; then
            echo "$(date +%T) w$w: $tag NÃO rodado: o run.py escolheria o seed $prev (curva em $OUT/curves)" | tee "$d/saida.log"
            touch "$d/.erro"; rm -f "$d/.rodando"; continue
        fi
        local ini; ini=$(date +%s)
        echo "$(date +%T) w$w gpu$gpu: início $tag ($agent)"
        (
            cd "$wd" && rm -f crash.log fault.log run.log
            PATH="$wd/bin:$PATH" CUDA_VISIBLE_DEVICES=$gpu \
            setsid --wait bash -c 'echo $$ > "$1"; shift; exec "$@"' _ "$d/pgid" \
                timeout -k 60 "$TIMEOUT" "$PY" "$REPO/run.py" hydra/launcher=basic env="$env" agent="$agent" \
                num_train_steps="$STEPS" runs=$((s + 1)) \
                curves_path="$OUT/curves" logs_path="$OUT/logs" \
                > "$d/saida.log" 2>&1
        )
        local rc=$? pg; pg=$(cat "$d/pgid" 2>/dev/null)
        sleep 5
        local sobra=0
        if [ -n "$pg" ]; then
            sobra=$(pgrep -g "$pg" | wc -l)
            [ "$sobra" -gt 0 ] && { pkill -TERM -g "$pg"; sleep 10; pkill -KILL -g "$pg" 2>/dev/null; }
        fi
        for f in crash.log fault.log run.log; do [ -f "$wd/$f" ] && cp "$wd/$f" "$d/"; done
        local fim; fim=$(date +%s)
        flock "$LOCK" bash -c "echo '$env,$agent,$s,w$w,$gpu,$(date -d @$ini +%F_%T),$(date -d @$fim +%F_%T),$(( (fim - ini) / 60 )),$rc,$sobra' >> '$OUT/estado.csv'"
        echo "$(date +%T) w$w: fim $tag exit=$rc processos_restantes=$sobra"
        if [ $rc -eq 0 ]; then touch "$d/.ok"; else touch "$d/.erro"; fi
        rm -f "$d/.rodando"
    done
    echo "$(date +%T) w$w: sem mais runs"
}

rm -f "$OUT"/runs/*/.rodando          # sobras de uma fila interrompida: esses runs recomeçam do zero
echo "$(date +%T) fila: $(($(wc -l < "$RUNS") - 1)) runs em $RUNS, WORKERS=$WORKERS, GPUS=$GPUS, timeout=${TIMEOUT}s"
for ((w = 0; w < WORKERS; w++)); do
    worker $w &
    sleep 30                            # escalona a criação dos simuladores
done
wait $(jobs -p | grep -v "^$MON$") 2>/dev/null
echo "$(date +%T) fila concluída"
