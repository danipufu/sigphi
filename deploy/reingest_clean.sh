#!/usr/bin/env bash
# Re-ingesta NETA dels fitxers amb boilerplate de procedència (Produced by,
# [Illustration], peus d'escaneig, notes de transcriptor), aplicant la nova
# strip_editorial_boilerplate. Treu els chunks vells, re-ingereix net i re-passa
# el dedup (per si algun duplicat byte-idèntic ressorgeix). El servei queda avall
# durant la re-ingesta i s'aixeca sol al final.
#   nohup bash deploy/reingest_clean.sh > ~/rc.log 2>&1 &
#   tail -f ~/rc.log

# GUARD: una sola instància (la consola web pot duplicar l'enganxat).
exec 9>/tmp/reingest_clean.lock
if ! flock -n 9; then echo ">>> Ja n'hi ha una en curs. Surto."; exit 0; fi

cd /home/daniel/sigphi
PY=/home/daniel/sigphi/venv/bin/python3
git pull 2>&1 | tail -1

AFFECTED=$(grep -lE 'Produced by |\[Illustration|Digitized by|Google Book Search|Transcriber' corpus/*.txt 2>/dev/null | xargs -n1 basename | tr '\n' ' ')
echo ">>> Fitxers afectats a re-ingerir net: $(echo $AFFECTED | wc -w)"

systemctl stop sigphi
echo "===== 1/4  treure chunks vells ====="
su daniel -c "cd /home/daniel/sigphi && VECTOR_DB_TYPE=qdrant $PY scripts/remove_files.py --apply $AFFECTED 2>&1 | tail -2"
echo "===== 2/4  re-ingerir net (hores) ====="
su daniel -c "cd /home/daniel/sigphi && VECTOR_DB_TYPE=qdrant $PY scripts/ingest.py 2>&1 | tail -4"
echo "===== 3/4  re-dedup (duplicats byte-idèntics que ressorgeixin) ====="
su daniel -c "cd /home/daniel/sigphi && VECTOR_DB_TYPE=qdrant $PY scripts/dedup.py --apply 2>&1 | tail -2"
systemctl start sigphi
sleep 5
echo "===== 4/4  salut del corpus ====="
su daniel -c "cd /home/daniel/sigphi && VECTOR_DB_TYPE=qdrant $PY scripts/corpus_health.py 2>/dev/null | grep '##'"
curl -s --max-time 5 localhost:8000/api/health
echo ""
echo ">>> FET"
