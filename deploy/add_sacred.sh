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

echo ">>> [1/4] Baixant els textos sagrats de Project Gutenberg..."
cd "$APP"
sudo -u daniel "$PY" scripts/download_sacred.py

echo ">>> [2/4] Aturant el servei sigphi (alliberar RAM)..."
systemctl stop sigphi

echo ">>> [3/4] Ingest dels nous fitxers cap a Qdrant (espera, no tanquis)..."
sudo -u daniel bash -c "cd $APP && source venv/bin/activate && VECTOR_DB_TYPE=qdrant python -u scripts/ingest.py"

echo ">>> [4/4] Reiniciant el servei sigphi..."
systemctl start sigphi
sleep 3
systemctl status sigphi --no-pager | head -n 5
echo ">>> Fet. Textos sagrats afegits i servei actiu de nou."
