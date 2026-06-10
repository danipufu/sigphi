#!/usr/bin/env bash
# Recarrega el servei sigphi per aplicar canvis que es llegeixen a l'arrencada
# (authors_aliases.json, prompts, config). NO cal re-ingest: els vectors no canvien.
# Ús:  sudo bash deploy/reload.sh
echo ">>> Reiniciant sigphi per recarregar àlies/prompts (sense re-ingest)..."
systemctl restart sigphi
sleep 3
systemctl status sigphi --no-pager | head -n 5
echo ">>> Fet. Servei recarregat amb la configuració nova."
