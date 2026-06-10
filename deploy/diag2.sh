#!/usr/bin/env bash
# Diagnostic d'una consulta + log del servei, per veure PER QUE /api/chat torna buit.
# Us:  bash deploy/diag2.sh
cd "$(dirname "$0")/.." 2>/dev/null

echo "=== UNA consulta (cos + codi HTTP + temps) ==="
curl -s -m 90 \
  -w "\n[HTTP %{http_code} | temps %{time_total}s | bytes %{size_download}]\n" \
  -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"query":"Que diu Balmes sobre pensar be","history":[]}'

echo ""
echo "=== Ultimes 35 linies del log del servei (errors aqui) ==="
journalctl -u sigphi --no-pager -n 35 2>/dev/null | tail -n 35
