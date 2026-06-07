#!/usr/bin/env bash
# PROVA d'ingest: només 5 fitxers cap a Qdrant real (valida tot el camí
# abans de l'ingest complet). No modifica res permanent.
#
# Ús:  bash deploy/test_ingest.sh
set -e
cd /home/daniel/sigphi
source venv/bin/activate
export VECTOR_DB_TYPE=qdrant
echo ">>> Provant ingest de 5 fitxers cap a Qdrant (localhost:6333)..."
python scripts/ingest.py --max-files 5
