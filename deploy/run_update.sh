#!/usr/bin/env bash
# Actualització jun-2026 (auditoria de cobertura). En un sol pas:
#   - textos nous: Hegel (Filosofia/Història), Aristòtil (Organon, Física),
#     Aquino (Summa Contra Gentiles), Hobbes (Elements of Law, Behemoth),
#     Spencer (Data of Ethics, Man versus the State)
#   - neteja file-level de brossa d'OCR (Bergson "Creative evolution" 948 chunks
#     il·legibles, etc.) que NO es pot separar per autor+títol (cas/prefix)
#   - treu el fitxer orfe de Bertrand Russell (mort 1970 -> no PD a la UE fins 2041)
#   - re-ingesta resumible + reinici del servei
#
# Ús:  sudo bash deploy/run_update.sh
# (Va en primer pla; l'ingest pot trigar ~10-15 min. Recomanat: deploy/backup.sh abans.)
set -e
APP=/home/daniel/sigphi
PY=$APP/venv/bin/python
cd "$APP"
RUNPY() { sudo -u daniel bash -c "cd $APP && source venv/bin/activate && VECTOR_DB_TYPE=qdrant $*"; }

echo ">>> [1/7] git pull (scripts nous + remove_files.py)..."
sudo -u daniel git pull

# La brossa d'OCR comparteix títol amb la còpia neta (difereix només en majúscules
# o és un prefix), així que cleanup.py (LIKE, insensible a majúsc.) no la pot aïllar.
# grep SÍ és sensible a majúscules -> troba el FITXER exacte; remove_files.py esborra
# els chunks pel chunk_id ({fitxer}#n), sense tocar la còpia neta.
PAT='^work: (Creative evolution|The Meaning Of The War|Cato maior de senectute)$'
echo ">>> [2/7] Localitzant fitxers de brossa d'OCR (case-sensitive)..."
GARBAGE=$(grep -rlE "$PAT" corpus/ 2>/dev/null | xargs -rn1 basename || true)
echo "    trobats: ${GARBAGE:-(cap)}"

if [ -n "$GARBAGE" ]; then
  echo ">>> [3/7] DRY-RUN: chunks a esborrar (han de ser ~948 / ~31 / ~52)..."
  RUNPY "python scripts/remove_files.py $GARBAGE"
  echo "    >>> Comprova els recomptes de dalt."
  read -p "    ENTER per APLICAR l'esborrat, o Ctrl-C per avortar... " _
  RUNPY "python scripts/remove_files.py --apply $GARBAGE"
  ( cd corpus && sudo -u daniel rm -f $GARBAGE )
  echo "    brossa d'OCR eliminada."
else
  echo ">>> [3/7] Cap fitxer de brossa trobat (potser ja s'havia tret)."
fi

echo ">>> [4/7] Treient el fitxer orfe de Bertrand Russell (els chunks ja són fora)..."
sudo -u daniel rm -f corpus/Bertrand_Russell__*.txt

echo ">>> [5/7] Baixant els textos nous (Gutenberg + archive.org)..."
sudo -u daniel "$PY" scripts/download_sacred.py
sudo -u daniel "$PY" scripts/download_archive.py

echo ">>> [6/7] Aturant el servei i ingerint els nous fitxers (espera, no tanquis)..."
systemctl stop sigphi
RUNPY "python -u scripts/ingest.py"

echo ">>> [7/7] Reiniciant el servei sigphi..."
systemctl start sigphi
sleep 3
systemctl status sigphi --no-pager | head -n 5
echo ">>> Fet. Textos nous afegits, brossa i Russell fora, servei actiu."
