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
from app.infrastructure.vector_db import build_vector_db
from app.services.chat import ChatService
from app.services.retrieval import RetrievalService


@asynccontextmanager
async def lifespan(app: FastAPI):
    s = get_settings()
    embedder = SentenceTransformersEmbedder(s.embed_model)
    chunk_store = ChunkStore(s.chunk_store_path)
    vector_db = build_vector_db(s, chunk_store=chunk_store)
    llm = GeminiLLM(s.google_api_key, model=s.gemini_model)
    retrieval = RetrievalService(embedder, vector_db, s.aliases_path, top_k=s.top_k)

    app.state.chunk_store = chunk_store
    app.state.vector_db = vector_db
    app.state.chat_service = ChatService(llm, retrieval)
    yield
    chunk_store.close()


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


# Hero (logo + wordmark + lema). El logo és la marca: estrella blau marí
# (#1a2a4f) amb accents daurats (#c9a227) i "ΣΦ".
HERO_HTML = (
    '<div id="sigphi-hero">'
    '<img src="/static/logo.svg" alt="SigPhi" class="sigphi-logo">'
    '<div class="sigphi-wordmark">SigPhi</div>'
    '<div class="sigphi-sub">Φιλοσοφία · filosofia des de fonts primàries</div>'
    "</div>"
)

# Paleta de marca + tipografia clàssica, responsive (desktop i mòbil).
SIGPHI_CSS = """
@import url('https://fonts.googleapis.com/css2?family=Playfair+Display:wght@600;700&display=swap');

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

/* Selector d'idioma com a píndoles */
#sigphi-lang { display:flex; justify-content:center; margin:6px 0 2px; }
#sigphi-lang .wrap, #sigphi-lang fieldset { display:flex !important; gap:6px; justify-content:center; flex-wrap:wrap; border:0 !important; }
#sigphi-lang label {
  border:1px solid #e3ddcf !important; border-radius:999px !important; padding:5px 16px !important;
  background:#fff; color:var(--sig-navy); cursor:pointer; transition:all .15s; font-size:.9rem;
}
#sigphi-lang label:has(input:checked) { background:var(--sig-navy); color:#fff; border-color:var(--sig-navy) !important; }

/* Capçalera descriptiva */
#sigphi-header { text-align:center; color:#374151; max-width:680px; margin:4px auto 8px; }
#sigphi-header h3 { font-family:'Playfair Display', Georgia, serif; color:var(--sig-navy); margin:.2em 0 .3em; }
#sigphi-header strong { color:var(--sig-navy); }

/* Xat */
#sigphi-chat { border:1px solid #e7e2d6 !important; border-radius:16px !important; background:#fff !important;
  box-shadow:0 1px 4px rgba(26,42,79,.06); }
#sigphi-chat a { color:var(--sig-navy); text-decoration:underline; text-decoration-color:var(--sig-gold); }

/* Botons primaris i exemples en to marca */
button.primary, .primary { background:var(--sig-navy) !important; border-color:var(--sig-navy) !important; }
.examples .example, [class*="example"] button {
  border:1px solid #e3ddcf !important; border-radius:12px !important; background:#fff !important;
  color:var(--sig-navy) !important; transition:all .15s;
}
.examples .example:hover, [class*="example"] button:hover { border-color:var(--sig-gold) !important; box-shadow:0 2px 8px rgba(201,162,39,.18); }

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

# Exemples (4, en anglès) que es mostren com a suggeriments inicials. El bot
# respon igualment en l'idioma de la pregunta; aquests només són la mostra.
EXAMPLES = [
    "What did Plato say about justice in The Republic?",
    "What are the Five Pillars of Islam?",
    "What did Marcus Aurelius say about death?",
    "Compare Plato and Nietzsche on morality",
]

# Capçalera (títol + descripció) localitzada. Nota: el CONTINGUT de les respostes
# ja segueix l'idioma de la pregunta (regla 7); això només és la crom de la UI.
HEADERS = {
    "Català": (
        "### SigPhi — Filosofia des de fonts primàries\n"
        "Respon NOMÉS amb textos filosòfics i religiosos primaris de domini públic, "
        "amb cites verificables. **Pregunta en l'idioma que vulguis** i et respondrà "
        "en el mateix."
    ),
    "Español": (
        "### SigPhi — Filosofía desde fuentes primarias\n"
        "Responde SOLO con textos filosóficos y religiosos primarios de dominio "
        "público, con citas verificables. **Pregunta en el idioma que quieras** y te "
        "responderá en el mismo."
    ),
    "English": (
        "### SigPhi — Philosophy from primary sources\n"
        "Answers ONLY from primary public-domain philosophical and religious texts, "
        "with verifiable citations. **Ask in any language** and it replies in the same."
    ),
    "Français": (
        "### SigPhi — La philosophie à partir des sources primaires\n"
        "Répond UNIQUEMENT à partir de textes philosophiques et religieux primaires "
        "du domaine public, avec des citations vérifiables. **Posez votre question "
        "dans la langue de votre choix** et il répondra dans la même."
    ),
    "Deutsch": (
        "### SigPhi — Philosophie aus Primärquellen\n"
        "Antwortet AUSSCHLIESSLICH auf Grundlage gemeinfreier philosophischer und "
        "religiöser Primärtexte, mit überprüfbaren Zitaten. **Fragen Sie in jeder "
        "Sprache** und es antwortet in derselben."
    ),
    "Italiano": (
        "### SigPhi — Filosofia dalle fonti primarie\n"
        "Risponde SOLO con testi filosofici e religiosi primari di pubblico dominio, "
        "con citazioni verificabili. **Fai la domanda nella lingua che preferisci** "
        "e risponderà nella stessa."
    ),
    "Русский": (
        "### SigPhi — Философия из первоисточников\n"
        "Отвечает ТОЛЬКО по первичным философским и религиозным текстам общественного "
        "достояния, с проверяемыми цитатами. **Задавайте вопрос на любом языке** — "
        "ответ будет на том же."
    ),
    "中文": (
        "### SigPhi — 源自原始文献的哲学\n"
        "仅依据公共领域的哲学与宗教原始文献作答，并附可查证的引用。"
        "**用任何语言提问**，都会以同一种语言回答。"
    ),
    "日本語": (
        "### SigPhi — 一次資料からの哲学\n"
        "パブリックドメインの哲学・宗教の一次資料のみに基づき、検証可能な出典付きで"
        "回答します。**どの言語で質問しても**、同じ言語で回答します。"
    ),
    "العربية": (
        "### SigPhi — الفلسفة من المصادر الأولية\n"
        "يجيب فقط اعتمادًا على نصوص فلسفية ودينية أولية في الملك العام، مع استشهادات "
        "قابلة للتحقق. **اسأل بأي لغة** وسيجيب باللغة نفسها."
    ),
    "हिन्दी": (
        "### SigPhi — मूल स्रोतों से दर्शन\n"
        "केवल सार्वजनिक डोमेन के मूल दार्शनिक और धार्मिक ग्रंथों के आधार पर उत्तर देता है, "
        "सत्यापन-योग्य उद्धरणों के साथ। **किसी भी भाषा में पूछें**, उसी भाषा में उत्तर मिलेगा।"
    ),
}


def _make_respond(app: FastAPI):
    def respond(message, history):
        chat_service = app.state.chat_service
        res = chat_service.answer(message, _history_to_tuples(history))
        if res.sources:
            srcs = "\n".join(f"- {s}" for s in res.sources)
            return f"{res.answer}\n\n---\n**Fonts:**\n{srcs}"
        return res.answer

    return respond


FOOTER_HTML = (
    '<div id="sigphi-footer">Només <b>fonts primàries de domini públic</b> · '
    "cites verificables · sense consells ni opinions</div>"
)


# Gradio 6 va moure theme/css del constructor de Blocks a mount_gradio_app().
# Detectem-ho per aplicar l'estil on toqui (robust a 4.x/5.x i 6.x).
import inspect as _inspect

_MOUNT_SUPPORTS_CSS = "css" in _inspect.signature(gr.mount_gradio_app).parameters


def _build_gradio(app: FastAPI) -> gr.Blocks:
    respond = _make_respond(app)
    # A Gradio <6, theme/css van al Blocks; a >=6 van a mount_gradio_app (a sota).
    blocks_kwargs = {} if _MOUNT_SUPPORTS_CSS else {"theme": SIGPHI_THEME, "css": SIGPHI_CSS}
    with gr.Blocks(title="SigPhi", **blocks_kwargs) as demo:
        gr.HTML(HERO_HTML)
        lang = gr.Radio(
            [
                "Català", "Español", "English", "Français", "Deutsch", "Italiano",
                "Русский", "中文", "日本語", "العربية", "हिन्दी",
            ],
            value="Català",
            show_label=False,
            container=False,
            elem_id="sigphi-lang",
        )
        header = gr.Markdown(HEADERS["Català"], elem_id="sigphi-header")
        gr.ChatInterface(
            fn=respond,
            examples=EXAMPLES,
            chatbot=gr.Chatbot(elem_id="sigphi-chat", height=460, show_label=False),
            textbox=gr.Textbox(
                placeholder="Fes una pregunta sobre filosofia… (en qualsevol idioma)",
                elem_id="sigphi-input",
                container=False,
                scale=7,
            ),
        )
        gr.HTML(FOOTER_HTML)
        lang.change(lambda l: HEADERS[l], inputs=lang, outputs=header)
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
    app = gr.mount_gradio_app(app, demo, path="/", **mount_kwargs)
    return app


app = build_app()
