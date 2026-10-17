#!/usr/bin/env bash
# Instala o ambiente de testes do biguagym num PC novo (ex.: PC do laboratório).
#
# Pré-requisitos:
#   - este repositório clonado, na branch testes-ambientes;
#   - acesso ao GitHub: o submódulo vem de ttszin/biguagym (.gitmodules) e o biguasim de ttszin/biguasim;
#   - em ~/leva (ou LEVA=/outro/caminho): SkyDive.tar.zst, o mundo gerado no notebook de desenvolvimento
#     (ver TESTES.md, 2026-10-02/03). Não é preciso se o mundo já estiver instalado;
#   - driver NVIDIA, git, zstd, gcc e Python 3.12 (python3.12 do sistema ou conda).
#
# Uso:  bash setup/instalar_pc_lab.sh
# Pode ser rodado de novo: o que já está feito é pulado.
set -euo pipefail
export GIT_PAGER=cat PAGER=cat     # sem paginador: em alguns PCs o `git log` abria o less e parava em (END)

REPO=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
LEVA=${LEVA:-$HOME/leva}
BIGUASIM=${BIGUASIM:-$HOME/biguasim}
VENV=${VENV:-$HOME/venv-biguagym}
WORLDS=${WORLDS:-$HOME/.local/share/biguasim/1.0.0/worlds}

SIM_URL=https://github.com/ttszin/biguasim.git             # fork com os patches do biguasim 1.0.0

# Commits esperados (os mesmos do notebook)
SUB_COMMIT=$(git -C "$REPO" ls-tree HEAD biguagym | awk '{print $3}')   # o que a branch clonada aponta (testes-ambientes: 32698e5; spec/recompensas: fcf4358)
SIM_COMMIT=53ad1f9dfd5e22ebe6e55c02da5f660a311335c7        # biguasim testes-biguagym (P3)
WORLD_MD5=bd371b063645adabe9ef38c13fdb5b6d                 # SkyDive.tar.zst
WORLD_REPO=${WORLD_REPO:-ttszin/biguasim}                 # release pública com o SkyDive.tar.zst (baixado se faltar em $LEVA)
WORLD_TAG=${WORLD_TAG:-skydive-20261002}

passo() { printf '\n== %s\n' "$*"; }
falha() { printf '\nERRO: %s\n' "$*" >&2; exit 1; }

passo "1/6 Pré-requisitos"
for c in git nvidia-smi gcc; do
    command -v "$c" >/dev/null || falha "comando '$c' não encontrado (gcc: sudo apt install build-essential)"
done
nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv,noheader

passo "2/6 Submódulo biguagym → $SUB_COMMIT"
SUB=$REPO/biguagym
if [ -e "$SUB/.git" ] && [ -n "$(git -C "$SUB" status --porcelain)" ]; then
    falha "$SUB tem alterações locais; resolva antes"
fi
git -C "$REPO" submodule sync -q          # aplica a URL do .gitmodules (fork ttszin/biguagym)
git -C "$REPO" submodule update --init
[ "$(git -C "$SUB" rev-parse HEAD)" = "$SUB_COMMIT" ] || falha "submódulo não está em $SUB_COMMIT"
git -C "$SUB" log --oneline -1

passo "3/6 biguasim em $BIGUASIM → $SIM_COMMIT"
if [ ! -e "$BIGUASIM/.git" ]; then
    git clone -q -b testes-biguagym "$SIM_URL" "$BIGUASIM"
fi
if [ "$(git -C "$BIGUASIM" rev-parse HEAD)" != "$SIM_COMMIT" ]; then
    # ~/biguasim já existia (ex.: clonado do hydrone-furg ou do bundle): traz a branch do fork sem mexer no origin.
    [ -z "$(git -C "$BIGUASIM" status --porcelain --untracked-files=no)" ] \
        || falha "$BIGUASIM tem alterações locais; resolva antes"
    git -C "$BIGUASIM" fetch -q "$SIM_URL" testes-biguagym
    git -C "$BIGUASIM" checkout -q -B testes-biguagym FETCH_HEAD
fi
[ "$(git -C "$BIGUASIM" rev-parse HEAD)" = "$SIM_COMMIT" ] || falha "biguasim não está em $SIM_COMMIT"
git -C "$BIGUASIM" log --oneline -1

passo "4/6 Python 3.12 em $VENV"
if [ ! -x "$VENV/bin/python" ]; then
    if command -v python3.12 >/dev/null; then
        python3.12 -m venv "$VENV"
    elif command -v conda >/dev/null; then
        conda create -y -q -p "$VENV" python=3.12 pip     # o conda novo não põe o pip junto com o python
    else
        falha "sem python3.12 nem conda (sudo apt install python3.12-venv python3.12-dev)"
    fi
fi
PY=$VENV/bin/python
"$PY" -c 'import sys; assert sys.version_info[:2] == (3, 12), sys.version' \
    || falha "$VENV não é Python 3.12; apague a pasta e rode de novo"
if ! "$PY" -m pip --version >/dev/null 2>&1; then   # venv criado sem pip (ex.: conda create só com python)
    echo "pip ausente em $VENV: instalando"
    "$PY" -m ensurepip --upgrade >/dev/null 2>&1 \
        || { command -v conda >/dev/null && conda install -y -q -p "$VENV" pip; } \
        || falha "não consegui instalar o pip em $VENV; apague a pasta e rode de novo"
fi
"$PY" -m pip install -q -U pip
"$PY" -m pip install -q -r "$REPO/requirements-venv.txt" \
    || falha "pip falhou. Se foi no evdev: sudo apt install build-essential python3.12-dev linux-libc-dev"
"$PY" -m pip install -q -e "$BIGUASIM" --no-deps

passo "5/6 Mundo SkyDive em $WORLDS"
if [ -f "$WORLDS/SkyDive/config.json" ]; then
    echo "já existe, extração pulada"
else
    if [ ! -f "$LEVA/SkyDive.tar.zst" ]; then
        # Baixa da release do GitHub (sem cópia manual). Release privada: precisa do gh logado (gh auth login).
        echo "baixando SkyDive.tar.zst (1,4 GB) da release $WORLD_TAG de $WORLD_REPO..."
        mkdir -p "$LEVA"
        if command -v gh >/dev/null && gh auth status >/dev/null 2>&1; then
            gh release download "$WORLD_TAG" -R "$WORLD_REPO" -p SkyDive.tar.zst -D "$LEVA" --clobber \
                || falha "download pelo gh falhou (a release $WORLD_TAG existe em $WORLD_REPO?)"
        else
            curl -fL --retry 5 -C - -o "$LEVA/SkyDive.tar.zst.part" \
                "https://github.com/$WORLD_REPO/releases/download/$WORLD_TAG/SkyDive.tar.zst" \
                && mv "$LEVA/SkyDive.tar.zst.part" "$LEVA/SkyDive.tar.zst" \
                || falha "download falhou. Se a release for privada: sudo apt install gh && gh auth login, e rode de novo"
        fi
    fi
    command -v zstd >/dev/null || falha "zstd não encontrado (sudo apt install zstd)"
    echo "conferindo md5..."
    [ "$(md5sum "$LEVA/SkyDive.tar.zst" | cut -d' ' -f1)" = "$WORLD_MD5" ] \
        || { rm -f "$LEVA/SkyDive.tar.zst"
             falha "SkyDive.tar.zst corrompido ou incompleto (md5 diferente de $WORLD_MD5): apagado; rode de novo para baixar"; }
    mkdir -p "$WORLDS"
    tar --zstd -xf "$LEVA/SkyDive.tar.zst" -C "$WORLDS"
fi
(cd "$WORLDS/SkyDive" && find config.json idColors.txt materials.csv palette.json Linux -type f \
    -not -path "*/_P_backups/*" -not -path "*/_BASE_backups/*" -not -path "Linux/Biguasim/Saved/*" \
    -printf "%s %p\n" | sort -k2) \
    | diff -q "$REPO/setup/skydive_manifest.txt" - >/dev/null \
    && echo "mundo idêntico ao do notebook ($(wc -l < "$REPO/setup/skydive_manifest.txt") arquivos; Saved/ ignorada)" \
    || falha "o mundo em $WORLDS/SkyDive difere de setup/skydive_manifest.txt (extração incompleta? em 2026-10-17 o
       Holodeck do PC do lab tinha 79 MB em vez de 241 MB e o simulador dava segfault). Refaça:
         df -h $WORLDS      # precisa de alguns GB livres
         mv $WORLDS/SkyDive $WORLDS/SkyDive_quebrado
         bash setup/instalar_pc_lab.sh"

passo "6/6 Verificação"
cd "$REPO"
"$PY" - <<'EOF'
import torch, gymnasium, hydra, cv2, scipy, dm_env, biguasim
print("torch", torch.__version__, "| cuda:", torch.cuda.is_available(),
      "|", torch.cuda.get_device_name(0) if torch.cuda.is_available() else "-")
print("biguasim", biguasim.__file__)
EOF
N=$("$PY" smoke_test.py --list 2>/dev/null | grep -c -- '-v[0-9]' || true)
echo "ids registrados: $N (esperado: 54)"

cat <<EOF

Instalação concluída. Para usar:
  source $VENV/bin/activate
  python smoke_test.py --env DjiMatriceLand-v0 --steps 200
  ps aux | grep -i -E "biguasim|holodeck|unreal" | grep -v grep    # deve vir vazio depois
EOF
