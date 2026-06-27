#!/usr/bin/env bash
# Posada a punt final del corpus després del redeploy: treu stubs/duplicats,
# baixa els textos nous (Montesquieu EN, Organon, Lisis...) i els ingereix.
# Es pot executar com a root o com a daniel — es re-executa com a daniel.
#   bash /home/daniel/sigphi/deploy/final_polish.sh
if [ "$(id -un)" != "daniel" ]; then
  exec su - daniel -c "bash /home/daniel/sigphi/deploy/final_polish.sh"
fi
set -e
cd /home/daniel/sigphi
git pull
PY=/home/daniel/sigphi/venv/bin/python3
export VECTOR_DB_TYPE=qdrant

echo "===== 1/5  Treure stubs d'índex ====="
echo s | bash deploy/remove_stubs.sh

echo "===== 2/5  Treure duplicats autèntics ====="
echo s | bash deploy/remove_duplicates.sh

echo "===== 3/5  Baixar textos nous (skip dels ja existents) ====="
$PY scripts/download_archive.py    || true
$PY scripts/download_wikisource.py || true
$PY scripts/download_sacred.py     || true

echo "===== 4/5  Ingerir només els fitxers nous ====="
$PY scripts/ingest.py

echo "===== 5/5  Verificar la salut del corpus ====="
$PY scripts/corpus_health.py | grep "##" || true

echo "===== FET — refinament complet ====="
