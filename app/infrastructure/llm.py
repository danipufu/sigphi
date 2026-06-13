"""GeminiLLM: adaptador del LLM de Google (Gemini) via LangChain."""
from __future__ import annotations

import logging
import time

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_google_genai import ChatGoogleGenerativeAI

_log = logging.getLogger("sigphi")

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
        messages.append(
            HumanMessage(
                content=user_query
                + "\n\n[IMPORTANT: write your entire reply in the SAME language as THIS "
                "question, regardless of the language of earlier turns or of the sources.]"
            )
        )

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
