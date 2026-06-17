"""GeminiLLM: adaptador del LLM de Google (Gemini) via LangChain."""
from __future__ import annotations

import logging
import re
import time

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_google_genai import ChatGoogleGenerativeAI

_log = logging.getLogger("sigphi")


# Marcadors DISCRIMINATIUS per idioma (alfabet llatí). Per desambiguar la llengua
# de la pregunta actual i anomenar-la EXPLÍCITAMENT al model (molt més fiable que
# "respon en el mateix idioma", que el model ignora si l'historial és en un altre).
# CLAU: només tokens que discriminen — s'EVITEN paraules compartides ("que", "sobre",
# "la", "de"...) que confonien (ex.: un català sense accents "que ... sobre" es
# detectava com a portuguès). Els articles plurals (els/los/os/les/gli) i el verb
# "dir" (diu/dice/diz/dit) discriminen molt bé català/espanyol/portuguès.
_LATIN_STOP = {
    "English": {"the", "what", "which", "did", "does", "how", "why", "who", "whose",
                "about", "say", "said", "are", "was", "were"},
    "Spanish": {"los", "las", "qué", "cómo", "cuál", "cuáles", "quién", "dice",
                "decía", "está", "según", "pero", "hizo", "pensaba"},
    "Catalan": {"els", "amb", "això", "aquest", "aquesta", "aquests", "dels", "diu",
                "diuen", "deia", "perquè", "però", "nosaltres", "vostè", "què", "són"},
    "French": {"les", "qu'est", "quoi", "comment", "pourquoi", "c'est", "vous",
               "votre", "dit", "disait", "était", "selon", "dans"},
    "German": {"was", "über", "und", "ist", "der", "die", "das", "nicht", "wie",
               "warum", "sagt", "sagte", "den", "dem", "eine"},
    "Italian": {"gli", "della", "delle", "perché", "sono", "cosa", "diceva", "sulla",
                "quali", "dei", "nella", "è"},
    "Portuguese": {"não", "você", "vocês", "então", "diz", "dizem", "porquê", "os",
                   "as", "uma", "à", "às"},
}


# Peticions EXPLÍCITES de canvi d'idioma com a seguiment ("en català", "in english",
# "auf deutsch"): el nom demanat -> la llengua de la resposta.
_LANG_REQUEST: dict[str, str] = {}
for _names, _lang in [
    (("català", "catala", "catalan"), "Catalan"),
    (("castellà", "castella", "castellano", "español", "espanol", "espanyol", "spanish"), "Spanish"),
    (("anglès", "angles", "anglés", "english", "inglés", "ingles", "inglese"), "English"),
    (("francès", "frances", "francés", "français", "francais", "french", "francese"), "French"),
    (("alemany", "deutsch", "german", "alemán", "aleman", "tedesco"), "German"),
    (("italià", "italia", "italiano", "italian"), "Italian"),
    (("rus", "russian", "ruso", "russe"), "Russian"),
    (("xinès", "xines", "chinese", "chino", "chinois"), "Chinese"),
    (("japonès", "japones", "japanese", "japonés", "japonais"), "Japanese"),
    (("àrab", "arab", "arabic", "árabe", "arabe"), "Arabic"),
    (("hindi",), "Hindi"),
    (("portuguès", "portugues", "português", "portuguese", "portugués"), "Portuguese"),
]:
    for _n in _names:
        _LANG_REQUEST[_n] = _lang


def _detect_language(text: str) -> str | None:
    """Nom (en anglès) de l'idioma de `text`, o None si no és prou clar. Els scripts
    no-llatins són senyal fort; per al llatí, desambigua amb stopwords distintives."""
    t = (text or "").strip()
    if not t:
        return None

    # Petició explícita: "en/in/auf <idioma>" (missatge curt) -> aquell idioma.
    if len(t.split()) <= 3:
        mreq = re.match(r"^(?:en|in|auf|på|по)\s+([^\s,.;:!?]+)", t, re.I)
        if mreq and mreq.group(1).lower() in _LANG_REQUEST:
            return _LANG_REQUEST[mreq.group(1).lower()]

    def cnt(lo: str, hi: str) -> int:
        return sum(1 for c in t if lo <= c <= hi)

    kana = cnt("぀", "ヿ")
    han = cnt("一", "鿿")
    if kana >= 1:
        return "Japanese"
    if cnt("가", "힣") >= 1:
        return "Korean"
    if han >= 1:
        return "Chinese"
    if cnt("Ѐ", "ӿ") >= 2:
        return "Russian"
    if cnt("؀", "ۿ") >= 2:
        return "Arabic"
    if cnt("֐", "׿") >= 2:
        return "Hebrew"
    if cnt("ऀ", "ॿ") >= 2:
        return "Hindi"
    if cnt("Ͱ", "Ͽ") + cnt("ἀ", "῿") >= 2:
        return "Greek"

    words = re.findall(r"[a-zàáâäçèéêëìíîïñòóôöùúûü'’]+", t.lower())
    if len(words) < 2:
        return None
    wset = set(words)
    scores = {lang: len(wset & {w.lower() for w in sw}) for lang, sw in _LATIN_STOP.items()}
    best = max(scores, key=scores.get)
    top = scores[best]
    if top == 0:
        return None
    # Empat clar (dos idiomes amb la mateixa puntuació màxima) -> no arrisquem.
    if sum(1 for v in scores.values() if v == top) > 1:
        return None
    return best

# Missatge amable quan Gemini està saturat (429) i s'esgoten els reintents. Trilingüe
# perquè no sabem encara l'idioma de la pregunta a aquest nivell.
_BUSY_MSG = (
    "⏳ El servei està rebent moltes peticions ara mateix; torna-ho a provar d'aquí uns segons.\n"
    "⏳ El servicio está recibiendo muchas peticiones; inténtalo de nuevo en unos segundos.\n"
    "⏳ The service is busy right now; please try again in a few seconds."
)


class GeminiLLM:
    """Genera respostes amb cites verificables, basant-se NOMES en el context.

    Patró de missatges:
        SystemMessage  -> regles de SigPhi (no opina, avisa de fragments, etc.)
        HumanMessage   -> el context recuperat (com a "material de treball")
        AIMessage      -> ack que farà servir només aquest material
        [history...]   -> torns previs de la conversa (opcional)
        HumanMessage   -> la pregunta de l'usuari
    temperature=0.2: respostes consistents i fidels a la font, poc creatives.
    """

    def __init__(self, api_key: str, model: str = "gemini-2.5-flash-lite") -> None:
        if not api_key:
            raise ValueError(
                "GOOGLE_API_KEY no està configurada. Defineix-la al .env "
                "o com a variable d'entorn abans d'instanciar GeminiLLM."
            )
        self._llm = ChatGoogleGenerativeAI(
            model=model,
            temperature=0.2,
            google_api_key=api_key,
            timeout=20,      # cada crida falla en <=20s en lloc de penjar-se indefinidament
            max_retries=0,   # desactiva la tempesta de reintents interns de langchain
            #                  (en fem de propis, acotats, a generate())
        )

    def generate(
        self,
        system_prompt: str,
        user_query: str,
        context: str,
        history: list[tuple[str, str]] | None = None,
    ) -> str:
        messages: list = [
            SystemMessage(content=system_prompt),
            HumanMessage(
                content=f"CONTEXT (fonts primàries recuperades):\n\n{context}"
            ),
            AIMessage(
                content="Understood. I will answer strictly from the provided material, "
                "and I will write my entire reply in the SAME language as the user's "
                "question itself — regardless of the language of the sources, the caveats, "
                "or earlier turns of the conversation."
            ),
        ]
        for user_turn, ai_turn in history or []:
            messages.append(HumanMessage(content=user_turn))
            messages.append(AIMessage(content=ai_turn))
        # Recordatori d'idioma ENGANXAT a la pregunta (salient just abans de generar):
        # contraresta el biaix de l'historial (ex.: torns anteriors en català fan que
        # el model segueixi en català encara que la pregunta actual sigui en castellà).
        # Si podem detectar la llengua, l'ANOMENEM explícitament (molt més fiable que
        # "el mateix idioma", que el model ignora quan l'historial és en un altre).
        lang = _detect_language(user_query)
        if lang:
            directive = (
                f"\n\n[IMPORTANT: the user's CURRENT question is in {lang}. Write your "
                f"ENTIRE reply in {lang}, regardless of the language of earlier turns or "
                "of the sources.]"
            )
        else:
            directive = (
                "\n\n[IMPORTANT: write your entire reply in the SAME language as THIS "
                "question, regardless of the language of earlier turns or of the sources.]"
            )
        messages.append(HumanMessage(content=user_query + directive))

        # Reintents amb espera creixent: el pla gratuït de Gemini limita ~req/min i
        # retorna 429 en ràfegues. Sense això, l'excepció arribaria a l'usuari com un 500.
        last_err: Exception | None = None
        for attempt in range(2):  # 2 intents (cada un acotat a 20s pel timeout)
            try:
                return self._llm.invoke(messages).content
            except Exception as e:  # 429 / timeout / errors transitoris de l'API
                last_err = e
                _log.warning("Gemini invoke ha fallat (intent %d/2): %s", attempt + 1, e)
                if attempt == 0:
                    time.sleep(2)  # una espera curta i tornem a provar
        _log.error("Gemini no respon després de 2 intents: %s", last_err)
        return _BUSY_MSG
