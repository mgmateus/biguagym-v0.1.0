#!/usr/bin/env bash
# Instala no cluster2 o ambiente dos treinos HydroneGoto (BiguaSim 1.1.0). O cluster2 não tem python3.12 nem conda:
# Miniconda no home e o venv pelo conda-forge (o canal padrão do conda novo pede aceite de termos e para o script).
# O mundo SkyDive 1.1.0 precisa já estar copiado (tools/copiar_mundo_cluster.sh, rodado no lab).
#
# Uso (no cluster2, na raiz do repositório):  bash tools/instalar_cluster_goto.sh
set -euo pipefail

REPO=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
CONDA_DIR=${CONDA_DIR:-$HOME/miniconda3}
VENV=${VENV:-$HOME/venv-biguagym}

if [ ! -x "$CONDA_DIR/bin/conda" ]; then
    echo "== Miniconda em $CONDA_DIR"
    curl -fsSL -o "$HOME/miniconda_instalador.sh" https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-x86_64.sh
    bash "$HOME/miniconda_instalador.sh" -b -p "$CONDA_DIR"
    rm -f "$HOME/miniconda_instalador.sh"
fi
if [ ! -x "$VENV/bin/python" ]; then
    echo "== venv Python 3.12 em $VENV (conda-forge)"
    "$CONDA_DIR/bin/conda" create -y -q -p "$VENV" -c conda-forge --override-channels python=3.12 pip
fi

cd "$REPO"
SIM_VERSAO=1.1.0 VENV="$VENV" bash setup/instalar_pc_lab.sh
