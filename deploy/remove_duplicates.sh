#!/usr/bin/env bash
# Elimina duplicats autèntics del corpus de forma PERMANENT (BD + ingest_done.txt
# + el .txt del corpus). IMPORTANT: cal esborrar el .txt; si no, una re-ingesta
# posterior els RESSUSCITA (això va passar amb overnight_update del 27-juny).
# Executa des de l'arrel del projecte amb el venv actiu:
#   source venv/bin/activate
#   sudo bash deploy/remove_duplicates.sh
set -e

cd /home/daniel/sigphi
PY=/home/daniel/sigphi/venv/bin/python3

# La còpia DOLENTA de cada parella (OCR-brossa / wiki-markup / parcial / curta);
# es conserva sempre l'altra versió (vegeu el comentari de cada línia).
FILES=(
  "Henri_Bergson__Creative_evolution_en.txt"                            # OCR brossa (es manté Creative_Evolution)
  "Henri_Bergson__The_Meaning_Of_The_War_en.txt"                        # OCR (es manté Life & Matter)
  "Francis_Bacon__Novum_Organum_en.txt"                                 # wiki {| (es manté Novum organum or True...)
  "Harriet_Taylor__Enfranchisement_of_women_Reprinted_from_the_Westmi_en.txt"  # nota de revista (es manté la neta)
  "Marcus_Aurelius__Thoughts_of_Marcus_Aurelius_en.txt"                 # curta (es manté ...Antoninus)
  "Plotinus__Select_works_of_Plotinus_translated_from_the_Greek_en.txt" # dup (es manté Select Works of Plotinus)
  "Nietzsche__The_Will_to_Power_An_Attempted_Transvaluation_of_A_en.txt" # parcial III-IV (es manté el complet)
)

echo "=== DRY-RUN (--apply no inclòs) ==="
VECTOR_DB_TYPE=qdrant $PY scripts/remove_files.py "${FILES[@]}"

echo ""
read -p "Confirmes l'eliminació PERMANENT (BD + .txt)? (s/N) " ans
if [[ "$ans" != "s" && "$ans" != "S" ]]; then
  echo "Cancel·lat."
  exit 0
fi

echo "=== APLICANT ==="
VECTOR_DB_TYPE=qdrant $PY scripts/remove_files.py --apply "${FILES[@]}"
for f in "${FILES[@]}"; do rm -f "corpus/$f"; done   # CLAU: esborrar el .txt perquè no ressusciti
echo "Fet (chunks + ingest_done + fitxers .txt eliminats)."
