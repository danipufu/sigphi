#!/usr/bin/env bash
# Comprova els textos espirituals/orientals del corpus (Tao, Confuci).
# Mostra l'inici de cada resposta + les fonts.
# Ús:  bash deploy/ask_religio.sh
ask() {
  echo ""
  echo "================================================================"
  echo "PREGUNTA: $1"
  echo "----------------------------------------------------------------"
  curl -s -X POST http://localhost:8000/api/chat \
    -H "Content-Type: application/json" \
    -d "{\"query\":\"$1\",\"history\":[]}" \
  | python3 -c "import sys,json; d=json.load(sys.stdin); print('RESPOSTA:', d['answer'][:450]); print(); print('FONTS:', ' | '.join(d['sources']))"
}

ask "Què diu el Tao Te Ching sobre el wu wei o no-acció?"
ask "Què ensenyava Confuci sobre la benevolència (ren)?"

echo ""
echo "================================================================"
echo ">>> Si surten respostes amb fonts de Laozi i Confuci, funcionen."
