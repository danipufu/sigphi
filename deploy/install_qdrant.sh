#!/usr/bin/env bash
# Instal·la Docker (si cal) i arrenca Qdrant al VPS.
# Qdrant queda lligat a 127.0.0.1 (NOMÉS localhost) perquè per defecte no té
# autenticació: així no és accessible des d'Internet, només des de l'app.
# Dades persistents a /home/daniel/qdrant_storage (al disc de 128 GB).
#
# Ús:  sudo bash deploy/install_qdrant.sh
set -e

QDRANT_DIR=/home/daniel/qdrant_storage

echo ">>> [0/3] curl..."
command -v curl >/dev/null 2>&1 || { apt-get update; apt-get install -y curl; }

echo ">>> [1/3] Docker..."
if ! command -v docker >/dev/null 2>&1; then
  apt-get update
  apt-get install -y docker.io
  systemctl enable --now docker
else
  echo "    Docker ja instal·lat."
fi

echo ">>> [2/3] Arrencant contenidor Qdrant..."
mkdir -p "$QDRANT_DIR"
docker rm -f qdrant >/dev/null 2>&1 || true
docker run -d --name qdrant --restart unless-stopped \
  -p 127.0.0.1:6333:6333 \
  -v "$QDRANT_DIR":/qdrant/storage \
  qdrant/qdrant

echo ">>> [3/3] Esperant que Qdrant respongui..."
ok=0
for i in $(seq 1 12); do
  if curl -sf http://localhost:6333/healthz >/dev/null 2>&1; then ok=1; break; fi
  sleep 3
done
if [ "$ok" = "1" ]; then
  echo ">>> OK: Qdrant escolta a http://localhost:6333 (només localhost)."
else
  echo ">>> Qdrant encara no respon. Revisa-ho amb:  docker logs qdrant"
fi
