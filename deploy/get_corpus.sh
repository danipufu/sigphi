#!/usr/bin/env bash
# Baixa el corpus des del GitHub Release i el descomprimeix a corpus/.
# Requereix que el release "corpus-v1" amb l'asset corpus.tar.gz estigui PUBLICAT.
#
# Ús:  bash deploy/get_corpus.sh
set -e
cd /home/daniel/sigphi

URL="https://github.com/danipufu/sigphi/releases/download/corpus-v1/corpus.tar.gz"
echo ">>> Baixant corpus de:"
echo "    $URL"
wget -q --show-progress -O corpus.tar.gz "$URL"

SIZE=$(stat -c%s corpus.tar.gz 2>/dev/null || echo 0)
if [ "$SIZE" -lt 1000000 ]; then
  echo ""
  echo "ERROR: la descàrrega fa només $SIZE bytes -> el release no és accessible."
  echo "Comprova que el release 'corpus-v1' està PUBLICAT a:"
  echo "  https://github.com/danipufu/sigphi/releases"
  exit 1
fi

echo ">>> Descomprimint ($((SIZE/1024/1024)) MB)..."
tar -xzf corpus.tar.gz
echo ">>> Fitxers a corpus/:"
ls corpus | wc -l
echo ">>> Fet."
