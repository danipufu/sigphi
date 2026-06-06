"""
SigPhi — Interfície web (Gradio).
Reutilitza la lògica de sigphi.py (recuperació amb detecció d'autor, avisos,
guardarails). Funciona en local (enllaç compartit) i a HuggingFace Spaces.
Local:  SHARE=true python app.py   -> genera enllaç públic temporal (gradio.live)
Spaces: només cal app.py + requirements.txt + chroma_db/ + secret GOOGLE_API_KEY
"""
import os
from dotenv import load_dotenv
load_dotenv()

from sigphi import load_db, retrieve, format_context, build_messages, get_sources, MAX_HISTORY
from langchain_google_genai import ChatGoogleGenerativeAI
import gradio as gr

print("Carregant model multilingüe + ChromaDB...")
DB = load_db()
LLM = ChatGoogleGenerativeAI(model="gemini-2.5-flash-lite", temperature=0.2)
print("Llest.")

INTRO = (
    "**SigPhi** respon NOMÉS des de **textos primaris de domini públic**, amb **cites verificables**.\n\n"
    "- Pots preguntar en **qualsevol idioma** (català, castellà, anglès, francès...).\n"
    "- Avisa si un text és **fragmentari** o **no escrit directament per l'autor** (p.ex. Epictet, recollit per Arrià).\n"
    "- **No dona consells ni opinions**: només mostra què deien els pensadors.\n\n"
    "Corpus actual (a fons): Plató, Aristòtil, els estoics (Sèneca, Epictet, Marc Aureli), "
    "Plutarc, Ciceró, Plotí, Agustí, Boeci, Xenofont, Diògenes Laerci i Nietzsche."
)


def respond(message, history):
    message = (message or "").strip()
    if not message:
        return "Escriu una pregunta sobre filosofia."
    docs = retrieve(DB, message)
    if not docs:
        return "Encara no hi ha documents indexats."
    ctx = format_context(docs)
    # història (format messages de Gradio) -> tuples (humà, ia)
    hist, pending = [], None
    for m in history or []:
        role = m.get("role"); content = m.get("content", "")
        if role == "user":
            pending = content
        elif role == "assistant" and pending is not None:
            hist.append((pending, content)); pending = None
    msgs = build_messages(hist[-MAX_HISTORY:], message, ctx)
    try:
        answer = LLM.invoke(msgs).content
    except Exception as e:
        return f"Error de l'API del model: {e}"
    srcs = get_sources(docs)[:6]
    return answer + "\n\n---\n*Fonts:* " + " · ".join(srcs)


demo = gr.ChatInterface(
    fn=respond,
    title="SigPhi — Filosofia des de fonts primàries",
    description=INTRO,
    examples=[
        "Què deia Plató sobre la justícia a La República?",
        "Què ensenyava Epictet sobre allò que depèn de nosaltres?",
        "What did Seneca think about the shortness of life?",
        "Compara què deien Plató i Nietzsche sobre la moral",
        "Què deia Ciceró sobre l'amistat?",
    ],
)

if __name__ == "__main__":
    share = os.environ.get("SHARE", "").lower() == "true"
    demo.launch(share=share, server_name="0.0.0.0", server_port=int(os.environ.get("PORT", 7860)))
