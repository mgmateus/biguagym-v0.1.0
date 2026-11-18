#!/usr/bin/env bash
# T11 da spec hydrone-goto-dique: obstáculos feitos de torpedos no simulador (conferência e smokes).
# Uso (na raiz do repositório, no lab): nohup bash tools/testar_obstaculos_lab.sh > ~/testar_obstaculos_lab.log 2>&1 &
PY=${PY:-$HOME/venv-biguagym/bin/python}
cd "$(dirname "$0")/.."

procs() { ps aux | grep -i -E "biguasim|holodeck|unreal" | grep -v -E "grep|testar_" | wc -l; }
etapa() { echo; echo "===== $(date +%H:%M:%S) $*"; }
filtro() { grep -v -i -E "warn|deprecat|torch.cross|linalg.cross|cross    ="; }

etapa "git"; git log --oneline -1; git -C biguagym log --oneline -1
etapa "processos do simulador antes: $(procs)"
etapa "pytest"; $PY -m pytest -q tests 2>&1 | tail -2

etapa "conferir_obstaculos (pilares e dique)"
timeout 1500 $PY -u tools/conferir_obstaculos.py --passos ${PASSOS:-200} 2>&1 | filtro | tail -40
echo "processos: $(procs)"

for id in HydroneGotoPilares-v0 HydroneGotoPilares-v1 HydroneGotoPilares-v2 HydroneGotoDique-v0; do
    etapa "smoke $id"
    timeout 1200 $PY smoke_test.py --env $id --steps 200 --frame-every 50 2>&1 | filtro | tail -12
    echo "processos: $(procs)"
done
etapa "FIM"
