#!/usr/bin/env bash
# Munta HTTPS amb Caddy per a sigphiai.com (reverse proxy -> localhost:8000).
# Passos: (1) allibera el port 443 del SSH (es queda a 22 i 2222), (2) instal·la Caddy,
# (3) hi posa el Caddyfile, (4) arrenca i prova el certificat.
#
# Us:  sudo bash deploy/setup_caddy.sh
# SEGURETAT: tens la consola VNC sempre disponible, encara que es complici l'SSH.
set -e
APP=/home/daniel/sigphi

echo ">>> [1/4] Alliberant el port 443 del SSH (es queda a 22 i 2222)..."
changed=0
for f in /etc/ssh/sshd_config /etc/ssh/sshd_config.d/*.conf; do
  [ -f "$f" ] || continue
  if grep -qiE '^[[:space:]]*Port[[:space:]]+443[[:space:]]*$' "$f"; then
    sed -ri 's/^[[:space:]]*Port[[:space:]]+443[[:space:]]*$/# Port 443 (alliberat per Caddy - SigPhi)/' "$f"
    echo "    modificat: $f"; changed=1
  fi
done
if [ "$changed" = 1 ]; then
  systemctl restart ssh 2>/dev/null || systemctl restart sshd
  echo "    SSH reiniciat (segueix a 22 i 2222)."
else
  echo "    (no s'ha trobat 'Port 443' a la config d'SSH)"
fi
sleep 1
if ss -tlnp 2>/dev/null | grep -E ':443[[:space:]]' | grep -q sshd; then
  echo "    AVIS: el 443 SEGUEIX ocupat pel SSH -> Caddy no podra arrencar. Revisa /etc/ssh/."
fi

echo ">>> [2/4] Instal·lant Caddy (si cal)..."
if ! command -v caddy >/dev/null 2>&1; then
  apt-get install -y debian-keyring debian-archive-keyring apt-transport-https curl
  curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' \
    | gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
  curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' \
    > /etc/apt/sources.list.d/caddy-stable.list
  apt-get update
  apt-get install -y caddy
else
  echo "    Caddy ja instal·lat."
fi

echo ">>> [3/4] Configurant el Caddyfile (sigphiai.com -> :8000)..."
cp "$APP/deploy/Caddyfile" /etc/caddy/Caddyfile
systemctl enable caddy >/dev/null 2>&1 || true
systemctl restart caddy

echo ">>> [4/4] Esperant que Caddy tregui el certificat (Let's Encrypt, ~20-40s)..."
sleep 25
systemctl status caddy --no-pager | head -n 6
echo ""
echo "--- Prova HTTPS (local, validant el certificat de sigphiai.com) ---"
curl -sS -m 25 --resolve sigphiai.com:443:127.0.0.1 https://sigphiai.com/api/health \
  && echo "  <- HTTPS OK!!! Ja tens https://sigphiai.com" \
  || echo "  (encara no; mira: journalctl -u caddy -n 40 --no-pager)"
