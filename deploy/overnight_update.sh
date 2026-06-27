#!/usr/bin/env bash
# Actualització completa desatesa (pensada per llançar de nit i deixar córrer):
#   1. git pull
#   2. eliminar 8 stubs d'índex de Wikisource (BD + .txt)
#   3. baixar els textos nous (Montesquieu EN + parts de l'Organon)
#   4. re-ingerir TOTS els Wikisource nets (aplica strip_mediawiki_markup) + els nous
#   5. reaixecar el servei i verificar la salut del corpus
#
# Llança'l així (sobreviu a la desconnexió) i ves a dormir:
#   nohup bash deploy/overnight_update.sh > ~/overnight.log 2>&1 &
#   tail -f ~/overnight.log     # opcional, per mirar; Ctrl-C no atura la feina
#
# El web estarà avall durant la re-ingesta (~1h) i s'aixeca sol al final.
# El servei es REAIXECA sempre, encara que algun pas falli (trap EXIT).

cd /home/daniel/sigphi
PY=/home/daniel/sigphi/venv/bin/python3
log(){ echo ""; echo "===== $(date '+%F %H:%M:%S')  $*  ====="; }

log "0/7  git pull"
git pull

log "1/7  Eliminar 8 stubs d'índex (BD + fitxers .txt)"
STUBS=(
  "Thomas_Aquinas__Summa_Theologiae_la.txt"
  "Montesquieu__Persian_Letters_en.txt"
  "Montesquieu__The_Spirit_of_Laws_1758__en.txt"
  "Aristotle__Organon_en.txt"
  "Aristotle__The_Works_of_Aristotle_en.txt"
  "Epictetus__Enchiridion_Epictetus__en.txt"
  "Emma_Goldman__Prison_Memoirs_of_an_Anarchist_en.txt"
  "Emma_Goldman__Mother_Earth_en.txt"
)
VECTOR_DB_TYPE=qdrant $PY scripts/remove_files.py --apply "${STUBS[@]}" || true
for f in "${STUBS[@]}"; do rm -f "corpus/$f"; done

log "2/7  Baixar textos nous (Montesquieu Spirit of Laws/Persian Letters EN + Organon)"
$PY scripts/download_archive.py || true
$PY scripts/download_wikisource.py || true

log "3/7  Aturar el servei (re-ingesta consistent)"
systemctl stop sigphi
trap 'echo ">>> (trap) reaixecant servei"; systemctl start sigphi 2>/dev/null || true' EXIT

log "4/7  Treure els chunks Wikisource vells perquè es re-ingereixin nets"
WIKI=$(grep -il "^Source:.*wikisource" corpus/*.txt | xargs -n1 basename)
echo "    $(echo "$WIKI" | wc -l) fitxers Wikisource"
VECTOR_DB_TYPE=qdrant $PY scripts/remove_files.py --apply $WIKI || true

log "5/7  Ingerir (Wikisource net + textos nous d'archive.org)"
VECTOR_DB_TYPE=qdrant $PY scripts/ingest.py

log "6/7  Reaixecar el servei"
systemctl start sigphi

log "7/7  Salut del corpus"
sleep 5
VECTOR_DB_TYPE=qdrant $PY scripts/corpus_health.py | grep "##" || true
echo ""
curl -s http://localhost:8000/api/health || true

log "FET — revisa més amunt el recompte de problemes i que el servei respongui"
