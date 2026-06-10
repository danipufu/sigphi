#!/usr/bin/env bash
# Diagnostic d'estat de SigPhi (NOMES lectura, no reinicia ni toca res).
# Us:  bash deploy/diag.sh
cd "$(dirname "$0")/.." 2>/dev/null

echo "=== 1) Servei actiu? ==="
systemctl is-active sigphi

echo ""
echo "=== 2) Estat (capcalera) ==="
systemctl status sigphi --no-pager 2>/dev/null | head -n 8

echo ""
echo "=== 3) Health a localhost:8000 ==="
curl -s -m 8 http://localhost:8000/api/health || echo "(no respon -> servei aturat o encara carregant el model)"

echo ""
echo ""
echo "=== 4) El Tractatus s'ha baixat al corpus? ==="
ls -la corpus/Wittgenstein__Tractatus_Ogden_en.txt 2>/dev/null || echo "(NO existeix -> la baixada del mirall va fallar)"

echo ""
echo "=== 5) Hi ha algun ingest corrent ara mateix? ==="
pgrep -af "scripts/ingest.py" || echo "(cap ingest en marxa)"
