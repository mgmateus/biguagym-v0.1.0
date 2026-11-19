#!/usr/bin/env bash
# Copia o mundo SkyDive do BiguaSim 1.1.0 de uma máquina que já o tem (o PC do lab) para o cluster2, e o manifesto que o
# instalador usa para conferi-lo (setup/instalar_pc_lab.sh com SIM_VERSAO=1.1.0). O mundo 1.1.0 só sai do servidor de
# mundos da universidade; o cluster é alcançado pelo host de salto (do notebook em casa dá timeout, do lab não).
#
# Uso (no lab):  nohup bash tools/copiar_mundo_cluster.sh > ~/copiar_mundo.log 2>&1 &
set -euo pipefail

VERSAO=${VERSAO:-1.1.0}
ORIGEM=${ORIGEM:-$HOME/.local/share/biguasim/$VERSAO/worlds/SkyDive}
DESTINO=${DESTINO:-teteu@cluster2}
SALTO=${SALTO:-teteu@10.230.108.173}
SSH="ssh -o BatchMode=yes -J $SALTO"
MANIFEST=$HOME/skydive_manifest_$VERSAO.txt

[ -f "$ORIGEM/config.json" ] || { echo "sem mundo em $ORIGEM"; exit 1; }
echo "$(date +%T) origem $ORIGEM: $(du -sh "$ORIGEM" | cut -f1)"

# mesmo formato de setup/skydive_manifest.txt
(cd "$ORIGEM" && find config.json idColors.txt materials.csv palette.json Linux -type f \
    -not -path "*/_P_backups/*" -not -path "*/_BASE_backups/*" -not -path "Linux/Biguasim/Saved/*" \
    -printf "%s %p\n" | sort -k2) > "$MANIFEST"
echo "$(date +%T) manifesto: $(wc -l < "$MANIFEST") arquivos"

$SSH "$DESTINO" "mkdir -p .local/share/biguasim/$VERSAO/worlds"
rsync -a --partial --exclude '/SkyDive/Linux/Biguasim/Saved/' -e "$SSH" "$ORIGEM" "$DESTINO:.local/share/biguasim/$VERSAO/worlds/"
echo "$(date +%T) rsync ok"
rsync -a -e "$SSH" "$MANIFEST" "$DESTINO:biguagym-v0.1.0/setup/skydive_manifest_$VERSAO.txt"
$SSH "$DESTINO" "du -sh .local/share/biguasim/$VERSAO/worlds/SkyDive"
echo "$(date +%T) FIM_COPIA"
