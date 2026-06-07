#!/usr/bin/env bash
# Instal·la SigPhi com a servei systemd, l'arrenca i prova el RAG real.
# Ús:  sudo bash deploy/start_app.sh
set -e
cd /home/daniel/sigphi

echo ">>> [1/3] Instal·lant el servei systemd..."
cp deploy/systemd/sigphi.service /etc/systemd/system/sigphi.service
systemctl daemon-reload
systemctl enable --now sigphi

echo ">>> [2/3] Esperant que l'app carregui el model i respongui (1-2 min)..."
ok=0
for i in $(seq 1 48); do
  if curl -sf http://localhost:8000/api/health >/dev/null 2>&1; then ok=1; break; fi
  sleep 5
done
if [ "$ok" != "1" ]; then
  echo ">>> L'app no respon. Revisa els logs:  journalctl -u sigphi -n 40 --no-pager"
  exit 1
fi

echo ">>> /api/health:"
curl -s http://localhost:8000/api/health; echo ""

echo ">>> [3/3] Prova de RAG amb tot el corpus (pregunta sobre Adam Smith)..."
curl -s -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"query":"Què deia Adam Smith sobre la divisió del treball?","history":[]}'
echo ""
echo ""
echo ">>> SigPhi actiu com a servei. Comandes útils:"
echo "    Estat:   systemctl status sigphi --no-pager"
echo "    Logs:    journalctl -u sigphi -f"
