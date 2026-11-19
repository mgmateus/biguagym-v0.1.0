#!/usr/bin/env bash
# Piloto de treino do HydroneGoto (antes dos runs longos no cluster): um run por vez, curto, para ver se o treino
# completa sem erro e sem simulador órfão e para medir passos/s com o agente aprendendo.
#   HydroneGotoPilares-v1 + cuprl (RGB + profundidade, como o Depth-CUPRL)
#   HydroneGotoPilares-v2 + td3   (LiDAR + sonar)
# learning_starts=1000 nos dois: o padrão do td3 (25000) passa do tamanho do piloto e ele nunca atualizaria a rede.
#
# O PC do lab é dividido com os treinos do TCC: um run por vez, e o run é encerrado se a memória disponível
# (coluna available do free) cair abaixo de MIN_DISP_MB (pedido da sessão "tcc", 2026-11-19).
#
# Uso (na raiz do repositório, no lab):  nohup bash tools/piloto_goto_lab.sh > ~/piloto_goto.log 2>&1 &
set -uo pipefail

REPO=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
PY=${PY:-$HOME/venv-biguagym/bin/python}
OUT=${OUT:-$REPO/treinos/piloto_goto}
STEPS=${STEPS:-20000}
MIN_DISP_MB=${MIN_DISP_MB:-5120}
TIMEOUT=${TIMEOUT:-18000}            # 5 h por run
SIM_RE='Binaries/Linux/Holodeck'
RUNS=${RUNS:-"HydroneGotoPilares-v1:cuprl HydroneGotoPilares-v2:td3"}

mkdir -p "$OUT"
cd "$REPO"
echo "$(date +%T) git $(git log --oneline -1 | cut -c1-60) | submódulo $(git -C biguagym log --oneline -1 | cut -c1-60)"

disp_mb() { free -m | awk '/^Mem:/{print $7}'; }

for par in $RUNS; do
    env=${par%%:*}; agent=${par##*:}
    d=$OUT/${env}_${agent}; mkdir -p "$d/curves" "$d/logs"   # o run.py não cria a pasta das curvas
    echo "$(date +%T) início $env ($agent), $STEPS passos, disponível $(disp_mb) MB, simuladores $(pgrep -c -f "$SIM_RE")"
    ini=$(date +%s)
    (
        cd "$d" && rm -f crash.log fault.log
        setsid --wait bash -c 'echo $$ > "$1"; shift; exec "$@"' _ "$d/pgid" \
            timeout -k 60 "$TIMEOUT" "$PY" "$REPO/run.py" hydra/launcher=basic env="$env" agent="$agent" \
            num_train_steps="$STEPS" runs=1 eval_freq=10000 num_eval_episodes=1 agent.learning_starts=1000 \
            curves_path="$d/curves" logs_path="$d/logs" > "$d/saida.log" 2>&1
    ) &
    sub=$!
    sleep 5; pg=$(cat "$d/pgid" 2>/dev/null)
    motivo=""
    while kill -0 $sub 2>/dev/null; do
        disp=$(disp_mb)
        echo "$(date +%F_%T),$disp,$(pgrep -c -f "$SIM_RE")" >> "$d/memoria.csv"
        if [ "$disp" -lt "$MIN_DISP_MB" ]; then
            motivo="memória disponível $disp MB < $MIN_DISP_MB MB"
            echo "$(date +%T) $env: $motivo; encerrando o grupo $pg"
            pkill -TERM -g "$pg"; sleep 20; pkill -KILL -g "$pg" 2>/dev/null
            break
        fi
        sleep 20
    done
    wait $sub; rc=$?
    sleep 5
    sobra=0; [ -n "$pg" ] && sobra=$(pgrep -g "$pg" | wc -l)
    [ "$sobra" -gt 0 ] && { pkill -TERM -g "$pg"; sleep 10; pkill -KILL -g "$pg" 2>/dev/null; }
    min=$(( ($(date +%s) - ini) / 60 ))
    echo "$(date +%T) fim $env: exit $rc, $min min, processos do grupo ao fim $sobra${motivo:+, parado: $motivo}"
    grep -v -i -E "warn|deprecat|cross" "$d/saida.log" | tail -8
    [ -n "$motivo" ] && break
done
echo "$(date +%T) simuladores no fim: $(pgrep -c -f "$SIM_RE") (os da tcc incluídos)"
echo FIM_PILOTO
