"""Tests de configuració de GeminiLLM (model separat per als suggeriments,
thinking_budget=0 al client de suggeriments). No toquen Gemini de veritat:
ChatGoogleGenerativeAI no valida credencials ni fa cap crida de xarxa a
__init__, només desa la configuració -- podem inspeccionar-la directament."""
from __future__ import annotations

from app.infrastructure.llm import GeminiLLM


def test_suggestions_model_defaults_to_main_model_when_not_set():
    llm = GeminiLLM(api_key="test-key-not-real", model="gemini-2.5-flash-lite")
    assert llm._llm.model.endswith("gemini-2.5-flash-lite")
    assert llm._suggest_llm.model.endswith("gemini-2.5-flash-lite")


def test_suggestions_model_uses_separate_model_when_set():
    # A propòsit DIFERENT del principal: la quota gratuïta és per model, així
    # que compartir-lo gastava el mateix dipòsit amb 2 crides per resposta.
    llm = GeminiLLM(
        api_key="test-key-not-real",
        model="gemini-2.5-flash-lite",
        suggestions_model="gemini-2.5-flash",
    )
    assert llm._llm.model.endswith("gemini-2.5-flash-lite")
    assert llm._suggest_llm.model.endswith("gemini-2.5-flash")


def test_suggestions_client_disables_thinking_budget():
    # Trobat en producció: gemini-2.5-flash (a diferència de flash-lite) reserva
    # per defecte part del tope de tokens per a "pensament" intern -> amb el
    # tope de 256 la resposta sortia tallada a mitja paraula. La tria de 3
    # preguntes no necessita raonament.
    llm = GeminiLLM(
        api_key="test-key-not-real",
        model="gemini-2.5-flash-lite",
        suggestions_model="gemini-2.5-flash",
    )
    assert llm._suggest_llm.thinking_budget == 0


def test_main_client_leaves_thinking_budget_untouched():
    # NOMÉS el client de suggeriments es toca; el principal queda amb el
    # comportament per defecte del model (no forcem cap valor).
    llm = GeminiLLM(api_key="test-key-not-real", model="gemini-2.5-flash-lite")
    assert llm._llm.thinking_budget is None


def test_suggestions_client_has_low_token_cap():
    llm = GeminiLLM(api_key="test-key-not-real", model="gemini-2.5-flash-lite")
    assert llm._suggest_llm.max_output_tokens == 256
