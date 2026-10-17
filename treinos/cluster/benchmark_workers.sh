#!/usr/bin/env bash
# Quantos treinos em paralelo (WORKERS) dão mais passos por segundo no total?
#
# Para cada N em NS, lança N treinos TD3 curtos do mesmo ambiente ao mesmo tempo (um processo run.py cada, em
# diretório próprio, como a fila_cluster.sh) e mede, pelo saida.log com hora, os passos/s de cada um na fase com
# atualização da rede (do passo LS+100 até o fim). Total = soma dos N. Também registra VRAM e RAM no pico.
# Para quando um N falha (erro ou falta de memória) e não tenta N maiores.
#
# Cada treino tem STEPS passos (padrão 3000, abaixo do limite de 5k sem autorização) e learning_starts=LS (500):
# a fase aleatória inicial do TD3 (25k passos) não usa a GPU e não representa a maior parte de um treino de 250k.
#
# Uso (no PC do lab, com a máquina livre):
#   nohup setsid bash treinos/cluster/benchmark_workers.sh > /dev/null 2>&1 < /dev/null &
#   tail -f treinos/cluster/benchmark/resultado.txt
# Variáveis: NS="1 2 3 4"  ENV=BlueROV2Nav-v0  STEPS=3000  LS=500  FORCAR=1 (roda mesmo com outros processos na GPU)
set -uo pipefail

REPO=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
PY=${PY:-$HOME/venv-biguagym/bin/python}
NS=${NS:-"1 2 3 4"}
ENV=${ENV:-BlueROV2Nav-v0}
STEPS=${STEPS:-3000}
LS=${LS:-500}
TIMEOUT=${TIMEOUT:-3600}            # por N
SIM_RE='Binaries/Linux/Holodeck'
OUT=$REPO/treinos/cluster/benchmark
RES=$OUT/resultado.txt
mkdir -p "$OUT"
ps -o pgid= $$ | tr -d ' ' > "$OUT/benchmark.pgid"
log() { echo "$*" | tee -a "$RES"; }

# só treinos (python) e simuladores (Holodeck): o desktop (gnome-shell, plasmashell, Xorg) também aparece na lista
outros=$(nvidia-smi --query-compute-apps=process_name --format=csv,noheader | grep -c -i -E 'python|holodeck' || true)
sims=$(pgrep -c -f "$SIM_RE" || true)
log "== benchmark $(date '+%F %T') | $(nvidia-smi --query-gpu=name,memory.total --format=csv,noheader) | RAM $(free -m | awk '/^Mem:/{print $2}') MiB | CPUs $(nproc)"
log "ENV=$ENV STEPS=$STEPS LS=$LS NS=\"$NS\" | processos na GPU antes: $outros, simuladores antes: $sims"
if { [ "$outros" -gt 0 ] || [ "$sims" -gt 0 ]; } && [ "${FORCAR:-0}" != 1 ]; then
    log "PAREI: a GPU está em uso (TCC?). A medida sairia errada e atrapalharia o outro treino. Rode com FORCAR=1 para ignorar."
    exit 1
fi

# saída do run.py com a hora de cada linha
carimbo() { "$PY" -u -c 'import sys,time
for l in sys.stdin: sys.stdout.write(f"{time.time():.3f} {l}"); sys.stdout.flush()'; }

for N in $NS; do
    D=$OUT/N$N; rm -rf "$D"; mkdir -p "$D"
    log "-- N=$N: $(date +%T)"
    pids=()
    for ((i = 0; i < N; i++)); do
        wd=$D/w$i; mkdir -p "$wd/curves" "$wd/logs"
        (
            cd "$wd" && PYTHONUNBUFFERED=1 setsid bash -c 'echo $$ > pgid; exec "$@"' _ \
                timeout -k 30 "$TIMEOUT" "$PY" "$REPO/run.py" hydra/launcher=basic env="$ENV" agent=td3 \
                num_train_steps="$STEPS" runs=1 agent.learning_starts="$LS" \
                eval_freq=1000000 num_eval_episodes=1 \
                curves_path="$wd/curves" logs_path="$wd/logs" 2>&1 | carimbo > "$wd/saida.log"
        ) &
        pids+=($!)
        sleep 2
    done
    # pico de VRAM/RAM enquanto rodam
    pico_vram=0; min_ram=999999
    while pgrep -f "run.py.*curves_path=$D/" >/dev/null; do
        v=$(nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits | head -1 | tr -d ' ')
        r=$(free -m | awk '/^Mem:/{print $7}')
        [ "$v" -gt "$pico_vram" ] && pico_vram=$v
        [ "$r" -lt "$min_ram" ] && min_ram=$r
        sleep 5
    done
    wait
    # encerra o que sobrou de cada grupo (o close() não fecha o simulador; o atexit fecha na saída normal)
    sleep 5; sobra=0
    for ((i = 0; i < N; i++)); do
        pg=$(cat "$D/w$i/pgid" 2>/dev/null) || continue
        n=$(pgrep -g "$pg" | wc -l); sobra=$((sobra + n))
        [ "$n" -gt 0 ] && { pkill -TERM -g "$pg"; sleep 10; pkill -KILL -g "$pg" 2>/dev/null; }
    done
    # passos/s de cada worker na fase com atualização
    "$PY" - "$D" "$N" "$LS" "$STEPS" "$pico_vram" "$min_ram" "$sobra" <<'EOF' | tee -a "$RES"
import glob, re, sys
D, N, LS, STEPS, vram, ram, sobra = sys.argv[1], int(sys.argv[2]), int(sys.argv[3]), int(sys.argv[4]), *sys.argv[5:]
vel, falhas = [], 0
for f in sorted(glob.glob(f'{D}/w*/saida.log')):
    pts = [(float(l.split()[0]), int(m.group(1))) for l in open(f, errors='replace')
           if (m := re.search(r'\| train \| S: (\d+)', l))]
    pts = [p for p in pts if p[1] >= LS + 100]
    if len(pts) < 2 or pts[-1][1] < STEPS * 0.9 or 'Traceback' in open(f, errors='replace').read():
        falhas += 1; print(f'   {f}: FALHOU (veja o arquivo)'); continue
    v = (pts[-1][1] - pts[0][1]) / (pts[-1][0] - pts[0][0]); vel.append(v)
    print(f'   {f.split("/")[-2]}: {v:.2f} passos/s')
tot = sum(vel)
print(f'N={N}: total {tot:.2f} passos/s ({", ".join(f"{v:.2f}" for v in vel)}) | falhas {falhas} | '
      f'pico VRAM {vram} MiB | RAM livre mínima {ram} MiB | processos que sobraram {sobra}')
if tot:
    print(f'N={N}: 8 treinos de 250k levariam ~{8 * 250000 / tot / 3600:.0f} h ({8 * 250000 / tot / 86400:.1f} dias)')
open(f'{D}/total', 'w').write(f'{tot:.4f} {falhas}\n')
EOF
    read -r tot falhas < "$D/total"
    [ "$falhas" -gt 0 ] && { log "N=$N teve falha: parei aqui (N maiores usariam ainda mais memória)."; break; }
done

melhor=$(for f in "$OUT"/N*/total; do read -r t fl < "$f"; [ "$fl" -eq 0 ] && echo "$t ${f%/total}"; done \
         | sort -gr | head -1)
log "== melhor: ${melhor##*/} (${melhor%% *} passos/s no total). Use WORKERS=${melhor##*/N} na fila_cluster.sh"
log "   simuladores abertos agora: $(pgrep -c -f "$SIM_RE" || true)"
