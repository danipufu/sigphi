#!/usr/bin/env bash
# Repara El Capital Vol. III: la seva ingesta va quedar a mitges (text a SQLite,
# vectors a Qdrant incomplets) i per això no es recuperava. Treu el fitxer de
# ingest_done i el torna a ingestar -> el re-embedding sobreescriu els vectors.
#
# IMPORTANT: fes-ho amb prou memòria perquè aquest cop completi. Recomanat:
#   git pull
#   sudo bash deploy/add_swap.sh        # marge de memòria
#   sudo systemctl restart sigphi       # estat fresc + desplega el fix del timeout
#   sudo bash deploy/reembed_vol3.sh    # <- aquest script
set -e
APP=/home/daniel/sigphi
cd "$APP"

echo ">>> [1/3] Traient el Vol. III de ingest_done..."
sudo -u daniel bash -c "cd $APP && source venv/bin/activate && VECTOR_DB_TYPE=qdrant python scripts/reembed.py"

echo ">>> [2/3] Aturant el servei i re-ingestant (re-embedding del Vol. III; espera)..."
systemctl stop sigphi
sudo -u daniel bash -c "cd $APP && source venv/bin/activate && VECTOR_DB_TYPE=qdrant python -u scripts/ingest.py"

echo ">>> [3/3] Reiniciant el servei..."
systemctl start sigphi
sleep 3
systemctl status sigphi --no-pager | head -n 5
echo ">>> Fet. Prova una pregunta del Vol. III (p. ex. 'la renda de la terra' o 'la taxa de guany')."
