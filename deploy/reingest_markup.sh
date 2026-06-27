#!/usr/bin/env bash
# Re-ingesta dirigida dels fitxers amb entitats HTML o claudàtors residuals, perquè
# se'ls apliqui clean_residual_markup (entitats marxists.org, [[ ]], soroll {| |} d'OCR).
# Atura el servei, esborra els chunks d'aquests fitxers, els re-ingereix nets i reaixeca.
# Llança-ho i deixa-ho córrer:
#   nohup bash deploy/reingest_markup.sh > ~/rm.log 2>&1 &
#   tail -f ~/rm.log
set -e

# GUARD: una sola instància (la consola web de vegades duplica l'enganxat).
exec 9>/tmp/reingest_markup.lock
if ! flock -n 9; then echo ">>> Ja n'hi ha una en curs. Surto."; exit 0; fi

cd /home/daniel/sigphi
PY=/home/daniel/sigphi/venv/bin/python3

AFFECTED=$(grep -lE "&#[0-9]+;|\[\[|\{\||\|\}" corpus/*.txt 2>/dev/null | xargs -n1 basename)
N=$(echo "$AFFECTED" | wc -l)
echo ">>> $N fitxers amb entitats/claudàtors a re-ingerir"

systemctl stop sigphi
VECTOR_DB_TYPE=qdrant $PY scripts/remove_files.py --apply $AFFECTED
VECTOR_DB_TYPE=qdrant $PY scripts/ingest.py
systemctl start sigphi
sleep 5
VECTOR_DB_TYPE=qdrant $PY scripts/corpus_health.py | grep "##"
curl -s http://localhost:8000/api/health
echo ""
echo ">>> FET — el marcatge hauria de ser 0"
