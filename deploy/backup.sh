#!/usr/bin/env bash
# Còpia de seguretat GRATUÏTA de SigPhi (tot al disc del VPS, cap cost):
#   - snapshot de la col·lecció Qdrant (queda a qdrant_storage/snapshots/)
#   - còpia del ChunkStore (el text de tots els fragments)
# Si mai es corromp Qdrant, pots restaurar del snapshot o re-ingestar el corpus.
# Ús:  bash deploy/backup.sh
set -e
cd /home/daniel/sigphi
STAMP=$(date +%Y%m%d_%H%M%S)
DEST="/home/daniel/sigphi_backups"
mkdir -p "$DEST"

echo ">>> Creant snapshot de Qdrant (col·lecció 'sigphi')..."
if curl -s -X POST "http://localhost:6333/collections/sigphi/snapshots" >/dev/null; then
  echo "    OK (desat dins qdrant_storage/snapshots/sigphi/)"
else
  echo "    AVÍS: no s'ha pogut crear el snapshot (Qdrant respon?)"
fi

echo ">>> Copiant el ChunkStore (text dels fragments)..."
cp data/chunks.sqlite "$DEST/chunks_$STAMP.sqlite"

echo ">>> Backups actuals:"
ls -lh "$DEST"
echo ">>> Fet. El text dels fragments està protegit a $DEST"
