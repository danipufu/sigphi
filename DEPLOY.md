# Desplegament i manteniment de SigPhi

Servidor: **VPS Netcup Ubuntu 24.04** (IP 185.233.107.117, domini **sigphiai.com**).
App com a usuari **`daniel`** a `/home/daniel/sigphi`. Vector DB: **Qdrant** (Docker,
només localhost). LLM: **Gemini** (`GOOGLE_API_KEY` al `.env`). HTTPS: **Caddy**.

> ⚠️ El 27-juny-2026 el servidor antic va ser compromès (miner via SSH amb
> contrasenya feble) i es va reconstruir de zero amb l'enduriment de la Part A.
> Veure la memòria `sigphi-vps-rebuild`.

---

## Part A — Enduriment del servidor (FER PRIMER, sempre)

El forat va ser **SSH amb contrasenya de root feble**. L'enduriment el tanca:

1. **Reinstal·lar l'OS** des del panell SCP de Netcup (servercontrolpanel.de →
   Media → Images → Ubuntu 24.04 UEFI) amb contrasenya forta.
2. **Tallafoc + fail2ban** (com a root):
   ```bash
   apt update && NEEDRESTART_MODE=a apt -y upgrade && apt install -y ufw fail2ban
   ufw allow OpenSSH && ufw allow 80/tcp && ufw allow 443/tcp && ufw --force enable
   printf '[sshd]\nenabled = true\nbackend = systemd\nmaxretry = 5\nbantime = 1h\n' > /etc/fail2ban/jail.local
   systemctl enable --now fail2ban && systemctl restart fail2ban
   ```
3. **Claus SSH + desactivar contrasenyes** (genera la clau al PC: `ssh-keygen -t ed25519`,
   copia la pública a `~/.ssh/authorized_keys`, prova que entres amb clau, i llavors):
   ```bash
   printf 'PasswordAuthentication no\nKbdInteractiveAuthentication no\nPubkeyAuthentication yes\nPermitRootLogin prohibit-password\n' > /etc/ssh/sshd_config.d/00-hardening.conf
   sshd -t && systemctl restart ssh
   ```
   El prefix `00-` guanya l'ordre dels drop-ins (Ubuntu 24.04 posa
   `PasswordAuthentication yes` a `50-cloud-init.conf`).

**Auditoria** (després de qualsevol incident): `bash deploy/forensics.sh` (només
lectura: miner, persistència cron, claus-porta, logins, ports).

---

## Part B — Desplegament de SigPhi (de zero)

```bash
# Base + usuari
apt install -y git python3-venv python3-pip
adduser --disabled-password --gecos "" daniel
su - daniel -c "git clone https://github.com/danipufu/sigphi.git /home/daniel/sigphi"

cd /home/daniel/sigphi
bash deploy/add_swap.sh          # 4 GB de swap (evita OOM a la ingesta)
bash deploy/install_qdrant.sh    # Docker + Qdrant a 127.0.0.1:6333

su - daniel -c "cd ~/sigphi && python3 -m venv venv && venv/bin/pip install -r requirements.txt"
# .env (com a daniel):  GOOGLE_API_KEY=...   i   VECTOR_DB_TYPE=qdrant

bash deploy/get_corpus.sh        # baixa el paquet base (release corpus-v1, ~941 fitxers)
bash deploy/run_ingest.sh        # ingesta en segon pla (hores).  tail -f ingest.log
bash deploy/start_app.sh         # servei systemd (sigphi.service, com a daniel)
bash deploy/setup_caddy.sh       # HTTPS Let's Encrypt per sigphiai.com
bash deploy/set_ask_key.sh       # genera ASK_API_KEY (per a /api/ask i l'eval)
```

Tots els serveis queden `enabled` → sobreviuen a un reinici del VPS.

---

## Part C — Manteniment i QC del corpus

Tots són **dry-run o demanen confirmació** per defecte; treuen de Qdrant + ChunkStore
(+ `rm` del `.txt` quan cal, perquè una re-ingesta no els ressusciti).

| Script | Què fa |
|---|---|
| `deploy/dedup.sh [apply]` | Treu obres **byte-idèntiques** del mateix autor (hash del text); conserva'n 1 |
| `deploy/remove_stubs.sh` | Treu pàgines-índex de Wikisource (TOC sense text) |
| `deploy/remove_duplicates.sh` | Treu còpies dolentes de duplicats no idèntics (OCR brossa, etc.) |
| `deploy/final_polish.sh` | Tot junt: stubs + duplicats + baixar textos nous + re-ingest |
| `deploy/reingest_clean.sh` | Re-ingereix els fitxers amb boilerplate de procedència (neteja editorial) |
| `scripts/corpus_health.py` | Verificador: brossa OCR, marcatge, obres tísiques, duplicats candidats |
| `scripts/eval_golden.py` | Banc de proves de qualitat de respostes (gasta quota Gemini; 20/dia!) |

**Afegir textos nous:** edita `scripts/download_archive.py` (archive.org),
`scripts/download_sacred.py` (Gutenberg) o `scripts/download_wikisource.py`, després
al VPS `git pull` → `venv/bin/python3 scripts/download_*.py` → `ingest.py`.
**Regla de domini públic:** PD UE = 70 anys post-mortem (autor **i** traductor).

---

## Part D — Neteja del text a la ingesta (`scripts/ingest.py`)

Cada fitxer passa per (en ordre):

1. `strip_perseus_frontmatter` — crèdits editorials Perseus + blocs CVS `$Log:`.
2. `strip_gutenberg_boilerplate` — capçalera/peu `*** START/END OF PROJECT GUTENBERG ***`.
3. `strip_mediawiki_markup` (només `source: wikisource`) — plantilles, enllaços, `<ref>`,
   èmfasi, i l'**esquelet** de taules (conserva el text de les cel·les: vers/drama).
4. `clean_residual_markup` (totes les fonts) — `html.unescape` (entitats numèriques de
   marxists.org) + claudàtors `[[ ]] {{ }}` i soroll `{| |}` residual.
5. `strip_editorial_boilerplate` (totes) — `[Illustration:...]`, firmes `Produced by`,
   notes de transcriptor, peus d'escaneig de Google/Internet Archive.

El text NET es guarda i es mostra a l'LLM; el text EMBEGUT du a més un prefix amb el
nom de l'autor en 12 idiomes (cerca cross-lingual).
