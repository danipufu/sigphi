#!/usr/bin/env bash
# Re-neteja els 3 textos OCR del Lot 1 (Capital, Retòrica, De Oratore) amb la neteja
# millorada i, a la mateixa passada, afegeix el Lot 2 (Ciceró Div./Lleis, Kant
# Anthropologie) i qualsevol altre text nou dels scripts de descàrrega.
#
# Tot en una sola passada perquè facis servir el VPS un sol cop:
#   git pull
#   sudo bash deploy/refresh_and_add.sh
# (Deixa la VNC oberta: l'ingest va en primer pla i pot trigar ~10-15 min.)
set -e
APP=/home/daniel/sigphi
cd "$APP"

echo ">>> [1/2] Re-netejant els 3 textos OCR del Lot 1 (BD + corpus + ingest_done)..."
sudo -u daniel bash -c "cd $APP && source venv/bin/activate && VECTOR_DB_TYPE=qdrant python scripts/reclean_ocr.py"

echo ">>> [2/2] Baixant (els 3 re-netejats + el Lot 2) i re-ingestant..."
bash deploy/add_sacred.sh
