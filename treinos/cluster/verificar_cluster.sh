#!/usr/bin/env bash
# Verificação no cluster2 antes da fila (rodar depois do setup/instalar_pc_lab.sh). ~20–40 min.
#   1. hardware (GPUs, VRAM, CPU, RAM, disco) e se já há processos de outras pessoas nas GPUs;
#   2. smoke de 200 passos em um ambiente v0, um v1 (câmera) e um v2 (sonar), sem tela (-RenderOffScreen);
#   3. pilotos curtos do caminho de treino (< 5k passos, CLAUDE.md regra 2):
#        TD3 em DjiMatriceNav-v2 (2000 passos) e CUPRL em DjiMatriceNav-v1 (2000 passos; nunca rodado antes);
#   4. em qual GPU o Unreal abre os simuladores (decide se WORKERS > 1 com várias GPUs é seguro).
# Tudo vai para treinos/cluster/verificacao/. Leve o relatorio.txt de volta (ou cole na conversa).
set -uo pipefail

REPO=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
PY=${PY:-$HOME/venv-biguagym/bin/python}
V=$REPO/treinos/cluster/verificacao
REL=$V/relatorio.txt
mkdir -p "$V"
cd "$REPO"
exec > >(tee "$REL") 2>&1

sec() { printf '\n== %s\n' "$*"; }
sims() { pgrep -c -f 'Binaries/Linux/Holodeck' || true; }

sec "1. Máquina ($(hostname), $(date '+%F %T'))"
nvidia-smi --query-gpu=index,name,memory.total,memory.used,utilization.gpu --format=csv
nvidia-smi --query-compute-apps=pid,used_memory --format=csv,noheader | head
echo "CPU: $(nproc) | RAM: $(free -g | awk '/^Mem:/{print $2" GB total, "$7" GB livre"}') | disco: $(df -h "$REPO" | awk 'NR==2{print $4" livre"}')"
echo "DISPLAY='${DISPLAY:-}' | vulkan: $(ls /usr/share/vulkan/icd.d/ /etc/vulkan/icd.d/ 2>/dev/null | tr '\n' ' ')"
echo "simuladores já abertos: $(sims)"
git log --oneline -1; git -C biguagym log --oneline -1
"$PY" -c "import biguasim, torch; print('biguasim', biguasim.__file__); print('torch', torch.__version__, torch.cuda.is_available(), torch.cuda.device_count())"

sec "2. Smoke (200 passos cada)"
for e in DjiMatriceNav-v0 DjiMatriceNav-v1 BlueBoatTrajectoryFollower-v2; do
    "$PY" smoke_test.py --env "$e" --steps 200 --frame-every 100 --out "$V/smoke" > "$V/smoke_$e.log" 2>&1
    "$PY" - "$V/smoke/$e/summary.json" "$e" <<'EOF'
import json, sys
try:
    d = json.load(open(sys.argv[1]))
    print(f"{sys.argv[2]}: {d.get('status')} | {d.get('steps_per_s')} passos/s | obs {d.get('obs_dim')} | ação {d.get('act_dim')} "
          f"| sims depois {d.get('sim_procs_after')} | erro: {(d.get('error') or '')[:150]}")
except Exception as ex:
    print(f"{sys.argv[2]}: sem summary.json ({ex}); veja smoke_{sys.argv[2]}.log")
EOF
done
echo "simuladores abertos depois do smoke: $(sims)"

sec "3. Pilotos de treino (2000 passos) + 4. GPU usada pelo Unreal"
piloto() {  # $1=ambiente $2=agente $3..=overrides
    local e=$1 a=$2; shift 2
    local d=$V/piloto_${a}_$e; mkdir -p "$d"
    ( while true; do
        echo "$(date +%T),$(sims),$(nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits | tr '\n' ' ')"
        sleep 15; done ) > "$d/vram.csv" &
    local mon=$! ini; ini=$(date +%s)
    ( cd "$d" && PATH="$V/bin:$PATH" CUDA_VISIBLE_DEVICES=$G timeout 3600 "$PY" "$REPO/run.py" hydra/launcher=basic env="$e" agent="$a" \
        num_train_steps=2000 eval_freq=1000 num_eval_episodes=1 runs=1 "$@" \
        curves_path="$d/curves" logs_path="$d/logs" > "$d/saida.log" 2>&1 )
    local rc=$?
    kill $mon 2>/dev/null
    echo "$a $e: exit=$rc em $(( $(date +%s) - ini )) s | sims depois: $(sims)"
    grep -E "\| eval|Traceback|Error" "$d/saida.log" | tail -4
    echo "  VRAM por GPU (MiB) no pico: $(sort -t, -k2 -n "$d/vram.csv" | tail -1 | cut -d, -f2-)"
}
# Os pilotos rodam como a fila: presos à ÚLTIMA GPU, com o nvidia-smi falso que só mostra essa GPU.
G=$(( $(nvidia-smi -L | wc -l) - 1 ))
mkdir -p "$V/bin"
printf '#!/bin/sh\nexec "%s" -i %s "$@"\n' "$(command -v nvidia-smi)" "$G" > "$V/bin/nvidia-smi"; chmod +x "$V/bin/nvidia-smi"
echo "pilotos presos à GPU $G (CUDA_VISIBLE_DEVICES=$G)"
piloto DjiMatriceNav-v2 td3 agent.learning_starts=500
piloto DjiMatriceNav-v1 cuprl

sec "Resumo"
echo "- GPUs: $(nvidia-smi -L | wc -l). Os pilotos estavam presos à GPU $G. Se a VRAM subiu na GPU 0 e não na $G,"
echo "  o Unreal ignora o CUDA_VISIBLE_DEVICES: com WORKERS>1, todos os simuladores vão para a GPU 0"
echo "  (~1,2–2 GB cada, 3 por run). Nesse caso, escolha WORKERS pela VRAM da GPU 0."
echo "- Simuladores ainda abertos: $(sims) (devia ser 0)."
echo "Relatório em $REL"
