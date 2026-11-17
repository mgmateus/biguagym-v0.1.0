#!/usr/bin/env bash
# Testes do Goto do Hydrone no simulador (T6/T7 das specs pipeline-pixels, hydrone-goto-dique e sensores-goto).
# Uso (na raiz do repositório): nohup bash tools/testar_goto_lab.sh > ~/testar_goto_lab.log 2>&1 &
PY=${PY:-$HOME/venv-biguagym/bin/python}
cd "$(dirname "$0")/.."

procs() { ps aux | grep -i -E "biguasim|holodeck|unreal" | grep -v -E "grep|testar_goto" | wc -l; }
etapa() { echo; echo "===== $(date +%H:%M:%S) $*"; }

etapa "git"; git log --oneline -1; git -C biguagym log --oneline -1
etapa "processos do simulador antes: $(procs)"

etapa "pytest"; $PY -m pytest -q tests 2>&1 | tail -2

etapa "explorar_mapa: spawn do cenário pilares (ar e água), 4 guinadas"
timeout 600 $PY tools/explorar_mapa.py --ponto 103.6,97.4,2 --ponto 103.6,97.4,-0.5 --giro \
    --saida explorar_mapa/teste_spawn 2>&1 | grep -v -i "warn" | tail -30
echo "processos: $(procs)"

etapa "diag_goto (guinada e subida)"
timeout 600 $PY tools/diag_goto.py HydroneGotoPilares-v0 5 2>&1 | grep -v -i "warn" | tail -20
echo "processos: $(procs)"

for v in v0 v1 v2; do
    etapa "smoke HydroneGotoPilares-$v"
    timeout 1200 $PY smoke_test.py --env HydroneGotoPilares-$v --steps 200 --frame-every 50 2>&1 | grep -v -i "warn" | tail -25
    echo "processos: $(procs)"
done

etapa "fim; processos do simulador: $(procs)"
