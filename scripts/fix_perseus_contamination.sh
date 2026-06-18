#!/usr/bin/env bash
# Remediació de textos Perseus contaminats:
#   - Elimina 3 fitxers amb contingut equivocat (contingut d'un altre autor)
#   - Força re-ingesta de 9 textos amb $Log: CVS noise (ara strip_perseus_frontmatter els neteja)
#   - Baixa De Anima EN net des de Wikisource (reemplaça el Perseus corrupte)
set -e
cd "$(dirname "$0")/.."

API_KEY="e5808c629c34ba57bba9f68f2090e92e"
BASE="http://localhost:8000"

echo "=== 1/5 Eliminant del DB: contingut equivocat ==="
for AUTHOR_WORK in \
    'Aristotle|De Anima EN' \
    'Plato|Phaedo EN' \
    'Plato|Symposium EN'; do
  AUTHOR="${AUTHOR_WORK%%|*}"
  WORK="${AUTHOR_WORK##*|}"
  echo "  remove: $AUTHOR — $WORK"
  curl -s -X POST "$BASE/api/admin/remove" \
    -H "X-API-Key: $API_KEY" -H "Content-Type: application/json" \
    -d "{\"author\": \"$AUTHOR\", \"work\": \"$WORK\"}"
  echo
done

echo "=== 2/5 Esborrant fitxers de corpus amb contingut equivocat ==="
for F in corpus/Aristotle__De_Anima_EN_en.txt \
          corpus/Plato__Phaedo_EN_en.txt \
          corpus/Plato__Symposium_EN_en.txt; do
  [ -f "$F" ] && rm "$F" && echo "  rm $F" || echo "  (no existeix) $F"
done

echo "=== 3/5 Eliminant del DB: textos amb \$Log: CVS noise (es re-ingestaran nets) ==="
curl -s -X POST "$BASE/api/admin/remove" \
  -H "X-API-Key: $API_KEY" -H "Content-Type: application/json" \
  -d '{"author": "Aristotle", "work": "Politics EN"}' && echo
curl -s -X POST "$BASE/api/admin/remove" \
  -H "X-API-Key: $API_KEY" -H "Content-Type: application/json" \
  -d '{"author": "Aristotle", "work": "Nicomachean Ethics EN"}' && echo
curl -s -X POST "$BASE/api/admin/remove" \
  -H "X-API-Key: $API_KEY" -H "Content-Type: application/json" \
  -d '{"author": "Aristotle", "work": "Metaphysics EN"}' && echo
curl -s -X POST "$BASE/api/admin/remove" \
  -H "X-API-Key: $API_KEY" -H "Content-Type: application/json" \
  -d '{"author": "Aristotle", "work": "Poetics EN"}' && echo
curl -s -X POST "$BASE/api/admin/remove" \
  -H "X-API-Key: $API_KEY" -H "Content-Type: application/json" \
  -d '{"author": "Aristotle", "work": "De Anima GR"}' && echo
curl -s -X POST "$BASE/api/admin/remove" \
  -H "X-API-Key: $API_KEY" -H "Content-Type: application/json" \
  -d '{"author": "Plato", "work": "Republic GR"}' && echo
curl -s -X POST "$BASE/api/admin/remove" \
  -H "X-API-Key: $API_KEY" -H "Content-Type: application/json" \
  -d '{"author": "Marcus Aurelius", "work": "Meditations GR"}' && echo
curl -s -X POST "$BASE/api/admin/remove" \
  -H "X-API-Key: $API_KEY" -H "Content-Type: application/json" \
  -d '{"author": "Lucretius"}' && echo

echo "=== 4/5 Netejant ingest_done.txt ==="
DONE="corpus/ingest_done.txt"
if [ -f "$DONE" ]; then
  for P in Aristotle__De_Anima_EN Plato__Phaedo_EN Plato__Symposium_EN \
            Aristotle__Politics_EN Aristotle__Nicomachean_Ethics_EN \
            Aristotle__Metaphysics_EN Aristotle__Poetics_EN \
            Aristotle__De_Anima_GR Plato__Republic_GR \
            Marcus_Aurelius__Meditations_GR \
            Lucretius__De_Rerum_Natura_EN Lucretius__De_Rerum_Natura_LA; do
    sed -i "/$P/d" "$DONE"
    echo "  removed from done_log: $P"
  done
else
  echo "  (ingest_done.txt no trobat, s'ometrà)"
fi

echo "=== 5/5 Baixant De Anima EN (Wikisource Collier 1855) ==="
python scripts/download_wikisource.py

echo ""
echo "Ara executa:"
echo "  python scripts/ingest.py"
echo "(i reinicia el servei si cal per aplicar el fix de Rule 20)"
