#!/usr/bin/env bash
# Elimina pàgines-índex de Wikisource ingerides per error com a obres (només TOC/
# llistes, sense text real). Dry-run primer; cal confirmar per esborrar.
#   source venv/bin/activate
#   sudo bash deploy/remove_stubs.sh
set -e

cd /home/daniel/sigphi
PY=/home/daniel/sigphi/venv/bin/python3

FILES=(
  "Thomas_Aquinas__Summa_Theologiae_la.txt"
  "Montesquieu__Persian_Letters_en.txt"
  "Montesquieu__The_Spirit_of_Laws_1758__en.txt"
  "Aristotle__Organon_en.txt"
  "Aristotle__The_Works_of_Aristotle_en.txt"
  "Epictetus__Enchiridion_Epictetus__en.txt"
  "Emma_Goldman__Prison_Memoirs_of_an_Anarchist_en.txt"
  "Emma_Goldman__Mother_Earth_en.txt"
)

echo "=== DRY-RUN ==="
VECTOR_DB_TYPE=qdrant $PY scripts/remove_files.py "${FILES[@]}"

echo ""
read -p "Confirmes l'eliminació? (s/N) " ans
if [[ "$ans" != "s" && "$ans" != "S" ]]; then
  echo "Cancel·lat."
  exit 0
fi

echo "=== APLICANT ==="
VECTOR_DB_TYPE=qdrant $PY scripts/remove_files.py --apply "${FILES[@]}"
# també esborrem els .txt del corpus perquè no es re-ingereixin
for f in "${FILES[@]}"; do rm -f "corpus/$f"; done
echo "Fet (chunks + fitxers .txt eliminats)."
