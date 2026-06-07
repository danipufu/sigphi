#!/usr/bin/env bash
# Prova els textos sagrats nous. Espera que el servei estigui llest i pregunta
# sobre cadascun, mostrant l'inici de la resposta + les fonts.
# Ús:  bash deploy/ask_sagrats.sh
echo ">>> Esperant que el servei respongui (pot estar carregant el model)..."
for i in $(seq 1 30); do
  curl -sf http://localhost:8000/api/health >/dev/null 2>&1 && break
  sleep 5
done

ask() {
  echo ""
  echo "================================================================"
  echo "PREGUNTA: $1"
  echo "----------------------------------------------------------------"
  curl -s -X POST http://localhost:8000/api/chat \
    -H "Content-Type: application/json" \
    -d "{\"query\":\"$1\",\"history\":[]}" \
  | python3 -c "import sys,json; d=json.load(sys.stdin); print('RESPOSTA:', d['answer'][:420]); print(); print('FONTS:', ' | '.join(d['sources']))"
}

ask "Què diu la Bíblia sobre l'amor al proïsme?"
ask "Què diu l'Alcorà sobre la misericòrdia?"
ask "Què ensenya la Bhagavad Gita sobre el deure (dharma)?"
ask "Què diu el Dhammapada sobre la ment?"

echo ""
echo "================================================================"
echo ">>> Si surten respostes amb les fonts corresponents, els 4 textos funcionen."
