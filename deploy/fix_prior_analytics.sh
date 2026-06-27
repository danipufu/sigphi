#!/usr/bin/env bash
# Reemplaça l'stub de 5KB de Prior Analytics pels 2 llibres complets (Book 1/2)
# que collect() no seguia (<5 subpàgines). Operació petita; no cal aturar el servei.
set -e
cd /home/daniel/sigphi
PY=/home/daniel/sigphi/venv/bin/python3

echo ">>> 1. Treure l'stub vell de Prior Analytics"
VECTOR_DB_TYPE=qdrant $PY scripts/remove_files.py --apply Aristotle__Prior_Analytics_Owen_en.txt || true
rm -f corpus/Aristotle__Prior_Analytics_Owen_en.txt

echo ">>> 2. Baixar els textos nous (Prior Analytics Book 1+2)"
$PY scripts/download_wikisource.py

echo ">>> 3. Mida dels fitxers de l'Organon (verificació: cap stub de pocs KB)"
ls -la corpus/Aristotle__Prior_Analytics_Book*_Owen_en.txt corpus/Aristotle__Topics_Owen_en.txt 2>&1

echo ">>> 4. Ingerir els nous"
VECTOR_DB_TYPE=qdrant $PY scripts/ingest.py
echo ">>> FET"
