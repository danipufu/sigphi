#!/usr/bin/env bash
# Genera una clau secreta per a l'endpoint GET /api/ask, la desa al .env i reinicia
# el servei (que recarrega el codi nou + la clau). Imprimeix la clau al final perque
# la puguis ensenyar a Claude.
#
# Us:  sudo bash deploy/set_ask_key.sh
set -e
APP=/home/daniel/sigphi
ENVFILE="$APP/.env"

KEY=$(openssl rand -hex 16 2>/dev/null || head -c16 /dev/urandom | od -An -tx1 | tr -d ' \n')

touch "$ENVFILE"
# Treu una ASK_API_KEY anterior (si n'hi havia) i afegeix la nova.
sed -i '/^ASK_API_KEY=/d' "$ENVFILE"
echo "ASK_API_KEY=$KEY" >> "$ENVFILE"
chown daniel:daniel "$ENVFILE" 2>/dev/null || true

echo ">>> Clau desada al .env. Reiniciant el servei (carrega codi nou + clau)..."
systemctl restart sigphi
sleep 3
systemctl status sigphi --no-pager | head -n 4

echo ""
echo "==================================================================="
echo ">>> ASK_API_KEY = $KEY"
echo ">>> Ensenya aquesta clau a Claude perque pugui consultar SigPhi sol."
echo "==================================================================="
