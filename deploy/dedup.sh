#!/usr/bin/env bash
# Desduplica obres amb contingut IDENTIC dins un mateix autor (mateix text baixat
# dues vegades amb dos noms diferents). NO re-embeggeix; nomes esborra els chunks
# duplicats. El servei pot seguir actiu.
#
# Us:  bash deploy/dedup.sh         -> DRY-RUN: mostra que esborraria, NO esborra
#      bash deploy/dedup.sh apply   -> esborra els duplicats de debo
APP=/home/daniel/sigphi
FLAG=""
[ "$1" = "apply" ] && FLAG="--apply"
sudo -u daniel bash -c "cd $APP && source venv/bin/activate && VECTOR_DB_TYPE=qdrant python scripts/dedup.py $FLAG"
