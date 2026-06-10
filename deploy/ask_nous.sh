#!/usr/bin/env bash
# Prova de qualitat dels textos nous (Lot 4 + Lot 5). Pregunta sobre cadascun i
# mostra l'inici de la resposta + les fonts, per confirmar que es recuperen bé i
# que l'OCR no ha entrat soroll.
# Ús:  bash deploy/ask_nous.sh
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
  curl -s -m 60 -X POST http://localhost:8000/api/chat \
    -H "Content-Type: application/json" \
    -d "{\"query\":\"$1\",\"history\":[]}" \
  | python3 -c "
import sys, json
raw = sys.stdin.read()
try:
    d = json.loads(raw)
    print('RESPOSTA:', d.get('answer', '')[:500])
    print()
    print('FONTS:', ' | '.join(d.get('sources', [])))
except Exception:
    print('(sense resposta valida del servidor -- possible limit de frequencia; espera 1 min i reintenta)')
"
  sleep 7   # sota el limit de 10/min (9 preguntes espaiades)
}

# --- Lot 4 ---
ask "Què ensenya el Mahabharata sobre el deure (dharma) en la guerra?"
ask "Què diu l'Adi Granth sobre el nom de Déu i la devoció?"
ask "Què és el canvi segons l'I Ching?"
ask "Què diuen els Gathes de Zaratustra sobre el bé i el mal?"
# --- Lot 5 ---
ask "Què diu Kautilya sobre el bon govern a l'Arthashastra?"
ask "Què diu Ibn Khaldun sobre l'ascens i la decadència de les dinasties?"
ask "Què diu Balmes sobre com pensar bé?"
ask "Què diu Wittgenstein sobre els límits del llenguatge i del món?"
ask "Quina és la idea d'Espanya segons Ganivet?"

echo ""
echo "================================================================"
echo ">>> Revisa: cada resposta hauria de citar el text correcte i llegir-se bé"
echo ">>> (sense paraules trencades de l'OCR). Ibn Khaldun (francès) i Wittgenstein"
echo ">>> (alemany/anglès) proven també la recuperació cross-lingual."
