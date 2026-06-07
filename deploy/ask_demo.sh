#!/usr/bin/env bash
# Demostració: fa unes quantes preguntes a SigPhi (localhost:8000) i mostra
# les respostes amb les fonts. Et permet "veure'l funcionar" des de la VNC
# sense haver d'escriure res.
# Ús:  bash deploy/ask_demo.sh
ask() {
  echo ""
  echo "================================================================"
  echo "PREGUNTA: $1"
  echo "----------------------------------------------------------------"
  curl -s -X POST http://localhost:8000/api/chat \
    -H "Content-Type: application/json" \
    -d "{\"query\":\"$1\",\"history\":[]}"
  echo ""
}

ask "Què deia Epictet sobre allò que depèn de nosaltres?"
ask "Compara la idea de justícia en Plató i en Aristòtil."
ask "What did Nietzsche mean by the will to power?"

echo ""
echo "================================================================"
echo ">>> Demo acabada."
