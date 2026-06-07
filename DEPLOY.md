# Desplegament de SigPhi al VPS (Qdrant + corpus complet)

Estat: tot el codi (Blocs 7–12 + backend Qdrant) validat. Qdrant ja instal·lat
al VPS (`docker ps` ha de mostrar el contenidor `qdrant`).

Treballa com a usuari **`daniel`**, dins el venv, a `/home/daniel/sigphi`.

---

## Pas 3 — Pujar el corpus al VPS (~145 MB comprimit)

El corpus ja està comprimit a Windows: `C:\Users\danie\corpus.tar.gz` (941 fitxers, 145 MB).
Com que l'scp està bloquejat per la xarxa, cal un intermediari web. Opcions:

**A) GitHub Release (recomanat).** Crea un release a
`https://github.com/danipufu/sigphi/releases/new`, arrossega-hi `corpus.tar.gz`
com a asset, publica'l i copia la URL de descàrrega. Després, al VPS:
```bash
cd /home/daniel/sigphi
wget -O corpus.tar.gz "URL_DEL_RELEASE"
tar -xzf corpus.tar.gz           # crea/omple corpus/
ls corpus | wc -l                # ha de dir ~941
```

**B) Google Drive.** Puja el zip a Drive, fes-lo "qualsevol amb l'enllaç", i:
```bash
pip install gdown && gdown "ID_DEL_FITXER" -O corpus.tar.gz && tar -xzf corpus.tar.gz
```

---

## Pas 4 — Ingest a Qdrant

1. Posa el backend al `.env`:
   ```bash
   echo "VECTOR_DB_TYPE=qdrant" >> .env
   ```
2. **Prova ràpida** (5 fitxers) abans de l'ingest llarg:
   ```bash
   VECTOR_DB_TYPE=qdrant python scripts/ingest.py --max-files 5
   ```
3. **Ingest complet en segon pla** (resumible; triga hores):
   ```bash
   bash deploy/run_ingest.sh
   tail -f ingest.log              # seguir el progrés
   ```
   Si es talla, torna a executar `bash deploy/run_ingest.sh`: continua on anava.

---

## Pas 5 — Aixecar l'app i provar

```bash
VECTOR_DB_TYPE=qdrant uvicorn app.main:app --host 0.0.0.0 --port 8000 &
curl -s localhost:8000/api/health
curl -s -X POST localhost:8000/api/chat -H "Content-Type: application/json" \
  -d '{"query":"Què deia Plató sobre la justícia?","history":[]}'
```

---

## Pas 6 — Servei permanent (systemd)

```bash
sudo cp deploy/systemd/sigphi.service /etc/systemd/system/sigphi.service
sudo systemctl daemon-reload
sudo systemctl enable --now sigphi
systemctl status sigphi
```

## Pas 7 — HTTPS públic (Caddy) — quan tinguis un domini
Edita `deploy/Caddyfile` amb el teu domini i:
```bash
sudo apt install -y caddy
sudo cp deploy/Caddyfile /etc/caddy/Caddyfile
sudo systemctl reload caddy
```
> Nota: des de la xarxa actual (Andorra) l'accés HTTP al VPS està bloquejat;
> prova per `curl localhost` a la VNC. L'accés públic funcionarà des d'altres xarxes.
