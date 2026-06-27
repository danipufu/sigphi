#!/usr/bin/env bash
# NOMÉS LECTURA: recull proves del compromís (miner + persistència + vector d'entrada).
# No mata ni esborra res. Resultat per pantalla; el més important (SSH/persistència) al final.
#   bash deploy/forensics.sh 2>&1 | tee /tmp/forensics.txt
echo "######## MINER ########"
for p in $(pgrep -f a430f447 2>/dev/null) 657988; do
  [ -d /proc/$p ] || continue
  echo "--- PID $p ---"
  echo "exe:     $(ls -l /proc/$p/exe 2>/dev/null | sed 's/.*-> //')"
  echo "cmdline: $(tr '\0' ' ' < /proc/$p/cmdline 2>/dev/null)"
  echo "cwd:     $(ls -l /proc/$p/cwd 2>/dev/null | sed 's/.*-> //')"
  echo "started: $(ps -o lstart= -p $p 2>/dev/null)  ppid: $(ps -o ppid= -p $p 2>/dev/null)"
done

echo ""
echo "######## XARXA (connexions sortints = pool de minat?) ########"
ss -tnp 2>/dev/null | grep ESTAB | head -20

echo ""
echo "######## FITXERS SOSPITOSOS (/tmp /var/tmp /dev/shm) ########"
ls -la /tmp /var/tmp /dev/shm 2>/dev/null | grep -vE '^total|^d.* \.$|^d.* \.\.$'

echo ""
echo "######## PERSISTÈNCIA ########"
echo "-- crontab root --";        crontab -l 2>/dev/null
echo "-- /etc/cron* --";          ls -la /etc/cron.d/ /etc/cron.hourly/ /etc/cron.daily/ 2>/dev/null | grep -v '^total'
echo "-- /etc/rc.local --";       cat /etc/rc.local 2>/dev/null
echo "-- /etc/ld.so.preload --";  cat /etc/ld.so.preload 2>/dev/null
echo "-- serveis systemd recents --"; ls -lt /etc/systemd/system/*.service 2>/dev/null | head -8
echo "-- cua de ~/.bashrc i ~/.profile --"; tail -4 ~/.bashrc ~/.profile 2>/dev/null

echo ""
echo "######## CLAUS SSH AUTORITZADES (portes del darrere?) ########"
cat /root/.ssh/authorized_keys 2>/dev/null
cat ~/.ssh/authorized_keys 2>/dev/null

echo ""
echo "######## VECTOR D'ENTRADA (SSH) ########"
echo "-- últims logins (IPs) --"; last -i 2>/dev/null | head -12
echo "-- logins SSH acceptats --"; grep -h 'Accepted' /var/log/auth.log /var/log/auth.log.1 2>/dev/null | tail -12
echo "-- intents fallits (força bruta) --"; grep -hc 'Failed password' /var/log/auth.log /var/log/auth.log.1 2>/dev/null
echo ""
echo "######## FET ########"
