"""GeminiLLM: adaptador del LLM de Google (Gemini) via LangChain."""
from __future__ import annotations

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_google_genai import ChatGoogleGenerativeAI


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

    def __init__(self, api_key: str, model: str = "gemini-2.5-flash") -> None:
        if not api_key:
            raise ValueError(
                "GOOGLE_API_KEY no està configurada. Defineix-la al .env "
                "o com a variable d'entorn abans d'instanciar GeminiLLM."
            )
        self._llm = ChatGoogleGenerativeAI(
            model=model,
            temperature=0.2,
            google_api_key=api_key,
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

        resp = self._llm.invoke(messages)
        return resp.content
