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

# Pou d'exemples (en anglès). A cada càrrega de pàgina (via @gr.render) se'n
# trien N_EXAMPLES a l'atzar, així varien a cada refresc. El bot respon igualment
# en l'idioma de la pregunta; aquests només són la mostra.
N_EXAMPLES = 3
EXAMPLE_POOL_EN = [
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
]

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
            inputs=[suggestions_state, ci.chatbot, last_query_state],
            triggers=[demo.load, suggestions_state.change, ci.chatbot.change],
        )
        def _render_chips(suggestions, history, last_query):
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
                    for q in random.sample(EXAMPLE_POOL_EN, N_EXAMPLES):
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
