#!/usr/bin/env bash
# Re-ingesta neta dels fitxers Wikisource (aplica strip_mediawiki_markup).
# Atura el servei, esborra els chunks vells, re-ingereix net i reaixeca.
# Llança-ho en segon pla i deixa-ho córrer:
#   nohup bash deploy/reingest_wikisource.sh > ~/reingest_wiki.log 2>&1 &
#   tail -f ~/reingest_wiki.log
set -e

cd /home/daniel/sigphi
PY=/home/daniel/sigphi/venv/bin/python3

WIKI=$(grep -il "^Source:.*wikisource" corpus/*.txt | xargs -n1 basename)
N=$(echo "$WIKI" | wc -l)
echo ">>> $N fitxers Wikisource a re-ingerir"

systemctl stop sigphi
VECTOR_DB_TYPE=qdrant $PY scripts/remove_files.py --apply $WIKI
VECTOR_DB_TYPE=qdrant $PY scripts/ingest.py
systemctl start sigphi
VECTOR_DB_TYPE=qdrant $PY scripts/corpus_health.py | grep "##"
echo ">>> FET"
