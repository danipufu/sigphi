#!/usr/bin/env bash
# Afegeix els textos sagrats (lot actual de download_sacred.py) al corpus i els
# ingesta, gestionant la RAM: atura el servei mentre ingesta (per no tenir 2
# models carregats alhora) i el reinicia en acabar.
#
# Ús:  sudo bash deploy/add_sacred.sh
# (Deixa la VNC oberta: l'ingest va en primer pla i pot trigar ~10-15 min.)
set -e
APP=/home/daniel/sigphi
PY=$APP/venv/bin/python

echo ">>> [1/6] Baixant els textos nous de Project Gutenberg..."
cd "$APP"
sudo -u daniel "$PY" scripts/download_sacred.py

echo ">>> [2/6] Baixant els textos nous d'archive.org (OCR)..."
sudo -u daniel "$PY" scripts/download_archive.py

echo ">>> [3/6] Baixant els textos nous de Wikisource..."
sudo -u daniel "$PY" scripts/download_wikisource.py

echo ">>> [4/6] Aturant el servei sigphi (alliberar RAM)..."
systemctl stop sigphi

echo ">>> [5/6] Ingest dels nous fitxers cap a Qdrant (espera, no tanquis)..."
sudo -u daniel bash -c "cd $APP && source venv/bin/activate && VECTOR_DB_TYPE=qdrant python -u scripts/ingest.py"

echo ">>> [6/6] Reiniciant el servei sigphi..."
systemctl start sigphi
sleep 3
systemctl status sigphi --no-pager | head -n 5
echo ">>> Fet. Textos nous afegits i servei actiu de nou."
