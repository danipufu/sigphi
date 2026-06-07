#!/usr/bin/env bash
# Comprova l'idioma: fa 2 preguntes EN CATALÀ i mostra NOMÉS l'inici de cada
# resposta + les fonts (perquè es llegeixi bé i no es desbordi la pantalla).
# Ús:  bash deploy/ask_ca.sh
ask() {
  echo ""
  echo "================================================================"
  echo "PREGUNTA (català): $1"
  echo "----------------------------------------------------------------"
  curl -s -X POST http://localhost:8000/api/chat \
    -H "Content-Type: application/json" \
    -d "{\"query\":\"$1\",\"history\":[]}" \
  | python3 -c "import sys,json; d=json.load(sys.stdin); print('RESPOSTA:', d['answer'][:450]); print(); print('FONTS:', ' | '.join(d['sources']))"
}

ask "Què deia Epictet sobre allò que depèn de nosaltres?"
ask "Compara la idea de justícia en Plató i en Aristòtil."

echo ""
echo "================================================================"
echo ">>> Si les dues respostes comencen en català, la regla d'idioma funciona."
