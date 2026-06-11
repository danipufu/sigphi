#!/usr/bin/env bash
# Diagnostic de xarxa per preparar l'HTTPS: per que 80/443 es veuen FILTRATS des de
# fora (timeout). Mostra el tallafoc, que escolta, i si hi ha web server. NOMES llegeix.
# Us:  sudo bash deploy/net_diag.sh
echo "=== 1) ufw ==="
ufw status verbose 2>/dev/null || echo "(ufw no instal·lat)"

echo ""
echo "=== 2) nftables (regles actives) ==="
nft list ruleset 2>/dev/null | head -n 60 || echo "(cap regla nft / no disponible)"

echo ""
echo "=== 3) iptables -S ==="
iptables -S 2>/dev/null | head -n 40 || echo "(no disponible)"

echo ""
echo "=== 4) Ports TCP escoltant (busca 80, 443, 8000) ==="
ss -tlnp 2>/dev/null || netstat -tlnp 2>/dev/null

echo ""
echo "=== 5) Web server ja instal·lat? ==="
{ command -v caddy >/dev/null && echo "caddy: $(caddy version)"; } || echo "caddy: NO instal·lat"
{ command -v nginx >/dev/null && nginx -v; } || echo "nginx: NO instal·lat"

echo ""
echo "=== 6) Prova local del 8000 (ha de respondre) ==="
curl -s -m 5 http://localhost:8000/api/health || echo "(8000 local no respon)"
echo ""
echo ">>> Fet. Ensenya'm tota la sortida."
