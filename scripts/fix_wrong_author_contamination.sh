#!/usr/bin/env bash
# Elimina 18 fitxers amb atribució d'autor equivocada detectats en la revisió de
# soroll del corpus. Llegeix el nom exacte d'autor/obra directament de cada
# capçalera SIGPHI per garantir que la crida a /api/admin/remove coincideixi amb
# el valor indexat al DB.
set -e
cd "$(dirname "$0")/.."

API_KEY="e5808c629c34ba57bba9f68f2090e92e"
BASE="http://localhost:8000"
DONE="corpus/ingest_done.txt"

remove_file() {
  local filepath="$1"
  if [ ! -f "$filepath" ]; then
    echo "  (no existeix, omès) $filepath"
    return
  fi
  # Llegeix autor i obra de la capçalera SIGPHI (insensible a majúscules)
  local author work
  author=$(grep -i "^author:" "$filepath" | head -1 | sed 's/^[Aa]uthor: *//')
  work=$(grep -i "^work:" "$filepath" | head -1 | sed 's/^[Ww]ork: *//')
  echo "  remove: $author — $work"
  curl -s -X POST "$BASE/api/admin/remove" \
    -H "X-API-Key: $API_KEY" -H "Content-Type: application/json" \
    -d "{\"author\": $(echo "$author" | python3 -c 'import json,sys; print(json.dumps(sys.stdin.read().strip()))'), \"work\": $(echo "$work" | python3 -c 'import json,sys; print(json.dumps(sys.stdin.read().strip()))')}"
  echo
  rm -f "$filepath"
  # Treu del done_log (usa el nom base sense extensió)
  local base
  base=$(basename "$filepath" .txt)
  [ -f "$DONE" ] && sed -i "/$base/d" "$DONE"
}

echo "=== Bergson: autors equivocats (iarchive Henri ≠ Henri Bergson) ==="
remove_file "corpus/Henri_Bergson__Legend_in_Japanese_art_a_description_of_historical_en.txt"
remove_file "corpus/Henri_Bergson__Memoirs_of_the_Sansons_from_private_notes_and_docu_en.txt"
remove_file "corpus/Henri_Bergson__Mohammedandchalemagne_en.txt"
remove_file "corpus/Henri_Bergson__The_Jewish_world_in_the_time_of_Jesus_en.txt"
remove_file "corpus/Henri_Bergson__Nouvelles_tables_trigonom_triques_fondamentales_co_fr.txt"

echo "=== Bergson: duplicat iarchive (versió Gutenberg ja existeix) ==="
remove_file "corpus/Henri_Bergson__The_Meaning_Of_The_War_en.txt"

echo "=== Bergson: font secundaria / revista ==="
remove_file "corpus/Henri_Bergson__La_Revue_de_Paris_fr.txt"
remove_file "corpus/Henri_Bergson__The_Philosophy_of_Bergson_Russell__en.txt"

echo "=== Leibniz / Thoreau: revista The Atlantic Monthly ==="
remove_file "corpus/Leibniz__The_Atlantic_Monthly_en.txt"
remove_file "corpus/Thoreau__The_Atlantic_Monthly_en.txt"

echo "=== Olympe de Gouges: diari Le Figaro ==="
remove_file "corpus/Olympe_de_Gouges__Le_Figaro_fr.txt"

echo "=== Kierkegaard: plantilla de navegació de Wikisource ==="
remove_file "corpus/Kierkegaard__Forside_da.txt"

echo "=== Mary Wollstonecraft: text d'Edmund Burke ==="
remove_file "corpus/Mary_Wollstonecraft__Reflections_on_the_Revolution_in_France_en.txt"

echo "=== Denis Diderot: text de Robert Ingersoll ==="
remove_file "corpus/Denis_Diderot__The_Great_Infidels_en.txt"

echo "=== Emma Goldman: text d'Alexander Berkman ==="
remove_file "corpus/Emma_Goldman__Prison_Memoirs_of_an_Anarchist_en.txt"

echo "=== Fichte / Pascal / Confuci: biografies sobre l'autor, no de l'autor ==="
remove_file "corpus/Johann_Fichte__Memoir_of_Johann_Gottlieb_Fichte_en.txt"
remove_file "corpus/Pascal__The_Life_and_Writings_of_Blaise_Pascal_en.txt"
remove_file "corpus/Confucius__The_Life_Labours_and_Doctrines_of_Confucius_en.txt"

echo ""
echo "Fet. 18 fitxers eliminats del DB i del corpus."
echo "No cal re-ingestar res: tots eren fitxers a treure, no a actualitzar."
