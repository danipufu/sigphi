#!/usr/bin/env bash
# Neteja obres/autors mal classificats de la BD. NO re-embeggeix; nomes esborra.
# El servei pot seguir actiu (no cal aturar-lo ni reiniciar).
#
# Us:  bash deploy/cleanup.sh         -> DRY-RUN: mostra que esborraria, NO esborra
#      bash deploy/cleanup.sh apply   -> esborra de debo
APP=/home/daniel/sigphi
FLAG=""
[ "$1" = "apply" ] && FLAG="--apply"
sudo -u daniel bash -c "cd $APP && source venv/bin/activate && VECTOR_DB_TYPE=qdrant python scripts/cleanup.py $FLAG"
