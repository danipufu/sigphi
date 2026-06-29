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
from app.infrastructure.vector_db import build_vector_db
from app.services.biographies import load_biographies
from app.services.chat import ChatService
from app.services.retrieval import RetrievalService
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
    retrieval = RetrievalService(embedder, vector_db, s.aliases_path, top_k=s.top_k)
    bios = load_biographies(s.biographies_path)

    app.state.chunk_store = chunk_store
    app.state.vector_db = vector_db
    app.state.usage_meter = meter
    app.state.chat_service = ChatService(
        llm, retrieval, biographies=bios, meter=meter, monthly_budget_eur=s.monthly_budget_eur
    )
    yield
    chunk_store.close()
    meter.close()


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
#sigphi-header { text-align:center; color:#374151; max-width:640px; margin:4px auto 8px; }
#sigphi-header p { margin:.25em 0; }
#sigphi-header strong { color:var(--sig-navy); }
#sigphi-header p:last-child { font-size:.8rem; color:#a59b86; }  /* avís de fase beta, tènue */

/* Xat */
#sigphi-chat { border:1px solid #e7e2d6 !important; border-radius:16px !important; background:#fff !important;
  box-shadow:0 1px 4px rgba(26,42,79,.06); }
#sigphi-chat a { color:var(--sig-navy); text-decoration:underline; text-decoration-color:var(--sig-gold); }

/* Botons primaris en to marca */
button.primary, .primary { background:var(--sig-navy) !important; border-color:var(--sig-navy) !important; }

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


def _build_gradio(app: FastAPI) -> gr.Blocks:
    def respond_full(message, history):
        """UI principal: retorna (markdown_amb_fonts, llista_suggeriments). El segon
        valor va a additional_outputs -> suggestions_state -> chips de seguiment."""
        res = app.state.chat_service.answer(message, _history_to_tuples(history))
        return _format_answer_md(res), res.suggestions

    # A Gradio <6, theme/css van al Blocks; a >=6 van a mount_gradio_app (a sota).
    blocks_kwargs = {} if _MOUNT_SUPPORTS_CSS else {"theme": SIGPHI_THEME, "css": SIGPHI_CSS}
    with gr.Blocks(title="SigPhi", **blocks_kwargs) as demo:
        hero = gr.HTML(_hero_html("English"))
        lang = gr.Radio(
            [
                "Català", "Español", "English", "Français", "Deutsch", "Italiano",
                "Русский", "中文", "日本語", "العربية", "हिन्दी",
            ],
            value="English",
            show_label=False,
            container=False,
            elem_id="sigphi-lang",
        )
        header = gr.Markdown(HEADERS["English"], elem_id="sigphi-header")
        # Estat amb les preguntes suggerides de l'ÚLTIMA resposta. S'omple via
        # additional_outputs del ChatInterface (i del runner de chips). Quan canvia,
        # @gr.render recrea els chips de seguiment.
        suggestions_state = gr.State([])
        ci = gr.ChatInterface(
            fn=respond_full,
            chatbot=gr.Chatbot(elem_id="sigphi-chat", height=460, show_label=False),
            textbox=gr.Textbox(
                placeholder="Ask a question about philosophy… (in any language)",
                elem_id="sigphi-input",
                container=False,
                scale=7,
            ),
            additional_outputs=[suggestions_state],
        )

        # Runner compartit per als chips (exemples i suggeriments): omple el xat amb
        # la pregunta, la respon, i actualitza els suggeriments (buida'ls mentre
        # carrega -> reapareixen amb els nous). Surt a (chatbot, suggestions_state).
        def _run_question(question, history):
            history = history or []
            yield history + [
                {"role": "user", "content": question},
                {"role": "assistant", "content": "…"},
            ], []
            md, suggestions = respond_full(question, history)
            yield history + [
                {"role": "user", "content": question},
                {"role": "assistant", "content": md},
            ], suggestions

        # Chips sota el xat. UN sol render decideix QUÈ mostrar segons l'estat:
        #   - conversa NO començada -> N_EXAMPLES exemples a l'atzar (varien a cada
        #     càrrega de pàgina);
        #   - hi ha preguntes suggerides (regla 21) -> les mostra a ELLES (els
        #     exemples desapareixen);
        #   - conversa començada però sense suggeriments (salutació, out-of-corpus…)
        #     -> cap chip.
        # Clicar un chip llança la pregunta i genera els suggeriments següents
        # -> bucle d'exploració. Es dispara al carregar i quan canvien xat/suggeriments.
        def _chip(question: str, elem_class: str) -> None:
            gr.Button(question, size="sm", elem_classes=elem_class).click(
                _run_question,
                inputs=[gr.State(question), ci.chatbot],
                outputs=[ci.chatbot, suggestions_state],
            )

        @gr.render(
            inputs=[suggestions_state, ci.chatbot],
            triggers=[demo.load, suggestions_state.change, ci.chatbot.change],
        )
        def _render_chips(suggestions, history):
            if suggestions:
                with gr.Row(elem_id="sigphi-suggestions"):
                    for q in suggestions:
                        _chip(q, "sigphi-sugg")
            elif not history:  # conversa encara no començada -> exemples inicials
                with gr.Row(elem_id="sigphi-examples"):
                    for q in random.sample(EXAMPLE_POOL_EN, N_EXAMPLES):
                        _chip(q, "sigphi-ex")

        footer = gr.HTML(_footer_html("English"))

        # Catàleg complet (autors + obres) que coneix la IA, plegable. Es pobla al
        # carregar la pàgina (demo.load), quan chunk_store ja és a app.state.
        with gr.Accordion(
            "📚 Authors & texts in the corpus", open=False, elem_id="sigphi-catalog"
        ):
            catalog_md = gr.Markdown("")

        def _catalog_md() -> str:
            cs = app.state.chunk_store
            items = cs.catalog()
            n_authors = len(items)
            n_works = sum(len(i["works"]) for i in items)
            n_chunks = cs.count()
            lines = [
                f"**{n_authors} authors · {n_works} works · {n_chunks:,} passages**",
                "",
            ]
            for it in items:
                lines.append(
                    f"- **{it['author']}** ({len(it['works'])}): "
                    + "; ".join(it["works"])
                )
            return "\n".join(lines)

        demo.load(_catalog_md, outputs=catalog_md)

        lang.change(
            lambda l: (_hero_html(l), HEADERS[l], _footer_html(l)),
            inputs=lang,
            outputs=[hero, header, footer],
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
    app = gr.mount_gradio_app(app, demo, path="/", **mount_kwargs)
    return app


app = build_app()
