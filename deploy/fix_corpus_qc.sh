#!/usr/bin/env bash
# QC del lot Perseus (TITOL != CONTINGUT) + reemplaçament de les Cartes de Sèneca.
#
# Esborra 5 obres mal classificades de la BD:
#   - Plato "Apology EN"            = l'Electra de Sòfocles (font XML soph.el_eng)
#   - Cicero "Tusculan Disp. EN"    = text llatí amb aparat crític (no anglès)
#   - Cicero "De Natura Deorum EN"  = duplicat byte-idèntic del Tusculan llatí
#   - Seneca "Epistles EN"          = Epistulae Morales en llatí amb aparat
#   - Seneca "Epistles LA"          = introducció anglesa sobre HIPÒCRATES
# (El De Natura Deorum real ja és dins "Cicero's Tusculan Disputations" -bundle
#  Yonge-; l'Apologia i el Tusculan anglès tenen còpies netes que es conserven.)
#
# I afegeix la traducció anglesa NETA de les Cartes a Lucili (Gummere, Wikisource),
# que la BD no tenia en anglès.
#
# Ús:  sudo bash deploy/fix_corpus_qc.sh
# (Deixa la VNC oberta: l'ingest va en primer pla, pot trigar uns minuts.)
set -e
APP=/home/daniel/sigphi
PY=$APP/venv/bin/python
cd "$APP"

echo ">>> [1/6] Esborrant obres mal classificades de la BD (Perseus QC)..."
sudo -u daniel bash -c "cd $APP && source venv/bin/activate && VECTOR_DB_TYPE=qdrant python scripts/cleanup.py --apply"

echo ">>> [2/6] Esborrant els .txt equivocats del corpus (per no re-ingestar-los)..."
sudo -u daniel rm -f \
  "$APP/corpus/Plato__Apology_EN_en.txt" \
  "$APP/corpus/Cicero__Tusculan_Disputations_EN_en.txt" \
  "$APP/corpus/Cicero__De_Natura_Deorum_EN_en.txt" \
  "$APP/corpus/Seneca__Epistles_EN_en.txt" \
  "$APP/corpus/Seneca__Epistles_LA_la.txt"

echo ">>> [3/6] Baixant Sèneca — Cartes a Lucili (anglès net, Wikisource)..."
sudo -u daniel "$PY" scripts/download_wikisource.py

echo ">>> [4/6] Aturant el servei (alliberar RAM per a l'ingest)..."
systemctl stop sigphi

echo ">>> [5/6] Ingest dels fitxers nous cap a Qdrant (espera, no tanquis)..."
sudo -u daniel bash -c "cd $APP && source venv/bin/activate && VECTOR_DB_TYPE=qdrant python -u scripts/ingest.py"

echo ">>> [6/6] Reiniciant el servei sigphi..."
systemctl start sigphi
sleep 3
systemctl status sigphi --no-pager | head -n 5
echo ">>> Fet. 5 obres mal classificades eliminades; Cartes de Sèneca (EN) afegides."
echo ">>> Comprova:  curl -s 'http://localhost:8000/api/catalog?cb=qcdone' | grep -i 'Moral Letters'"
