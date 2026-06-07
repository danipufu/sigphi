#!/usr/bin/env bash
# Reinicia el servei SigPhi (per aplicar codi nou després d'un git pull).
# Ús:  sudo bash deploy/restart.sh
systemctl restart sigphi
echo ">>> Servei reiniciat. Carregant el model (~1 min)..."
sleep 3
systemctl status sigphi --no-pager | head -n 6
