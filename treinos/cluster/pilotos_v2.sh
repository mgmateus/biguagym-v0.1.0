#!/usr/bin/env bash
# Pilotos de 15k (spec colapso-blueboat, T13) nos dois ambientes do barco com env_version=v2 (padrão), em paralelo,
# seguidos da avaliação TD3 × aleatória (tools/avaliar_politica.py, 10 episódios, mesmos alvos).
# Uso: nohup setsid bash treinos/cluster/pilotos_v2.sh > treinos/cluster/piloto_v2/pilotos.log 2>&1 < /dev/null &
set -uo pipefail
REPO=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
PY=${PY:-$HOME/venv-biguagym/bin/python}
OUT=${OUT:-$REPO/treinos/cluster/piloto_v2}
STEPS=${STEPS:-15000}
mkdir -p "$OUT/aval" "$OUT/curves" "$OUT/logs"
piloto() {  # $1=ambiente
    local e=$1 d=$OUT/runs/$1
    mkdir -p "$d"
    echo "$(date +%T) início $e"
    (cd "$d" && timeout -k 60 7200 "$PY" "$REPO/run.py" hydra/launcher=basic env="$e" agent=td3 \
        num_train_steps="$STEPS" eval_freq=1000000 num_eval_episodes=1 runs=1 agent.learning_starts=1000 \
        curves_path="$OUT/curves" logs_path="$OUT/logs" > "$d/saida.log" 2>&1)
    local rc=$?
    echo "$(date +%T) fim treino $e exit=$rc"
    [ "$rc" -ne 0 ] && return "$rc"
    (cd "$REPO" && timeout -k 60 3600 "$PY" tools/avaliar_politica.py "$e" \
        "$OUT/logs/td3-state/$e/run_0/models/actor_last.pt" "$OUT/aval/$e.json" 10 v1 v2 > "$OUT/aval/$e.log" 2>&1)
    rc=$?
    echo "$(date +%T) fim avaliação $e exit=$rc"
}
piloto BlueBoatNav-v0 &
sleep 60
piloto BlueBoatTrajectoryFollower-v0 &
wait
echo "$(date +%T) pilotos concluídos; simuladores restantes: $(pgrep -fc 'Binaries/Linux/Holodeck')"
