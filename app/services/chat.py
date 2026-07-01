"""ChatService: orquestra el RAG end-to-end.

Flux: retrieve (amb filtre d'autor) -> munta context amb CAVEATS -> LLM genera
resposta fidel a les fonts -> recull la llista de fonts (amb avisos ⚠).
"""
from __future__ import annotations
import re
from dataclasses import dataclass, field

from app.domain.caveats import discriminatory_warning, historical_context_note
from app.domain.interfaces import LLMInterface
from app.domain.models import RetrievedChunk
from app.services.biographies import background_block
from app.services.prompts import NO_CORPUS_MESSAGE, SUGGESTIONS_PROMPT, SYSTEM_PROMPT
from app.services.retrieval import RetrievalService

# Captura [[NO_SOURCES]] (i variants amb un sol claudàtor) en qualsevol posició.
_NO_SOURCES_RE = re.compile(r"\s*\[+\s*NO_SOURCES\s*\]+\s*")

# Missatge quan s'arriba al tope de despesa mensual (protecció de factura). Trilingüe.
_BUDGET_MSG = (
    "⏳ SigPhi ha arribat al límit d'ús d'aquest mes. Disculpa les molèsties; torna-ho a provar més endavant.\n"
    "⏳ SigPhi ha alcanzado el límite de uso de este mes. Disculpa las molestias; inténtalo más adelante.\n"
    "⏳ SigPhi has reached this month's usage limit. Sorry for the inconvenience; please try again later."
)

# Xarxa de seguretat DEFENSIVA: els suggeriments ja NO es demanen dins la resposta
# principal (ara és una crida separada i garantida, veure generate_suggestions a
# ChatService.answer). Aquest regex només neteja la resposta visible si el model,
# per costum après, hi cola igualment un bloc [[SUGGESTIONS]] espontani.
_SUGGESTIONS_RE = re.compile(r"\[+\s*SUGGESTIONS\s*\]+\s*(.*)\Z", re.IGNORECASE | re.DOTALL)


def split_suggestions(text: str) -> tuple[str, list[str]]:
    """Separa la resposta d'un bloc [[SUGGESTIONS]] espontani, si n'hi ha.

    Retorna (resposta_neta, llista_de_preguntes). Si no hi ha bloc, la llista és
    buida i la resposta queda intacta. Treu vinyetes/numeració de cada línia i
    limita a 3 suggeriments (robust a sortides una mica desviades del format)."""
    m = _SUGGESTIONS_RE.search(text)
    if not m:
        return text, []
    answer = text[: m.start()].rstrip()
    suggestions: list[str] = []
    for line in m.group(1).splitlines():
        q = re.sub(r"^\s*(?:[-*•·]|\d+[.)])\s*", "", line).strip()
        if q:
            suggestions.append(q)
    return answer, suggestions[:3]

# SEGUIMENTS: missatges que NO introdueixen un tema nou sinó que demanen re-fer la
# resposta anterior (canvi d'idioma, més detall, "per què", etc.). Per a aquests, el
# retrieval ha de reutilitzar el TEMA de la pregunta ANTERIOR (si no, "En català"
# recupera textos catalans aleatoris i el bot denega). NO inclou "i/and X" perquè
# sovint introdueixen tema nou.
_LANG_REQUEST_RE = re.compile(
    r"^\s*(?:en|in|auf|på|по)\s+[\w'’]+\s*[!.?]*\s*$"
    r"|^\s*(?:translat\w*|tradu\w+|traduis\w*|traduci\w*)\b",
    re.I,
)
_META_KW_RE = re.compile(
    r"\b(?:m[ée]s|more|explica\w*|explain\w*|amplia\w*|detalla\w*|elaborate|resum\w*|"
    r"summar\w*|simplif\w*|simpler|shorter|breu\w*|briefly|per\s*qu[èe]|perqu[èe]|why|"
    r"pourquoi|por\s*qu[ée]|warum|continua|continue|seg[uü]eix)\b",
    re.I,
)


def _is_followup(query: str) -> bool:
    """El missatge demana re-fer/ajustar la resposta anterior (no obre tema nou)?"""
    q = (query or "").strip()
    if not q:
        return False
    if _LANG_REQUEST_RE.match(q):  # "en català", "in english", "tradueix"...
        return True
    return len(q.split()) <= 3 and bool(_META_KW_RE.search(q))  # curt + paraula meta


@dataclass(frozen=True, slots=True)
class ChatResult:
    """Resultat d'un torn de xat: resposta + fonts citables + chunks crus + suggeriments."""
    answer: str
    sources: list[str]
    retrieved: list[RetrievedChunk]
    suggestions: list[str] = field(default_factory=list)


def format_context(
    retrieved: list[RetrievedChunk], bios: dict[str, str] | None = None
) -> str:
    """Munta el context per al LLM, amb capçalera i CAVEAT per bloc.

    Si hi ha biografies, s'anteposa un bloc de REREFONS d'autor (context editorial
    no citable) per als autors presents, abans de les fonts primàries."""
    sections = []
    authors: list[str] = []
    for r in retrieved:
        c = r.chunk
        if c.author and c.author not in authors:
            authors.append(c.author)
        header = f"Source: {c.author} — {c.work}"
        if c.language:
            header += f" ({c.language})"
        header += f" [relevance: {r.score:.0%}]"
        caveat_parts = []
        disc = discriminatory_warning(c.author, c.work, c.text)
        if disc:
            caveat_parts.append(disc)
        ctx = historical_context_note(c.author, c.work, c.text)
        if ctx:
            caveat_parts.append(ctx)
        if c.note and c.note != "—":
            caveat_parts.append(c.note)
        if caveat_parts:
            header += f"\nCAVEAT: {' | '.join(caveat_parts)}"
        sections.append(f"[{header}]\n{c.text}")
    body = "\n\n---\n\n".join(sections)
    bg = background_block(authors, bios or {})
    return f"{bg}\n\n=====\n\n{body}" if bg else body


def get_sources(retrieved: list[RetrievedChunk]) -> list[str]:
    """Llista de fonts úniques, amb marca ⚠ si fragmentàries/no directes o discriminatòries."""
    # Obres (autor+títol) amb almenys UN chunk recuperat que dispara l'avís: així la
    # marca de la font és coherent encara que l'avís sigui a nivell de passatge i els
    # chunks arribin en qualsevol ordre (la deduplicació per etiqueta no perd el flag).
    disc_works = {
        (r.chunk.author, r.chunk.work)
        for r in retrieved
        if discriminatory_warning(r.chunk.author, r.chunk.work, r.chunk.text)
    }
    ctx_works = {
        (r.chunk.author, r.chunk.work)
        for r in retrieved
        if historical_context_note(r.chunk.author, r.chunk.work, r.chunk.text)
    }
    seen: set[str] = set()
    sources: list[str] = []
    for r in retrieved:
        c = r.chunk
        label = f"{c.author} — {c.work}".strip(" —") if c.author else c.work
        flags = []
        if (c.author, c.work) in disc_works:
            flags.append("contingut discriminatori")
        if (c.author, c.work) in ctx_works:
            flags.append("context històric")
        if c.note and c.note != "—":
            if c.completeness and c.completeness != "Complete work":
                flags.append(c.completeness.lower())
            if c.authorship and c.authorship != "Written by the author":
                flags.append(c.authorship.lower())
        if flags:
            label += f" [⚠ {'; '.join(flags)}]"
        if label not in seen:
            seen.add(label)
            sources.append(label)
    return sources


class ChatService:
    def __init__(
        self,
        llm: LLMInterface,
        retrieval: RetrievalService,
        max_history: int = 5,
        biographies: dict[str, str] | None = None,
        meter=None,
        monthly_budget_eur: float = 0.0,
    ) -> None:
        self._llm = llm
        self._retrieval = retrieval
        self._max_history = max_history
        self._bios = biographies or {}
        self._meter = meter  # UsageMeter-like (.month_cost_eur()) o None
        self._budget = monthly_budget_eur

    def answer(
        self,
        query: str,
        history: list[tuple[str, str]] | None = None,
    ) -> ChatResult:
        # Tope de despesa mensual: si s'hi ha arribat, no cridem l'LLM (protecció de
        # factura). El retrieval és local (gratuït), però l'estalviem igualment.
        if (
            self._meter is not None
            and self._budget > 0
            and self._meter.month_cost_eur() >= self._budget
        ):
            return ChatResult(answer=_BUDGET_MSG, sources=[], retrieved=[])

        # Per a seguiments (canvi d'idioma, "explica més"...) recuperem amb el TEMA
        # de la pregunta anterior, no amb el text literal del seguiment. L'LLM, però,
        # rep la instrucció ORIGINAL + l'historial, així re-fà la resposta com es demana.
        retrieval_query = query
        hist_pairs = history or []
        if hist_pairs and _is_followup(query):
            prev_q = hist_pairs[-1][0]
            if prev_q:
                retrieval_query = f"{prev_q}\n{query}"

        retrieved = self._retrieval.retrieve(retrieval_query)
        if not retrieved:
            return ChatResult(answer=NO_CORPUS_MESSAGE, sources=[], retrieved=[])
        context = format_context(retrieved, self._bios)
        hist = (history or [])[-self._max_history :]
        text = self._llm.generate(SYSTEM_PROMPT, query, context, hist)
        # Neteja defensiva d'un bloc [[SUGGESTIONS]] espontani (ja no es demana a la
        # resposta principal; els suggeriments "de veritat" venen d'una crida a part
        # més avall, sempre que la resposta faci servir les fonts).
        text, _ = split_suggestions(text)
        # Si l'LLM marca que NO ha fet servir les fonts (salutació, meta, regla
        # 3/14/20...), treu la marca, amaga les fonts i no demanem suggeriments.
        if "NO_SOURCES" in text:
            text = _NO_SOURCES_RE.sub(" ", text).strip()
            return ChatResult(answer=text, sources=[], retrieved=retrieved, suggestions=[])
        # Crida SEPARADA i garantida per als 3 suggeriments: no depèn que la resposta
        # citada (que pot ser llarga) arribi a incloure el bloc abans de truncar-se.
        suggestions = self._llm.generate_suggestions(SUGGESTIONS_PROMPT, query, text, context)
        return ChatResult(
            answer=text,
            sources=get_sources(retrieved),
            retrieved=retrieved,
            suggestions=suggestions,
        )
