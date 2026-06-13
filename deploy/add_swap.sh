#!/usr/bin/env bash
# Crea un fitxer d'intercanvi (SWAP) de 4 GB i el deixa permanent. És "RAM virtual"
# en disc: evita que el servei es pengi o el mati l'OOM-killer quan la memòria real
# s'esgota (p. ex. amb el corpus gros + embedder + Qdrant). Més lent que la RAM real,
# però barat (gratis) i evita les caigudes.
#
# Ús:  sudo bash deploy/add_swap.sh
set -e
SWAP=/swapfile
SIZE=4G

if swapon --show | grep -q "$SWAP"; then
    echo ">>> Ja hi ha swap actiu a $SWAP. Estat actual:"
    swapon --show
    free -h
    exit 0
fi

echo ">>> Creant swapfile de $SIZE a $SWAP..."
fallocate -l "$SIZE" "$SWAP" 2>/dev/null || dd if=/dev/zero of="$SWAP" bs=1M count=4096
chmod 600 "$SWAP"
mkswap "$SWAP"
swapon "$SWAP"

# Persistència després de reiniciar el servidor.
if ! grep -q "^$SWAP" /etc/fstab; then
    echo "$SWAP none swap sw 0 0" >> /etc/fstab
fi

# Fer servir el swap només quan calgui de debò (no agressivament).
sysctl -w vm.swappiness=10 >/dev/null
if ! grep -q "vm.swappiness" /etc/sysctl.conf; then
    echo "vm.swappiness=10" >> /etc/sysctl.conf
fi

echo ">>> Fet. Memòria ara:"
free -h
echo ">>> Recomanació: reinicia el servei perquè arrenqui amb marge -> systemctl restart sigphi"
