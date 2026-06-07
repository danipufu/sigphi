#!/usr/bin/env bash
# Llança l'ingest del corpus complet a Qdrant EN SEGON PLA (resumible).
# Es pot tancar la VNC i l'ingest continua. Segueix-lo amb:  tail -f ingest.log
#
# Ús:  bash deploy/run_ingest.sh
set -e
cd /home/daniel/sigphi
source venv/bin/activate
export VECTOR_DB_TYPE=qdrant
nohup python -u scripts/ingest.py > ingest.log 2>&1 &
echo "Ingest llançat en segon pla (PID $!)."
echo "Segueix el progrés amb:   tail -f ingest.log"
echo "Compta els chunks fets:   wc -l data/ingest_done.txt"
