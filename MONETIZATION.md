# Monetització de SigPhi

Pla de monetització i full de ruta tècnic. Model **freemium amb comptes**:
ingrés lateral recurrent ara, amb les peces de creixement preparades per si
arrenca. Tots els números són **hipòtesis inicials a validar**, no dogma.

> Decisió de fons (juny 2026): NO il·limitat. Cada consulta té un cost (per petit
> que sigui), així que cada tier porta un sostre → marge garantit per usuari, cap
> balena net-negativa, i el valor dels usuaris intensos es captura amb un tier
> superior (model **Free / Pro / Max** de Claude). El sostre es posa prou alt
> perquè l'ús típic no el senti mai.

---

## 1. La proposta de valor (el fossat)

Per què pagar per SigPhi si tens ChatGPT/Claude gratis: SigPhi està **ancorat als
textos reals, cita les fonts, no al·lucina filosofia, és multilingüe** i té un
corpus curat de domini públic. La venda és *"filosofia que pots citar, treta de
les fonts"*, no "xatejar de filosofia" (això ja és gratis a tot arreu). Tota la
monetització es construeix sobre aquest avantatge i sobre els guardrails ja
existents (sense consell de vida, avisos de contingut, cites).

---

## 2. Els tiers

| Tier | Preu | Quota | Per a qui |
|---|---|---|---|
| **Gratuït** | €0 | anònim **3/dia** · compte gratuït **5/dia** (~150/mes) | Tastar i fiar-se |
| **Plus** | **€4,5/mes** · €45/any | **~500 consultes/mes** + model premium limitat | Lectura diària |
| **Pro** | **€10/mes** | **~2.000/mes** + més model premium + publicar col·leccions | Ús intensiu, recerca, docents |
| **Educació** | a mida | accés per aula + panell docent + factura institucional | Centres (futur) |

**Funcionalitats de pagament (el mur):** historial de converses + col·leccions,
exportar cites (BibTeX, Markdown), model premium per a preguntes fondes. La
conversió depèn més del que hi ha darrere del mur que del preu exacte.

**Condició de MODEL per tier (afegit jul-2026):** el pla **Gratuït queda lligat
al model barat (Flash-Lite)** encara que el model principal de l'app pugi de
tram; **Plus/Pro reben el model bo per defecte**. Motiu doble: (a) econòmic — si
el model bo servís també els gratuïts, a l'escenari "Creixent" el cost del tram
gratuït (~€126/mes amb 3 Flash) es menjaria pràcticament tot el benefici net
projectat (~€131); (b) de venda — el golden-set (jul-2026) demostra QUÈ falla el
model barat (regles 14/20: respon coses que hauria de refusar), així que "model
millor" és un argument de conversió demostrable, no màrqueting buit. El model
concret del tram de pagament es decideix amb l'A/B del golden-set
(3.1 Flash-Lite vs 3 Flash).

**Cap escalonat com a embut:** anònim (3/dia) → compte gratuït (5/dia, ja tens
l'email) → Plus → Pro. Cada salt té un motiu. El cap també és el fre de risc: amb
5/dia, l'exposició màxima d'un gratuït que mai paga és ~€0,15/mes.

**Top-up (vessament ocasional, v2):** €0,01/consulta (10× el cost; just per sobre
de la tarifa Plus per empènyer a pujar a Pro). Es ven en **packs ≥€5 o moneder de
crèdit** — MAI €1 solt: la comissió fixa de la passarel·la (~€0,46/transacció) se
n'enduria ~46%. **Només model estàndard** (Flash-Lite); el premium quedaria car.

**Mecanisme de quota:** comptador mensual que es reinicia (més senzill que les
finestres mòbils de Claude). El tier surt del producte de subscripció; el
*metering* és el mateix codi per a tots, només canvia el número.

---

## 3. Economia

**Supòsits (tots discutibles; recalculats jul-2026):**

Des de jul-2026 cada resposta amb fonts fa **2 crides** a l'LLM (resposta +
suggeriments de seguiment); la de suggeriments és petita (~€0,0002) i sempre pot
quedar-se al model barat. Cost per consulta segons el model de la crida
PRINCIPAL (~8k tokens in + ~700 out reals, mesurats):

| Model principal | Cost/consulta (2 crides) | Notes |
|---|---|---|
| Gemini 2.5 Flash-Lite (actual) | ~€0,0012 | el supòsit original (~€0,001) aguanta |
| Gemini 3.1 Flash-Lite | ~€0,0032 | candidat a "model bo" |
| Gemini 3 Flash | ~€0,0063 | ⚠ Pro a 2.000/mes seria NET-NEGATIU (equilibri ~1.435) |
| Premium (p. ex. Claude Haiku 4.5) | ~€0,012 | coincideix amb el supòsit original de premium |

| Variable | Valor |
|---|---|
| Cost fix mensual | ~€11 (VPS Netcup ~€10 + domini ~€1) |
| Comissió de pagament (Lemon Squeezy, MoR) | ~5% + €0,46/transacció |
| Supabase / hosting auth | €0 (tier gratuït) fins a escala |
| Punt d'equilibri de la infraestructura | **~4 subscriptors** |

**Guarda de marge al Pro (afegit jul-2026):** si el model bo acaba sent 3 Flash,
el sostre Pro de 2.000/mes al pitjor cas dona marge negatiu (−€3,6). Sortides,
per ordre de preferència: (a) Pro serveix 3.1 Flash-Lite per defecte + un
SUB-TOPALL de consultes premium (p. ex. 200/mes amb el model car); (b) baixar el
sostre Pro a ~1.200; (c) pujar Pro a €12. Es decideix quan l'A/B digui quin
model cal de veritat.

**La conclusió clau:** l'economia NO és el coll d'ampolla — el **trànsit** sí. El
cost per consulta és tan baix que mai et tomba; l'única cosa que importa és
quanta gent ve. La fontaneria de cobrar es construeix en un parell de caps de
setmana; arribar a milers d'usuaris és la feina de l'any (veure §5, SEO).

**Escenaris** (conversió 2%; 80% dels que paguen a Plus, 20% a Pro; gratuïts
~10 consultes/mes de mitjana amb el cap de 5/dia):

| Escenari | Usuaris gratuïts/mes | Subs (Plus+Pro) | Benefici net/mes | A l'any |
|---|---|---|---|---|
| Llavor | 500 | 10 (8+2) | ~€25 | ~€300 |
| **Creixent** (fita) | 2.000 | 40 (32+8) | **~€131** | **~€1.575** |
| Arrelat | 5.000 | 100 (80+20) | ~€345 | ~€4.140 |
| Consolidat | 10.000 | 200 (160+40) | ~€700 | ~€8.400 |

"Ingrés lateral seriós" = arribar a **uns 5.000-10.000 usuaris/mes**. Fita
realista a 6-12 mesos: **"Creixent" (2.000/mes, ~€130/mes net)**.

**Palanques (per ordre de força):**
1. **Conversió** — d'1% a 3% triplica l'ingrés amb els mateixos usuaris. Inverteix
   en el que hi ha darrere del mur, no en retocar el preu.
2. **Trànsit** — el sostre real; veure SEO (§5).
3. **Preu / mix de tiers** — secundari; provar €5 a Plus i €12 a Pro més endavant.

---

## 4. Full de ruta tècnic

### Fase 0 — Sostenibilitat (PRECONDICIÓ, abans de res)
Ara mateix el tier gratuït de Gemini tomba a **20 req/dia**: no es pot servir
trànsit real ni provar res amb usuaris. Cal:
- **Gemini de pagament** amb **límit de despesa dur** (Google Cloud budget cap +
  alerta) — protegeix la cartera quan s'obri la porta.
- **Rate-limiting** a FastAPI (per IP de moment).

### Fase 1 — Comptes + metering
- **Auth gestionat: Supabase** (Postgres + Auth, regió UE, tier gratuït). No
  construir login a mà.
- Taula d'usuaris amb `tier` + `quota`.
- Comptador de consultes per usuari (mensual per al tier, diari per al cap
  gratuït), comprovat a FastAPI **abans** de cridar l'LLM.
- Cap escalonat: anònim 3/dia, compte gratuït 5/dia.

### Fase 2 — Pagaments + Plus/Pro
- **Lemon Squeezy** (merchant-of-record: gestiona l'IVA de tota la UE; com a
  autònom a Espanya, evita el malson MOSS). **No** Stripe directe.
- Productes de subscripció **Plus** i **Pro** (tiers discrets, no top-ups encara).
- Webhook de pagament → `user.tier = plus|pro`.
- Mur + funcionalitats Plus/Pro (historial, col·leccions, exportar cites, model
  premium) + portal de facturació.

### Fase 3 — Frontend propi + creixement
- Migrar de **Gradio** a un frontend web propi (Next.js / SvelteKit) sobre l'API
  `/api/ask` — control de l'embut, landing, pàgina de preus, ajustos de compte.
  Es pot fer per etapes (mantenir Gradio per al xat al principi).
- **Motor de creixement SEO:** pàgines públiques i indexables per filòsof/tema,
  amb resums *grounded* i citacions → trànsit de cerca → embut cap al xat →
  conversió a Plus. És la palanca de creixement més barata per al corpus (177
  filòsofs, textos PD).

### Fase 4 — Comunitat (Àgora) + top-ups
- **Pas previ (baix risc):** deixar que els **Pro publiquin col·leccions/fils
  curats** públics (lectura per a tothom). Curat → poca moderació; indexable →
  SEO; dona a Pro un avantatge de publicació.
- **Fòrum/Àgora complet** quan hi hagi massa crítica: Supabase RLS fa trivial el
  "tothom llegeix, només Pro escriu" (`policy: escriure si tier='pro'`). NO abans
  de tenir comunitat — un fòrum buit fa mal (efecte poble fantasma) i porta
  càrrega de moderació/legal que és feina solitària.
- **Top-up / moneder de crèdit** (§2) com a v2.

---

## 5. Riscos i coses a revisar
- **El trànsit és el coll d'ampolla**, no el codi. Prioritza SEO i boca-orella per
  sobre de retocar preus.
- **Cap gratuït massa estricte** mata l'activació (SigPhi és conversacional; una
  indagació es menja 5 torns). Vigilar la primera impressió; baixar/pujar el cap
  segons dades reals.
- **Moderació de l'Àgora** és una feina contínua de naturalesa diferent de
  programar. No obrir fòrum obert fins a tenir massa crítica.
- **Supòsits econòmics** (preu Flash-Lite, conversió 2%) a recalibrar amb dades
  reals un cop hi hagi usuaris.

---

## 6. Línia base tancada (juny 2026)
- **Gratuït** 5/dia (anònim 3/dia) · **Plus €4,5/mes (€45/any) ~500/mes** ·
  **Pro €10/mes ~2.000/mes + premium** · top-up €0,01/consulta (packs ≥€5, v2).
- Stack: **Supabase** (auth + DB) · **Lemon Squeezy** (pagaments/IVA) · FastAPI
  (metering) · Gemini de pagament amb tope.
- Fita 6-12 mesos: **2.000 usuaris/mes (~€130/mes net)**.
- Següent pas concret: **Fase 0** (Gemini de pagament amb límit + rate-limiting).

### Addèndum (jul-2026)
- Estructura i preus REVALIDATS amb el cost real de 2 crides/consulta: aguanten.
- Novetats que afecten el pla: **Gratuït lligat a Flash-Lite** (§2) i **guarda de
  marge al Pro** si el model bo és 3 Flash (§3).
- Els **caps del gratuït (3/5 per dia) es recalibraran amb telemetria real**
  (TelemetryStore, en producció des de jul-2026): els chips de suggeriments
  conviden a encadenar preguntes i poden menjar-se el cap en una sola exploració
  — decidir amb 2-4 setmanes de dades de torns/sessió, no a cegues.
- En activar la facturació de Gemini: **fer-ho en un projecte de Google Cloud
  SEPARAT** (el tram gratuït desapareix del projecte facturat; conservar
  l'actual gratuït per al banc de proves).
- El tope de despesa de l'app (10€/mes, Fase 0) s'haurà de pujar en proporció
  als subscriptors quan es llancin els plans (escenari Creixent amb model bo:
  €60-130/mes de despesa LLM, coberta pels ~€180 d'ingressos).
