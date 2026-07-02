"""Punt d'entrada de SigPhi.

FastAPI amb:
  - lifespan: carrega el model d'embeddings i construeix els serveis UN sol cop
    (per això cal 1 sol worker d'uvicorn: amb més es duplicaria el model en RAM).
  - API REST a /api/* (chat, health) amb rate limiting per IP.
  - UI Gradio muntada a / (Opció B: FastAPI + Gradio al mateix procés).

Execució (VPS):  uvicorn app.main:app --host 0.0.0.0 --port 8000
"""
from __future__ import annotations
import logging
import random
from contextlib import asynccontextmanager
from pathlib import Path

import gradio as gr
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.api import routes_chat, routes_health
from app.api.dependencies import limiter
from app.config import get_settings
from app.infrastructure.chunk_store import ChunkStore
from app.infrastructure.embedder import SentenceTransformersEmbedder
from app.infrastructure.llm import GeminiLLM
from app.infrastructure.reranker import CrossEncoderReranker
from app.infrastructure.vector_db import build_vector_db
from app.services.biographies import load_biographies
from app.services.chat import ChatService
from app.services.retrieval import RetrievalService
from app.services.telemetry import TelemetryStore
from app.services.usage import UsageMeter


@asynccontextmanager
async def lifespan(app: FastAPI):
    s = get_settings()
    embedder = SentenceTransformersEmbedder(s.embed_model)
    chunk_store = ChunkStore(s.chunk_store_path)
    vector_db = build_vector_db(s, chunk_store=chunk_store)
    meter = UsageMeter(
        s.usage_store_path,
        s.llm_price_input_per_million_eur,
        s.llm_price_output_per_million_eur,
    )
    llm = GeminiLLM(
        s.google_api_key,
        model=s.gemini_model,
        max_output_tokens=s.max_output_tokens,
        meter=meter,
        suggestions_model=s.suggestions_model,
    )
    reranker = None
    if s.rerank_enabled:
        try:
            reranker = CrossEncoderReranker(s.rerank_model)
        except Exception:
            logging.getLogger("sigphi").exception(
                "No s'ha pogut carregar el reranker; retrieval sense reordenar"
            )
    retrieval = RetrievalService(
        embedder, vector_db, s.aliases_path,
        top_k=s.top_k, reranker=reranker, rerank_pool=s.rerank_pool,
        lexical=chunk_store if s.hybrid_search_enabled else None,
    )
    bios = load_biographies(s.biographies_path)
    telemetry = TelemetryStore(s.telemetry_store_path)

    app.state.chunk_store = chunk_store
    app.state.vector_db = vector_db
    app.state.usage_meter = meter
    app.state.telemetry = telemetry
    app.state.chat_service = ChatService(
        llm, retrieval, biographies=bios, meter=meter,
        monthly_budget_eur=s.monthly_budget_eur, telemetry=telemetry,
    )
    yield
    chunk_store.close()
    meter.close()
    telemetry.close()


def _history_to_tuples(history) -> list[tuple[str, str]]:
    """Adapta l'historial de Gradio (format 'messages' o 'tuples') a tuples."""
    tuples: list[tuple[str, str]] = []
    if not history:
        return tuples
    if isinstance(history[0], dict):  # format "messages"
        pending = None
        for m in history:
            role, content = m.get("role"), m.get("content", "")
            if role == "user":
                pending = content
            elif role == "assistant" and pending is not None:
                tuples.append((pending, content))
                pending = None
    else:  # format "tuples" [[user, assistant], ...]
        for pair in history:
            if len(pair) == 2:
                tuples.append((pair[0], pair[1]))
    return tuples


# Lema localitzat (la part grega "Φιλοσοφία ·" es manté com a marca; canvia la
# resta segons l'idioma de la UI).
SUBTITLES = {
    "Català": "filosofia des de fonts primàries",
    "Español": "filosofía desde fuentes primarias",
    "English": "philosophy from primary sources",
    "Français": "la philosophie depuis les sources primaires",
    "Deutsch": "Philosophie aus Primärquellen",
    "Italiano": "filosofia dalle fonti primarie",
    "Русский": "философия из первоисточников",
    "中文": "源自原始文献的哲学",
    "日本語": "一次資料からの哲学",
    "العربية": "الفلسفة من المصادر الأولية",
    "हिन्दी": "मूल स्रोतों से दर्शन",
}


# Hero (logo + wordmark + lema). El logo és la marca: estrella blau marí
# (#1a2a4f) amb accents daurats (#c9a227) i "ΣΦ".
def _hero_html(lang: str = "Català") -> str:
    sub = SUBTITLES.get(lang, SUBTITLES["English"])
    return (
        '<div id="sigphi-hero">'
        '<img src="/static/logo.svg" alt="SigPhi" class="sigphi-logo">'
        '<div class="sigphi-wordmark">SigPhi</div>'
        f'<div class="sigphi-sub">Φιλοσοφία · {sub}</div>'
        "</div>"
    )

# <head> extra: metadades SEO/compartició + càrrega de font NO bloquejant
# (abans Playfair entrava per @import dins el CSS, el mètode més lent).
SIGPHI_HEAD = """
<meta name="description" content="SigPhi — philosophy from primary sources. Answers only from public-domain primary texts, with verifiable citations.">
<meta property="og:title" content="SigPhi — Φιλοσοφία · philosophy from primary sources">
<meta property="og:description" content="Ask about any thinker, tradition or idea. Answers come only from primary public-domain texts, with verifiable citations.">
<meta property="og:type" content="website">
<meta property="og:url" content="https://sigphiai.com/">
<meta property="og:image" content="https://sigphiai.com/static/logo.svg">
<meta name="theme-color" content="#1a2a4f">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Playfair+Display:wght@600;700&display=swap" rel="stylesheet">
"""

# Paleta de marca + tipografia clàssica, responsive (desktop i mòbil).
SIGPHI_CSS = """
:root { --sig-navy:#1a2a4f; --sig-navy-2:#24386b; --sig-gold:#c9a227; --sig-cream:#f7f5ef; }

/* Contenidor centrat i llegible */
.gradio-container { max-width: 920px !important; margin: 0 auto !important; }
gradio-app { background: var(--sig-cream); }

/* Hero */
#sigphi-hero { text-align:center; padding: 14px 0 4px; }
#sigphi-hero .sigphi-logo { width: 76px; height:76px; filter: drop-shadow(0 2px 5px rgba(26,42,79,.18)); }
#sigphi-hero .sigphi-wordmark {
  font-family:'Playfair Display', Georgia, serif; font-weight:700;
  font-size: 2.5rem; line-height:1.1; color: var(--sig-navy); letter-spacing:.5px; margin-top:2px;
}
#sigphi-hero .sigphi-sub { color:#6b7280; font-size:.95rem; margin-top:2px; }
#sigphi-hero::after {
  content:""; display:block; width:64px; height:3px; margin:12px auto 0;
  background: var(--sig-gold); border-radius:3px;
}

/* Selector d'idioma: dropdown compacte i centrat, en to de marca.
   (El component és un Dropdown; l'antic CSS de "píndoles" apuntava a un Radio
   que ja no existeix i no s'aplicava mai.) */
#sigphi-lang { max-width:210px; margin:6px auto 2px !important; }
#sigphi-lang input { text-align:center; color:var(--sig-navy); font-size:.9rem; }
#sigphi-lang .wrap, #sigphi-lang .container, #sigphi-lang .secondary-wrap {
  border-color:#e3ddcf !important; border-radius:999px !important; background:#fff;
}

/* Capçalera descriptiva */
#sigphi-header { text-align:center; color:#374151; max-width:640px; margin:4px auto 8px; }
#sigphi-header p { margin:.25em 0; }
#sigphi-header strong { color:var(--sig-navy); }
#sigphi-header p:last-child { font-size:.8rem; color:#a59b86; }  /* avís de fase beta, tènue */

/* Xat */
#sigphi-chat { border:1px solid #e7e2d6 !important; border-radius:16px !important; background:#fff !important;
  box-shadow:0 1px 4px rgba(26,42,79,.06); }
#sigphi-chat a { color:var(--sig-navy); text-decoration:underline; text-decoration-color:var(--sig-gold); }
/* Idiomes RTL (àrab/hebreu): que cada paràgraf segueixi la direcció del seu text */
#sigphi-chat .message, #sigphi-chat .prose p, #sigphi-chat .prose li { unicode-bidi: plaintext; }
/* Pantalles altes: aprofita l'espai vertical en lloc del tope fix de 460px */
@media (min-height: 900px) { #sigphi-chat { height: 580px !important; } }

/* Botons primaris en to marca */
button.primary, .primary { background:var(--sig-navy) !important; border-color:var(--sig-navy) !important; }

/* Feedback (👍/👎) sota l'última resposta: discret, no competeix amb els chips */
#sigphi-feedback { justify-content:center; gap:6px !important; margin-top:6px; }
#sigphi-feedback button.sigphi-fb {
  border:1px solid #e3ddcf !important; border-radius:999px !important; background:#fff !important;
  min-width:auto !important; padding:4px 12px !important; font-size:.9rem !important;
}
#sigphi-feedback button.sigphi-fb:hover { border-color:var(--sig-gold) !important; }

/* Exemples propis (botons-chip) */
#sigphi-examples { gap:8px !important; flex-wrap:wrap; margin-top:10px; }
#sigphi-examples button {
  border:1px solid #e3ddcf !important; border-radius:12px !important; background:#fff !important;
  color:var(--sig-navy) !important; font-size:.86rem !important; font-weight:400 !important;
  white-space:normal; text-align:left;
}
#sigphi-examples button:hover { border-color:var(--sig-gold) !important; box-shadow:0 2px 8px rgba(201,162,39,.18); }

/* Preguntes suggerides (chips de seguiment sota la resposta). Accent daurat a
   l'esquerra per distingir-les dels exemples i convidar a continuar explorant. */
#sigphi-suggestions { gap:8px !important; flex-wrap:wrap; margin-top:8px; }
#sigphi-suggestions button {
  border:1px solid #e3ddcf !important; border-left:3px solid var(--sig-gold) !important;
  border-radius:12px !important; background:#fbfaf6 !important;
  color:var(--sig-navy) !important; font-size:.84rem !important; font-weight:400 !important;
  white-space:normal; text-align:left;
}
#sigphi-suggestions button:hover { border-color:var(--sig-gold) !important; box-shadow:0 2px 8px rgba(201,162,39,.18); }

/* Peu */
#sigphi-footer { text-align:center; color:#9ca3af; font-size:.8rem; margin:14px 0 4px; }
#sigphi-footer b { color:var(--sig-gold); }
footer { display:none !important; }  /* amaga el "Built with Gradio" */

/* ---- Mòbil ---- */
@media (max-width: 768px) {
  .gradio-container { padding: 0 10px !important; }
  #sigphi-hero .sigphi-wordmark { font-size: 2.05rem; }
  #sigphi-hero .sigphi-logo { width: 64px; height:64px; }
  #sigphi-chat { border-radius:12px !important; }
}
@media (max-width: 480px) {
  #sigphi-hero { padding-top:8px; }
  #sigphi-hero .sigphi-wordmark { font-size: 1.8rem; }
  #sigphi-header { font-size:.92rem; }
  #sigphi-lang label { padding:5px 13px !important; font-size:.85rem; }
}
"""

SIGPHI_THEME = gr.themes.Soft(
    primary_hue=gr.themes.colors.indigo,
    secondary_hue=gr.themes.colors.amber,
    neutral_hue=gr.themes.colors.slate,
    font=[gr.themes.GoogleFont("Inter"), "system-ui", "sans-serif"],
).set(
    body_background_fill="#f7f5ef",
    button_primary_background_fill="#1a2a4f",
    button_primary_background_fill_hover="#24386b",
    button_primary_text_color="#ffffff",
    block_title_text_color="#1a2a4f",
    block_border_width="1px",
)

# Pou d'exemples, traduït als 11 idiomes de la UI (abans només en anglès, encara
# que la UI estigués en un altre idioma). A cada càrrega de pàgina (o canvi
# d'idioma) via @gr.render se'n trien N_EXAMPLES a l'atzar, així varien a cada
# refresc. Les 30 preguntes són les MATEIXES a totes les llengües (mateix índex),
# només traduïdes -- facilita mantenir-les sincronitzades si se n'afegeixen.
N_EXAMPLES = 3
EXAMPLE_POOL: dict[str, list[str]] = {
    "English": [
        "What did Plato say about justice in The Republic?",
        "What are the Five Pillars of Islam?",
        "What did Marcus Aurelius say about death?",
        "Compare Plato and Nietzsche on morality",
        "What is the meaning of life according to the Stoics?",
        "What does the Tao Te Ching teach about wu wei?",
        "What did Epictetus say about what is in our control?",
        "What is Nietzsche's idea of the will to power?",
        "What did Aristotle mean by the golden mean?",
        "How does the Bhagavad Gita describe duty (dharma)?",
        "What did Seneca think about the shortness of life?",
        "What is Kant's categorical imperative?",
        "What did Confucius teach about virtue?",
        "How do Buddhism and Christianity view death?",
        "What did Marx say about class struggle?",
        "What does 'I think, therefore I am' mean in Descartes?",
        "What did Augustine say about time in the Confessions?",
        "What does the Dhammapada say about the mind?",
        "What did Machiavelli advise rulers in The Prince?",
        "What is Spinoza's view of God in the Ethics?",
        "What did Hume say about cause and effect?",
        "What did Schopenhauer say about suffering?",
        "What is the Stoic view of fate and providence?",
        "What did Rousseau argue in The Social Contract?",
        "What did Lao Tzu say about leadership?",
        "How does the Quran describe mercy?",
        "What did Cicero say about friendship?",
        "What is Hegel's master–slave dialectic?",
        "What did Mill argue in On Liberty?",
        "What did Heraclitus mean that everything flows?",
    ],
    "Català": [
        "Què deia Plató sobre la justícia a La República?",
        "Quins són els Cinc Pilars de l'Islam?",
        "Què deia Marc Aureli sobre la mort?",
        "Compara Plató i Nietzsche sobre la moral",
        "Quin és el sentit de la vida segons els estoics?",
        "Què ensenya el Tao Te Ching sobre el wu wei?",
        "Què deia Epictet sobre allò que està al nostre abast?",
        "Quina és la idea de Nietzsche de la voluntat de poder?",
        "Què volia dir Aristòtil amb el terme mitjà?",
        "Com descriu el Bhagavad-Gita el deure (dharma)?",
        "Què pensava Sèneca sobre la brevetat de la vida?",
        "Què és l'imperatiu categòric de Kant?",
        "Què ensenyava Confuci sobre la virtut?",
        "Com veuen la mort el budisme i el cristianisme?",
        "Què deia Marx sobre la lluita de classes?",
        "Què vol dir \"penso, doncs existeixo\" en Descartes?",
        "Què deia Agustí sobre el temps a les Confessions?",
        "Què diu el Dhammapada sobre la ment?",
        "Quins consells donava Maquiavel als governants a El Príncep?",
        "Quina és la visió de Déu de Spinoza a l'Ètica?",
        "Què deia Hume sobre la causa i l'efecte?",
        "Què deia Schopenhauer sobre el sofriment?",
        "Quina és la visió estoica del destí i la providència?",
        "Què defensava Rousseau al Contracte Social?",
        "Què deia Lao-Tsé sobre el lideratge?",
        "Com descriu l'Alcorà la misericòrdia?",
        "Què deia Ciceró sobre l'amistat?",
        "Què és la dialèctica de l'amo i l'esclau de Hegel?",
        "Què defensava Mill a Sobre la llibertat?",
        "Què volia dir Heràclit amb que tot flueix?",
    ],
    "Español": [
        "¿Qué decía Platón sobre la justicia en La República?",
        "¿Cuáles son los Cinco Pilares del Islam?",
        "¿Qué decía Marco Aurelio sobre la muerte?",
        "Compara a Platón y Nietzsche sobre la moral",
        "¿Cuál es el sentido de la vida según los estoicos?",
        "¿Qué enseña el Tao Te Ching sobre el wu wei?",
        "¿Qué decía Epicteto sobre lo que está en nuestro poder?",
        "¿Cuál es la idea de Nietzsche de la voluntad de poder?",
        "¿Qué quería decir Aristóteles con el término medio?",
        "¿Cómo describe el Bhagavad-Gita el deber (dharma)?",
        "¿Qué pensaba Séneca sobre la brevedad de la vida?",
        "¿Qué es el imperativo categórico de Kant?",
        "¿Qué enseñaba Confucio sobre la virtud?",
        "¿Cómo ven la muerte el budismo y el cristianismo?",
        "¿Qué decía Marx sobre la lucha de clases?",
        "¿Qué significa \"pienso, luego existo\" en Descartes?",
        "¿Qué decía Agustín sobre el tiempo en las Confesiones?",
        "¿Qué dice el Dhammapada sobre la mente?",
        "¿Qué consejos daba Maquiavelo a los gobernantes en El Príncipe?",
        "¿Cuál es la visión de Dios de Spinoza en la Ética?",
        "¿Qué decía Hume sobre la causa y el efecto?",
        "¿Qué decía Schopenhauer sobre el sufrimiento?",
        "¿Cuál es la visión estoica del destino y la providencia?",
        "¿Qué defendía Rousseau en El contrato social?",
        "¿Qué decía Lao Tse sobre el liderazgo?",
        "¿Cómo describe el Corán la misericordia?",
        "¿Qué decía Cicerón sobre la amistad?",
        "¿Qué es la dialéctica del amo y el esclavo de Hegel?",
        "¿Qué defendía Mill en Sobre la libertad?",
        "¿Qué quería decir Heráclito con que todo fluye?",
    ],
    "Français": [
        "Que disait Platon sur la justice dans La République ?",
        "Quels sont les cinq piliers de l'islam ?",
        "Que disait Marc Aurèle sur la mort ?",
        "Comparez Platon et Nietzsche sur la morale",
        "Quel est le sens de la vie selon les stoïciens ?",
        "Que dit le Tao-tö-king sur le wu wei ?",
        "Que disait Épictète sur ce qui dépend de nous ?",
        "Quelle est l'idée de la volonté de puissance chez Nietzsche ?",
        "Que voulait dire Aristote par le juste milieu ?",
        "Comment la Bhagavad-Gîtâ décrit-elle le devoir (dharma) ?",
        "Que pensait Sénèque de la brièveté de la vie ?",
        "Qu'est-ce que l'impératif catégorique de Kant ?",
        "Qu'enseignait Confucius sur la vertu ?",
        "Comment le bouddhisme et le christianisme voient-ils la mort ?",
        "Que disait Marx sur la lutte des classes ?",
        "Que signifie « je pense, donc je suis » chez Descartes ?",
        "Que disait Augustin sur le temps dans les Confessions ?",
        "Que dit le Dhammapada sur l'esprit ?",
        "Quels conseils Machiavel donnait-il aux princes dans Le Prince ?",
        "Quelle est la vision de Dieu de Spinoza dans l'Éthique ?",
        "Que disait Hume sur la cause et l'effet ?",
        "Que disait Schopenhauer sur la souffrance ?",
        "Quelle est la vision stoïcienne du destin et de la providence ?",
        "Que défendait Rousseau dans Du contrat social ?",
        "Que disait Lao Tseu sur le leadership ?",
        "Comment le Coran décrit-il la miséricorde ?",
        "Que disait Cicéron sur l'amitié ?",
        "Qu'est-ce que la dialectique du maître et de l'esclave chez Hegel ?",
        "Que défendait Mill dans De la liberté ?",
        "Que voulait dire Héraclite par « tout coule » ?",
    ],
    "Deutsch": [
        "Was sagte Platon über Gerechtigkeit im Staat?",
        "Was sind die fünf Säulen des Islam?",
        "Was sagte Mark Aurel über den Tod?",
        "Vergleiche Platon und Nietzsche zur Moral",
        "Was ist laut den Stoikern der Sinn des Lebens?",
        "Was lehrt das Tao Te King über Wu Wei?",
        "Was sagte Epiktet darüber, was in unserer Macht steht?",
        "Was ist Nietzsches Idee vom Willen zur Macht?",
        "Was meinte Aristoteles mit der goldenen Mitte?",
        "Wie beschreibt die Bhagavad Gita die Pflicht (Dharma)?",
        "Was dachte Seneca über die Kürze des Lebens?",
        "Was ist Kants kategorischer Imperativ?",
        "Was lehrte Konfuzius über Tugend?",
        "Wie sehen Buddhismus und Christentum den Tod?",
        "Was sagte Marx über den Klassenkampf?",
        "Was bedeutet \"Ich denke, also bin ich\" bei Descartes?",
        "Was sagte Augustinus über die Zeit in den Bekenntnissen?",
        "Was sagt das Dhammapada über den Geist?",
        "Welche Ratschläge gab Machiavelli den Herrschern im Fürst?",
        "Wie sieht Spinoza Gott in der Ethik?",
        "Was sagte Hume über Ursache und Wirkung?",
        "Was sagte Schopenhauer über das Leiden?",
        "Wie sehen die Stoiker Schicksal und Vorsehung?",
        "Was vertrat Rousseau im Gesellschaftsvertrag?",
        "Was sagte Laotse über Führung?",
        "Wie beschreibt der Koran die Barmherzigkeit?",
        "Was sagte Cicero über Freundschaft?",
        "Was ist Hegels Herr-Knecht-Dialektik?",
        "Was vertrat Mill in Über die Freiheit?",
        "Was meinte Heraklit damit, dass alles fließt?",
    ],
    "Italiano": [
        "Cosa diceva Platone sulla giustizia nella Repubblica?",
        "Quali sono i Cinque Pilastri dell'Islam?",
        "Cosa diceva Marco Aurelio sulla morte?",
        "Confronta Platone e Nietzsche sulla morale",
        "Qual è il senso della vita secondo gli stoici?",
        "Cosa insegna il Tao Te Ching sul wu wei?",
        "Cosa diceva Epitteto su ciò che è in nostro potere?",
        "Qual è l'idea di Nietzsche della volontà di potenza?",
        "Cosa intendeva Aristotele con la giusta misura?",
        "Come descrive la Bhagavad Gita il dovere (dharma)?",
        "Cosa pensava Seneca della brevità della vita?",
        "Cos'è l'imperativo categorico di Kant?",
        "Cosa insegnava Confucio sulla virtù?",
        "Come vedono la morte il buddismo e il cristianesimo?",
        "Cosa diceva Marx sulla lotta di classe?",
        "Cosa significa \"penso, dunque sono\" in Cartesio?",
        "Cosa diceva Agostino sul tempo nelle Confessioni?",
        "Cosa dice il Dhammapada sulla mente?",
        "Quali consigli dava Machiavelli ai governanti ne Il Principe?",
        "Qual è la visione di Dio di Spinoza nell'Etica?",
        "Cosa diceva Hume su causa ed effetto?",
        "Cosa diceva Schopenhauer sulla sofferenza?",
        "Qual è la visione stoica del destino e della provvidenza?",
        "Cosa sosteneva Rousseau nel Contratto sociale?",
        "Cosa diceva Lao Tzu sulla leadership?",
        "Come descrive il Corano la misericordia?",
        "Cosa diceva Cicerone sull'amicizia?",
        "Cos'è la dialettica servo-padrone di Hegel?",
        "Cosa sosteneva Mill ne La libertà?",
        "Cosa intendeva Eraclito dicendo che tutto scorre?",
    ],
    "Русский": [
        "Что говорил Платон о справедливости в «Государстве»?",
        "Каковы пять столпов ислама?",
        "Что говорил Марк Аврелий о смерти?",
        "Сравните взгляды Платона и Ницше на мораль",
        "В чём смысл жизни, по мнению стоиков?",
        "Чему учит «Дао дэ цзин» о недеянии (у-вэй)?",
        "Что говорил Эпиктет о том, что в нашей власти?",
        "В чём идея воли к власти у Ницше?",
        "Что имел в виду Аристотель под золотой серединой?",
        "Как Бхагавад-гита описывает долг (дхарму)?",
        "Что думал Сенека о краткости жизни?",
        "Что такое категорический императив Канта?",
        "Чему учил Конфуций о добродетели?",
        "Как буддизм и христианство рассматривают смерть?",
        "Что говорил Маркс о классовой борьбе?",
        "Что значит «я мыслю, следовательно, существую» у Декарта?",
        "Что говорил Августин о времени в «Исповеди»?",
        "Что говорит Дхаммапада об уме?",
        "Какие советы давал Макиавелли правителям в «Государе»?",
        "Каково представление Спинозы о Боге в «Этике»?",
        "Что говорил Юм о причине и следствии?",
        "Что говорил Шопенгауэр о страдании?",
        "Каков стоический взгляд на судьбу и провидение?",
        "Что отстаивал Руссо в «Общественном договоре»?",
        "Что говорил Лао-цзы о лидерстве?",
        "Как Коран описывает милосердие?",
        "Что говорил Цицерон о дружбе?",
        "Что такое диалектика господина и раба у Гегеля?",
        "Что отстаивал Милль в «О свободе»?",
        "Что имел в виду Гераклит, говоря, что всё течёт?",
    ],
    "中文": [
        "柏拉图在《理想国》中如何论述正义？",
        "伊斯兰教的五功是什么？",
        "马可·奥勒留如何看待死亡？",
        "比较柏拉图和尼采关于道德的观点",
        "斯多葛学派如何看待人生的意义？",
        "《道德经》对无为是怎么讲的？",
        "爱比克泰德如何论述我们能掌控的事？",
        "尼采的权力意志是什么概念？",
        "亚里士多德所说的中道是什么意思？",
        "《薄伽梵歌》如何描述达摩（责任）？",
        "塞涅卡如何看待人生短暂？",
        "康德的绝对命令是什么？",
        "孔子如何教导美德？",
        "佛教和基督教如何看待死亡？",
        "马克思如何论述阶级斗争？",
        "笛卡尔的“我思故我在”是什么意思？",
        "奥古斯丁在《忏悔录》中如何论述时间？",
        "《法句经》如何论述心？",
        "马基雅维利在《君主论》中给统治者什么建议？",
        "斯宾诺莎在《伦理学》中如何看待上帝？",
        "休谟如何论述因果关系？",
        "叔本华如何看待苦难？",
        "斯多葛学派如何看待命运与天意？",
        "卢梭在《社会契约论》中主张什么？",
        "老子如何论述领导之道？",
        "《古兰经》如何描述慈悲？",
        "西塞罗如何论述友谊？",
        "黑格尔的主奴辩证法是什么？",
        "密尔在《论自由》中主张什么？",
        "赫拉克利特所说的“万物皆流”是什么意思？",
    ],
    "日本語": [
        "プラトンは『国家』で正義について何と述べたか？",
        "イスラム教の五行とは何か？",
        "マルクス・アウレリウスは死についてどう述べたか？",
        "道徳についてプラトンとニーチェを比較して",
        "ストア派によれば人生の意味とは何か？",
        "『老子道徳経』は無為について何を教えているか？",
        "エピクテトスは私たちの力の及ぶことについて何と述べたか？",
        "ニーチェの権力への意志とはどのような考えか？",
        "アリストテレスの中庸とはどのような意味か？",
        "『バガヴァッド・ギーター』は義務（ダルマ）をどう説明しているか？",
        "セネカは人生の短さについてどう考えたか？",
        "カントの定言命法とは何か？",
        "孔子は徳について何を教えたか？",
        "仏教とキリスト教は死をどう捉えているか？",
        "マルクスは階級闘争について何と述べたか？",
        "デカルトの「我思う、ゆえに我あり」とはどういう意味か？",
        "アウグスティヌスは『告白』で時間について何と述べたか？",
        "『法句経（ダンマパダ）』は心について何を説いているか？",
        "マキャヴェッリは『君主論』で統治者にどんな助言をしたか？",
        "スピノザは『エチカ』で神をどう捉えているか？",
        "ヒュームは因果関係について何と述べたか？",
        "ショーペンハウアーは苦しみについて何と述べたか？",
        "ストア派は運命と摂理をどう捉えているか？",
        "ルソーは『社会契約論』で何を主張したか？",
        "老子はリーダーシップについて何と述べたか？",
        "コーランは慈悲についてどう述べているか？",
        "キケロは友情について何と述べたか？",
        "ヘーゲルの主人と奴隷の弁証法とは何か？",
        "ミルは『自由論』で何を主張したか？",
        "ヘラクレイトスの「万物は流転する」とはどういう意味か？",
    ],
    "العربية": [
        "ماذا قال أفلاطون عن العدالة في كتاب الجمهورية؟",
        "ما هي أركان الإسلام الخمسة؟",
        "ماذا قال ماركوس أوريليوس عن الموت؟",
        "قارن بين أفلاطون ونيتشه في الأخلاق",
        "ما معنى الحياة بحسب الرواقيين؟",
        "ماذا يعلّم كتاب تاو ته تشينغ عن اللافعل (وو وي)؟",
        "ماذا قال إبكتيتوس عمّا هو في مقدرتنا؟",
        "ما هي فكرة نيتشه عن إرادة القوة؟",
        "ماذا قصد أرسطو بالوسط الذهبي؟",
        "كيف تصف البهاغافادغيتا الواجب (الدارما)؟",
        "ماذا كان يعتقد سينيكا عن قصر الحياة؟",
        "ما هو الأمر القطعي عند كانط؟",
        "ماذا علّم كونفوشيوس عن الفضيلة؟",
        "كيف ينظر البوذيون والمسيحيون إلى الموت؟",
        "ماذا قال ماركس عن الصراع الطبقي؟",
        "ماذا تعني عبارة \"أنا أفكر إذن أنا موجود\" عند ديكارت؟",
        "ماذا قال أوغسطينوس عن الزمن في كتاب الاعترافات؟",
        "ماذا يقول كتاب الدهمابادا عن العقل؟",
        "ما النصائح التي قدّمها ميكيافيلي للحكام في كتاب الأمير؟",
        "ما هي نظرة سبينوزا إلى الله في كتاب الأخلاق؟",
        "ماذا قال هيوم عن السبب والنتيجة؟",
        "ماذا قال شوبنهاور عن المعاناة؟",
        "ما هي النظرة الرواقية إلى القدر والعناية الإلهية؟",
        "بماذا نادى روسو في كتاب العقد الاجتماعي؟",
        "ماذا قال لاوتزو عن القيادة؟",
        "كيف يصف القرآن الرحمة؟",
        "ماذا قال شيشرون عن الصداقة؟",
        "ما هي جدلية السيد والعبد عند هيغل؟",
        "بماذا نادى ميل في كتاب عن الحرية؟",
        "ماذا قصد هيراقليطس بقوله إن كل شيء يتدفق؟",
    ],
    "हिन्दी": [
        "प्लेटो ने 'रिपब्लिक' में न्याय के बारे में क्या कहा?",
        "इस्लाम के पाँच स्तंभ कौन से हैं?",
        "मार्कस ऑरेलियस ने मृत्यु के बारे में क्या कहा?",
        "नैतिकता पर प्लेटो और नीत्शे की तुलना करें",
        "स्टोइक दार्शनिकों के अनुसार जीवन का अर्थ क्या है?",
        "ताओ ते चिंग वू वेई के बारे में क्या सिखाता है?",
        "एपिक्टेटस ने हमारे नियंत्रण में क्या है, इस बारे में क्या कहा?",
        "नीत्शे का शक्ति की इच्छा (विल टू पावर) का विचार क्या है?",
        "अरस्तू का स्वर्णिम मध्य (गोल्डन मीन) से क्या तात्पर्य था?",
        "भगवद्गीता कर्तव्य (धर्म) का वर्णन कैसे करती है?",
        "सेनेका जीवन की क्षणभंगुरता के बारे में क्या सोचते थे?",
        "कांट का कैटेगोरिकल इम्पेरेटिव क्या है?",
        "कन्फ्यूशियस ने सद्गुण के बारे में क्या सिखाया?",
        "बौद्ध धर्म और ईसाई धर्म मृत्यु को कैसे देखते हैं?",
        "मार्क्स ने वर्ग संघर्ष के बारे में क्या कहा?",
        "देकार्त के अनुसार \"मैं सोचता हूँ, इसलिए मैं हूँ\" का क्या अर्थ है?",
        "ऑगस्टीन ने 'कन्फेशन्स' में समय के बारे में क्या कहा?",
        "धम्मपद मन के बारे में क्या कहता है?",
        "मैकियावेली ने 'द प्रिंस' में शासकों को क्या सलाह दी?",
        "स्पिनोज़ा की 'एथिक्स' में ईश्वर के बारे में क्या दृष्टिकोण है?",
        "ह्यूम ने कारण और प्रभाव के बारे में क्या कहा?",
        "शोपेनहावर ने दुख के बारे में क्या कहा?",
        "भाग्य और विधान के बारे में स्टोइक दृष्टिकोण क्या है?",
        "रूसो ने 'द सोशल कॉन्ट्रैक्ट' में क्या तर्क दिया?",
        "लाओ त्ज़ु ने नेतृत्व के बारे में क्या कहा?",
        "क़ुरान दया का वर्णन कैसे करता है?",
        "सिसरो ने मित्रता के बारे में क्या कहा?",
        "हेगेल की स्वामी-दास द्वंद्वात्मकता क्या है?",
        "मिल ने 'ऑन लिबर्टी' में क्या तर्क दिया?",
        "हेराक्लिटस का \"सब कुछ प्रवाहित होता है\" से क्या तात्पर्य था?",
    ],
}

# Descripció localitzada (sense títol: el hero ja mostra "SigPhi"). Primera línia
# = què fa; segona línia = avís de fase beta (es mostra més tènue via CSS).
# El CONTINGUT de les respostes ja segueix l'idioma de la pregunta (regla 7).
HEADERS = {
    "Català": (
        "Respon NOMÉS amb textos filosòfics i religiosos primaris de domini públic, "
        "amb cites verificables.\n\n"
        "En fase beta: les respostes encara poden no ser òptimes."
    ),
    "Español": (
        "Responde SOLO con textos filosóficos y religiosos primarios de dominio "
        "público, con citas verificables.\n\n"
        "En fase beta: las respuestas aún pueden no ser óptimas."
    ),
    "English": (
        "Answers ONLY from primary public-domain philosophical and religious texts, "
        "with verifiable citations.\n\n"
        "Beta: answers may not yet be optimal."
    ),
    "Français": (
        "Répond UNIQUEMENT à partir de textes philosophiques et religieux primaires "
        "du domaine public, avec des citations vérifiables.\n\n"
        "Version bêta : les réponses peuvent ne pas encore être optimales."
    ),
    "Deutsch": (
        "Antwortet AUSSCHLIESSLICH auf Grundlage gemeinfreier philosophischer und "
        "religiöser Primärtexte, mit überprüfbaren Zitaten.\n\n"
        "Beta: Die Antworten sind möglicherweise noch nicht optimal."
    ),
    "Italiano": (
        "Risponde SOLO con testi filosofici e religiosi primari di pubblico dominio, "
        "con citazioni verificabili.\n\n"
        "Versione beta: le risposte potrebbero non essere ancora ottimali."
    ),
    "Русский": (
        "Отвечает ТОЛЬКО по первичным философским и религиозным текстам общественного "
        "достояния, с проверяемыми цитатами.\n\n"
        "Бета-версия: ответы пока могут быть неоптимальными."
    ),
    "中文": (
        "仅依据公共领域的哲学与宗教原始文献作答，并附可查证的引用。\n\n"
        "测试版：回答可能尚未达到最佳。"
    ),
    "日本語": (
        "パブリックドメインの哲学・宗教の一次資料のみに基づき、検証可能な出典付きで"
        "回答します。\n\n"
        "ベータ版：回答はまだ最適でない場合があります。"
    ),
    "العربية": (
        "يجيب فقط اعتمادًا على نصوص فلسفية ودينية أولية في الملك العام، مع استشهادات "
        "قابلة للتحقق.\n\n"
        "نسخة تجريبية: قد لا تكون الإجابات مثالية بعد."
    ),
    "हिन्दी": (
        "केवल सार्वजनिक डोमेन के मूल दार्शनिक और धार्मिक ग्रंथों के आधार पर उत्तर देता है, "
        "सत्यापन-योग्य उद्धरणों के साथ।\n\n"
        "बीटा: उत्तर अभी सर्वोत्तम नहीं हो सकते।"
    ),
}


# Placeholder del quadre de pregunta, benvinguda del xat buit i cadenes del
# catàleg, localitzats (abans quedaven fixos en anglès encara que la UI canviés
# d'idioma). El resum del catàleg és plantilla amb {a}=autors {w}=obres {p}=passatges.
PLACEHOLDERS = {
    "Català": "Pregunta sobre filosofia… (en qualsevol idioma)",
    "Español": "Pregunta sobre filosofía… (en cualquier idioma)",
    "English": "Ask a question about philosophy… (in any language)",
    "Français": "Posez une question de philosophie… (dans n'importe quelle langue)",
    "Deutsch": "Stellen Sie eine Frage zur Philosophie… (in jeder Sprache)",
    "Italiano": "Fai una domanda di filosofia… (in qualsiasi lingua)",
    "Русский": "Задайте вопрос о философии… (на любом языке)",
    "中文": "提出一个哲学问题……（任何语言均可）",
    "日本語": "哲学について質問してください…（どの言語でも）",
    "العربية": "اطرح سؤالاً في الفلسفة… (بأي لغة)",
    "हिन्दी": "दर्शन के बारे में प्रश्न पूछें… (किसी भी भाषा में)",
}
WELCOMES = {
    "Català": "**Φιλοσοφία**\n\nPregunta sobre qualsevol pensador, tradició o idea.\nLes respostes surten només de fonts primàries, amb cites.",
    "Español": "**Φιλοσοφία**\n\nPregunta sobre cualquier pensador, tradición o idea.\nLas respuestas salen solo de fuentes primarias, con citas.",
    "English": "**Φιλοσοφία**\n\nAsk about any thinker, tradition or idea.\nAnswers come only from primary sources, with citations.",
    "Français": "**Φιλοσοφία**\n\nInterrogez n'importe quel penseur, tradition ou idée.\nLes réponses proviennent uniquement de sources primaires, avec citations.",
    "Deutsch": "**Φιλοσοφία**\n\nFragen Sie nach Denkern, Traditionen oder Ideen.\nAntworten stammen nur aus Primärquellen, mit Zitaten.",
    "Italiano": "**Φιλοσοφία**\n\nChiedi di qualsiasi pensatore, tradizione o idea.\nLe risposte provengono solo da fonti primarie, con citazioni.",
    "Русский": "**Φιλοσοφία**\n\nСпросите о любом мыслителе, традиции или идее.\nОтветы — только из первоисточников, с цитатами.",
    "中文": "**Φιλοσοφία**\n\n询问任何思想家、传统或观念。\n回答仅来自原始文献，并附引用。",
    "日本語": "**Φιλοσοφία**\n\n思想家・伝統・概念について質問してください。\n回答は一次資料のみに基づき、出典付きです。",
    "العربية": "**Φιλοσοφία**\n\nاسأل عن أي مفكر أو تقليد أو فكرة.\nالإجابات من المصادر الأولية فقط، مع الاستشهادات.",
    "हिन्दी": "**Φιλοσοφία**\n\nकिसी भी विचारक, परंपरा या विचार के बारे में पूछें।\nउत्तर केवल मूल स्रोतों से, उद्धरणों के साथ।",
}
CATALOG_TITLES = {
    "Català": "📚 Autors i textos del corpus",
    "Español": "📚 Autores y textos del corpus",
    "English": "📚 Authors & texts in the corpus",
    "Français": "📚 Auteurs et textes du corpus",
    "Deutsch": "📚 Autoren & Texte im Korpus",
    "Italiano": "📚 Autori e testi del corpus",
    "Русский": "📚 Авторы и тексты корпуса",
    "中文": "📚 语料库中的作者与文本",
    "日本語": "📚 コーパスの著者とテキスト",
    "العربية": "📚 المؤلفون والنصوص في المكتبة",
    "हिन्दी": "📚 संग्रह के लेखक और ग्रंथ",
}
BROWSE_LABELS = {
    "Català": "Explora per autor",
    "Español": "Explora por autor",
    "English": "Browse by author",
    "Français": "Parcourir par auteur",
    "Deutsch": "Nach Autor stöbern",
    "Italiano": "Sfoglia per autore",
    "Русский": "Поиск по автору",
    "中文": "按作者浏览",
    "日本語": "著者から探す",
    "العربية": "تصفح حسب المؤلف",
    "हिन्दी": "लेखक के अनुसार देखें",
}
SUMMARY_TMPL = {
    "Català": "**{a} autors · {w} obres · {p:,} passatges** — tria un autor per veure les seves obres.",
    "Español": "**{a} autores · {w} obras · {p:,} pasajes** — elige un autor para ver sus obras.",
    "English": "**{a} authors · {w} works · {p:,} passages** — pick an author to see their works.",
    "Français": "**{a} auteurs · {w} œuvres · {p:,} passages** — choisissez un auteur pour voir ses œuvres.",
    "Deutsch": "**{a} Autoren · {w} Werke · {p:,} Passagen** — wählen Sie einen Autor, um seine Werke zu sehen.",
    "Italiano": "**{a} autori · {w} opere · {p:,} passi** — scegli un autore per vedere le sue opere.",
    "Русский": "**{a} авторов · {w} произведений · {p:,} фрагментов** — выберите автора, чтобы увидеть его труды.",
    "中文": "**{a} 位作者 · {w} 部作品 · {p:,} 个段落** — 选择作者查看其作品。",
    "日本語": "**{a} 名の著者 · {w} 作品 · {p:,} 節** — 著者を選ぶと作品が表示されます。",
    "العربية": "**{a} مؤلفًا · {w} عملاً · {p:,} مقطعًا** — اختر مؤلفًا لعرض أعماله.",
    "हिन्दी": "**{a} लेखक · {w} कृतियाँ · {p:,} अंश** — कृतियाँ देखने के लिए लेखक चुनें।",
}
WORKS_WORD = {
    "Català": "obres", "Español": "obras", "English": "works", "Français": "œuvres",
    "Deutsch": "Werke", "Italiano": "opere", "Русский": "произведений", "中文": "部作品",
    "日本語": "作品", "العربية": "أعمال", "हिन्दी": "कृतियाँ",
}


def _format_answer_md(res) -> str:
    """Resposta + llista de fonts en Markdown. Les preguntes suggerides NO van aquí:
    es retornen a part (res.suggestions) i la UI principal les mostra com a chips."""
    if res.sources:
        srcs = "\n".join(f"- {s}" for s in res.sources)
        return f"{res.answer}\n\n---\n**Fonts:**\n{srcs}"
    return res.answer


def _make_respond(app: FastAPI):
    """Responder string-only per a la UI de reserva (sense chips de suggeriments)."""
    def respond(message, history):
        res = app.state.chat_service.answer(message, _history_to_tuples(history))
        return _format_answer_md(res)

    return respond


# Peu localitzat.
FOOTERS = {
    "Català": "Només fonts primàries de domini públic · cites verificables · sense consells ni opinions",
    "Español": "Solo fuentes primarias de dominio público · citas verificables · sin consejos ni opiniones",
    "English": "Only primary public-domain sources · verifiable citations · no advice or opinions",
    "Français": "Uniquement des sources primaires du domaine public · citations vérifiables · sans conseils ni opinions",
    "Deutsch": "Nur gemeinfreie Primärquellen · überprüfbare Zitate · keine Ratschläge oder Meinungen",
    "Italiano": "Solo fonti primarie di pubblico dominio · citazioni verificabili · senza consigli né opinioni",
    "Русский": "Только первичные источники общественного достояния · проверяемые цитаты · без советов и мнений",
    "中文": "仅限公共领域的原始文献 · 可查证的引用 · 不提供建议或观点",
    "日本語": "パブリックドメインの一次資料のみ · 検証可能な出典 · 助言や意見なし",
    "العربية": "مصادر أولية في الملك العام فقط · استشهادات قابلة للتحقق · بلا نصائح أو آراء",
    "हिन्दी": "केवल सार्वजनिक डोमेन के मूल स्रोत · सत्यापन-योग्य उद्धरण · कोई सलाह या राय नहीं",
}


def _footer_html(lang: str = "Català") -> str:
    return f'<div id="sigphi-footer">{FOOTERS.get(lang, FOOTERS["English"])}</div>'


# Gradio 6 va moure theme/css del constructor de Blocks a mount_gradio_app().
# Detectem-ho per aplicar l'estil on toqui (robust a 4.x/5.x i 6.x).
import inspect as _inspect

_MOUNT_SUPPORTS_CSS = "css" in _inspect.signature(gr.mount_gradio_app).parameters
_MOUNT_SUPPORTS_HEAD = "head" in _inspect.signature(gr.mount_gradio_app).parameters


def _stream_answer(app: FastAPI, message: str, hist: list[tuple[str, str]]):
    """Generador compartit: yield-a (markdown_parcial, suggeriments, pregunta) a
    mesura que arriba la resposta (suggeriments buits fins que s'acaba), i acaba
    amb (markdown AMB fonts, suggeriments reals, pregunta). ChatService.answer_stream
    fa la feina real; aquí només l'adaptem al contracte (text, additional_outputs)
    que espera Gradio a cada yield. La pregunta viatja a last_query_state perquè
    els botons de feedback (👍/👎) sàpiguen a quina consulta es refereixen."""
    gen = app.state.chat_service.answer_stream(message, hist)
    res = None
    while True:
        try:
            partial = next(gen)
        except StopIteration as e:
            res = e.value
            break
        yield partial, [], message
    if res is not None:
        yield _format_answer_md(res), res.suggestions, message


def _send_feedback(app: FastAPI, query: str, vote: int) -> None:
    """Registra un polze amunt/avall sobre l'última resposta. Mai trenca la UI
    si el registre falla (avís de log, toast de confirmació igualment)."""
    if query:
        try:
            app.state.telemetry.record_feedback(query, vote)
        except Exception:
            logging.getLogger("sigphi").warning("No s'ha pogut registrar el feedback", exc_info=True)
    gr.Info("🙏")


def _build_gradio(app: FastAPI) -> gr.Blocks:
    def respond_full(message, history):
        """UI principal: yield-a (markdown, llista_suggeriments) progressivament
        (streaming). El segon valor va a additional_outputs -> suggestions_state
        -> chips de seguiment (només presents a l'últim yield)."""
        yield from _stream_answer(app, message, _history_to_tuples(history))

    # A Gradio <6, theme/css van al Blocks; a >=6 van a mount_gradio_app (a sota).
    blocks_kwargs = {} if _MOUNT_SUPPORTS_CSS else {"theme": SIGPHI_THEME, "css": SIGPHI_CSS}
    with gr.Blocks(title="SigPhi", **blocks_kwargs) as demo:
        hero = gr.HTML(_hero_html("English"))
        lang = gr.Dropdown(
            [
                "Català", "Español", "English", "Français", "Deutsch", "Italiano",
                "Русский", "中文", "日本語", "العربية", "हिन्दी",
            ],
            value="English",
            show_label=False,
            container=False,
            filterable=False,
            elem_id="sigphi-lang",
        )
        header = gr.Markdown(HEADERS["English"], elem_id="sigphi-header")
        # Estat amb les preguntes suggerides de l'ÚLTIMA resposta. S'omple via
        # additional_outputs del ChatInterface (i del runner de chips). Quan canvia,
        # @gr.render recrea els chips de seguiment.
        suggestions_state = gr.State([])
        # Última pregunta feta (per als botons de feedback 👍/👎: encara no hi ha
        # ID de torn, així que el feedback s'associa a la pregunta literal).
        last_query_state = gr.State("")
        ci = gr.ChatInterface(
            fn=respond_full,
            chatbot=gr.Chatbot(
                elem_id="sigphi-chat",
                height=460,
                show_label=False,
                placeholder=WELCOMES["English"],  # benvinguda al xat buit (abans, caixa blanca)
            ),
            textbox=gr.Textbox(
                placeholder=PLACEHOLDERS["English"],
                elem_id="sigphi-input",
                container=False,
                scale=7,
                autofocus=True,
            ),
            additional_outputs=[suggestions_state, last_query_state],
        )

        # Runner compartit per als chips (exemples i suggeriments): omple el xat amb
        # la pregunta i la respon EN STREAMING (buida els suggeriments mentre
        # carrega -> reapareixen amb els nous). Surt a (chatbot, suggestions_state,
        # last_query_state).
        def _run_question(question, history):
            history = history or []
            base = history + [{"role": "user", "content": question}]
            yield base + [{"role": "assistant", "content": "…"}], [], question
            hist_tuples = _history_to_tuples(history)
            for md, suggestions, q in _stream_answer(app, question, hist_tuples):
                yield base + [{"role": "assistant", "content": md}], suggestions, q

        # Chips sota el xat. UN sol render decideix QUÈ mostrar segons l'estat:
        #   - conversa NO començada -> N_EXAMPLES exemples a l'atzar (varien a cada
        #     càrrega de pàgina);
        #   - hi ha preguntes suggerides (crida separada de ChatService) -> les mostra a ELLES (els
        #     exemples desapareixen);
        #   - conversa començada però sense suggeriments (salutació, out-of-corpus…)
        #     -> cap chip.
        # Clicar un chip llança la pregunta i genera els suggeriments següents
        # -> bucle d'exploració. Es dispara al carregar i quan canvien xat/suggeriments.
        def _chip(question: str, elem_class: str) -> None:
            gr.Button(question, size="sm", elem_classes=elem_class).click(
                _run_question,
                inputs=[gr.State(question), ci.chatbot],
                outputs=[ci.chatbot, suggestions_state, last_query_state],
            )

        @gr.render(
            inputs=[suggestions_state, ci.chatbot, last_query_state, lang],
            triggers=[demo.load, suggestions_state.change, ci.chatbot.change, lang.change],
        )
        def _render_chips(suggestions, history, last_query, lang_value):
            # Feedback sobre l'última resposta: només té sentit si ja n'hi ha una.
            if history:
                with gr.Row(elem_id="sigphi-feedback"):
                    up = gr.Button("👍", size="sm", elem_classes="sigphi-fb")
                    down = gr.Button("👎", size="sm", elem_classes="sigphi-fb")
                    up.click(lambda: _send_feedback(app, last_query, 1), outputs=[])
                    down.click(lambda: _send_feedback(app, last_query, -1), outputs=[])
            if suggestions:
                with gr.Row(elem_id="sigphi-suggestions"):
                    for q in suggestions:
                        _chip(q, "sigphi-sugg")
            elif not history:  # conversa encara no començada -> exemples inicials
                with gr.Row(elem_id="sigphi-examples"):
                    pool = EXAMPLE_POOL.get(lang_value, EXAMPLE_POOL["English"])
                    for q in random.sample(pool, N_EXAMPLES):
                        _chip(q, "sigphi-ex")

        footer = gr.HTML(_footer_html("English"))

        # Catàleg que coneix la IA, plegable: recompte + selector d'autor cercable.
        # Els NOMS d'autor es localitzen amb l'àlies real per idioma (authors_aliases.json):
        # els clàssics/antics tenen forma pròpia establerta (Aristotle -> Aristòtil),
        # els moderns solen coincidir amb el canònic i per tant no canvien. Els TÍTOLS
        # d'obra es tradueixen al títol publicat real (mapa curat work_titles.json,
        # font: enllaços interlingües de Wikipedia). Ambdós amb fallback a l'original.
        import json as _json
        import unicodedata as _ud

        def _nfc(s: str) -> str:
            # el corpus barreja formes Unicode composta/descomposta pels accents
            # (p. ex. "à" com a U+00E0 o com "a"+U+0300); normalitzem per no fallar
            # una cerca exacta de diccionari per un simple detall de codificació.
            return _ud.normalize("NFC", s)

        try:
            _ALIASES = _json.loads(get_settings().aliases_path.read_text(encoding="utf-8"))
        except Exception:
            _ALIASES = {}
        try:
            _wt = _json.loads(
                (get_settings().aliases_path.parent / "work_titles.json").read_text(encoding="utf-8")
            )
            _TITLES = {_nfc(k): e["titles"] for e in _wt for k in e["keys"]}
        except Exception:
            _TITLES = {}
        _LANG_CODE = {
            "Català": "ca", "Español": "es", "English": "en", "Français": "fr",
            "Deutsch": "de", "Italiano": "it", "Русский": "ru", "中文": "zh",
            "日本語": "ja", "العربية": "ar", "हिन्दी": "hi",
        }
        _cat: dict[str, list[str]] = {}

        def _author_label(author: str, code: str) -> str:
            """Nom de l'autor en l'idioma 'code' (àlies), o el canònic si no hi és."""
            return (_ALIASES.get(author) or {}).get(code, author)

        def _author_choices(code: str):
            # (etiqueta localitzada, valor canònic); conserva l'ordre del catàleg
            return [(_author_label(a, code), a) for a in _cat]

        def _title(work: str, code: str) -> str:
            """Títol de l'obra en l'idioma 'code', o l'original si no hi ha traducció."""
            return (_TITLES.get(_nfc(work)) or {}).get(code, work)

        with gr.Accordion(
            CATALOG_TITLES["English"], open=False, elem_id="sigphi-catalog"
        ) as catalog_acc:
            catalog_summary = gr.Markdown("")
            author_pick = gr.Dropdown(
                choices=[], label=BROWSE_LABELS["English"], elem_id="sigphi-author-pick"
            )
            works_md = gr.Markdown("")

        def _catalog_summary(lang_value) -> str:
            n_works = sum(len(w) for w in _cat.values())
            tmpl = SUMMARY_TMPL.get(lang_value, SUMMARY_TMPL["English"])
            return tmpl.format(a=len(_cat), w=n_works, p=app.state.chunk_store.count())

        def _catalog_init(lang_value):
            _cat.clear()
            for it in app.state.chunk_store.catalog():
                _cat[it["author"]] = it["works"]
            code = _LANG_CODE.get(lang_value, "en")
            return (
                _catalog_summary(lang_value),
                gr.update(choices=_author_choices(code), value=None),
                "",
            )

        def _author_works(author, lang_value):
            works = _cat.get(author or "", [])
            if not works:
                return ""
            code = _LANG_CODE.get(lang_value, "en")
            name = _author_label(author, code)
            works_word = WORKS_WORD.get(lang_value, WORKS_WORD["English"])
            body = "\n".join(f"- {_title(w, code)}" for w in works)
            return f"**{name}** — {len(works)} {works_word}:\n\n{body}"

        demo.load(_catalog_init, inputs=lang, outputs=[catalog_summary, author_pick, works_md])
        author_pick.change(_author_works, inputs=[author_pick, lang], outputs=works_md)

        # UN sol gestor de canvi d'idioma: re-etiqueta TOTA la UI (abans el
        # placeholder del textbox, la benvinguda del xat i el catàleg quedaven
        # sempre en anglès).
        def _relang(l, author):
            code = _LANG_CODE.get(l, "en")
            return (
                _hero_html(l),
                HEADERS.get(l, HEADERS["English"]),
                _footer_html(l),
                gr.update(placeholder=PLACEHOLDERS.get(l, PLACEHOLDERS["English"])),
                gr.update(placeholder=WELCOMES.get(l, WELCOMES["English"])),
                gr.update(label=CATALOG_TITLES.get(l, CATALOG_TITLES["English"])),
                _catalog_summary(l),
                gr.update(
                    choices=_author_choices(code),
                    value=author,
                    label=BROWSE_LABELS.get(l, BROWSE_LABELS["English"]),
                ),
                _author_works(author, l),
            )

        lang.change(
            _relang,
            inputs=[lang, author_pick],
            outputs=[
                hero, header, footer, ci.textbox, ci.chatbot,
                catalog_acc, catalog_summary, author_pick, works_md,
            ],
        )
    return demo


def build_app() -> FastAPI:
    app = FastAPI(title="SigPhi", lifespan=lifespan)
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.include_router(routes_health.router)
    app.include_router(routes_chat.router)
    static_dir = Path(__file__).resolve().parent / "static"
    app.mount(
        "/static", StaticFiles(directory=str(static_dir), check_dir=False), name="static"
    )
    try:
        demo = _build_gradio(app)
    except Exception:
        logging.getLogger("sigphi").exception("UI multilingüe ha fallat; faig servir la UI simple")
        demo = gr.ChatInterface(fn=_make_respond(app))
    mount_kwargs = {"favicon_path": str(static_dir / "logo.svg")}
    if _MOUNT_SUPPORTS_CSS:  # Gradio 6+: l'estil s'aplica en muntar
        mount_kwargs.update(theme=SIGPHI_THEME, css=SIGPHI_CSS)
    if _MOUNT_SUPPORTS_HEAD:  # metadades SEO/OG + font amb preconnect (no bloquejant)
        mount_kwargs.update(head=SIGPHI_HEAD)
    app = gr.mount_gradio_app(app, demo, path="/", **mount_kwargs)
    return app


app = build_app()
