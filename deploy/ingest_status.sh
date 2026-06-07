#!/usr/bin/env bash
# Mostra el progrés de l'ingest: fitxers fets, si corre, i les últimes línies.
# Ús:  bash deploy/ingest_status.sh
cd /home/daniel/sigphi
DONE=$(wc -l < data/ingest_done.txt 2>/dev/null || echo 0)
echo ">>> Fitxers indexats: $DONE / 941"
if pgrep -f "scripts/ingest.py" >/dev/null; then
  echo ">>> Estat: EN CURS (l'ingest corre)."
else
  echo ">>> Estat: NO corre (acabat, o aturat -> relança amb bash deploy/run_ingest.sh)."
fi
echo ">>> Últimes línies del log:"
tail -n 6 ingest.log 2>/dev/null || echo "(encara no hi ha log)"
