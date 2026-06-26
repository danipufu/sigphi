#!/usr/bin/env bash
# Elimina duplicats autèntics del corpus (BD + ingest_done.txt).
# Executa des de l'arrel del projecte amb el venv actiu:
#   source venv/bin/activate
#   sudo bash deploy/remove_duplicates.sh
set -e

cd /home/daniel/sigphi

FILES=(
  "Henri_Bergson__Creative_evolution_en.txt"
  "Henri_Bergson__The_Meaning_Of_The_War_en.txt"
  "Francis_Bacon__Novum_Organum_en.txt"
  "Harriet_Taylor__Enfranchisement_of_women_Reprinted_from_the_Westmi_en.txt"
  "Marcus_Aurelius__Thoughts_of_Marcus_Aurelius_en.txt"
  "Plotinus__Select_works_of_Plotinus_translated_from_the_Greek_en.txt"
  "Nietzsche__The_Will_to_Power_An_Attempted_Transvaluation_of_A_en.txt"
)

echo "=== DRY-RUN (--apply no inclòs) ==="
VECTOR_DB_TYPE=qdrant python scripts/remove_files.py "${FILES[@]}"

echo ""
read -p "Confirmes l'eliminació? (s/N) " ans
if [[ "$ans" != "s" && "$ans" != "S" ]]; then
  echo "Cancel·lat."
  exit 0
fi

echo "=== APLICANT ==="
VECTOR_DB_TYPE=qdrant python scripts/remove_files.py --apply "${FILES[@]}"
echo "Fet."
