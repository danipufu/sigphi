import os
from pathlib import Path
from dotenv import load_dotenv
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_chroma import Chroma
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage

load_dotenv()

CHROMA_DIR = str(Path(__file__).parent / "chroma_db")
COLLECTION_NAME = "sigphi_corpus"
EMBED_MODEL = "paraphrase-multilingual-MiniLM-L12-v2"  # multilingüe, ha de coincidir amb ingest.py
TOP_K = 15                          # pujat per compensar la precisió de MiniLM
MAX_HISTORY = 5

SYSTEM_PROMPT = """You are SigPhi, a humanities assistant grounded exclusively in primary public-domain texts.

STRICT RULES:
1. Answer ONLY using the provided context. Never use outside knowledge.
2. Every claim must include a citation in this format: (Author, Work, Section/Chapter).
3. If the answer is not in the context, respond exactly: "This question is not directly addressed in the available texts."
4. Paraphrase by default. Use direct quotes only for iconic phrases or technical definitions.
5. Never offer personal opinions on whether an author is right or wrong.
6. When multiple authors address the same theme, show agreements and tensions without declaring a winner.
7. Respond in the same language the user used to ask the question.
8. Adapt response length to complexity: concise for simple questions, fuller for nuanced ones.
9. SOURCE CAVEATS — MANDATORY. Each context block has a header that may include a "CAVEAT:" note. This note warns that the text is INCOMPLETE (only fragments, a selection, or part of a larger work) or that it was NOT written directly by the named author (attributed/disputed authorship, recorded by students, compiled by disciples, or anonymous). Whenever your answer relies on such a source, you MUST briefly and explicitly warn the user of this caveat, in their language. Examples: "Note: only fragments of Heraclitus survive, quoted by later authors" / "The Analects were compiled by Confucius's disciples, not written by him" / "This work is only traditionally attributed to Laozi". Never present a fragmentary or attributed source as if it were a complete, directly-authored work.
10. Reflect uncertainty in citations: if authorship is attributed/uncertain, phrase it accordingly (e.g., "attributed to Sun Tzu, Art of War").
11. NO ADVICE. If the user asks for advice, guidance, or what they personally should do (e.g. "what should I do about my anxiety?", "how should I live?", "help me decide"), do NOT give your own advice, recommendations, or prescriptions. Briefly state that SigPhi does not give advice, then report only what the thinkers and texts said on that theme, with citations. The decision always remains the user's.
12. POLITICAL & IDEOLOGICAL NEUTRALITY. When asked about a thinker's politics, ideology, or affiliations, report ONLY what their own texts state (cited), and explicitly remind the user that SigPhi merely paraphrases the sources and does NOT endorse, promote, defend, or condemn any ideology, party, regime, or political position.
13. NEUTRAL COMPARISON. When comparing two or more religions, philosophies, or thinkers, lay out each position side by side strictly from the texts. Never judge which is better, truer, more valid, or more correct, and never take a side.
OVERARCHING PRINCIPLE: SigPhi neither opines nor decides. It never offers opinions, advice, endorsements, value judgements, or verdicts of its own. It only shows, attributes, and contextualizes what a given thinker or text said about a given topic — nothing more."""


import json
# Mapa àlies→autor canònic (per detectar autors anomenats a la consulta en 12 idiomes)
_ALIAS_FILE = Path(__file__).parent / "authors_aliases.json"
ALIAS2AUTHOR = {}
if _ALIAS_FILE.exists():
    for _canon, _names in json.loads(_ALIAS_FILE.read_text(encoding="utf-8")).items():
        for _v in list(_names.values()) + [_canon]:
            _v = (_v or "").strip().lower()
            # inclou àlies distintius: ASCII llargs (≥5) o qualsevol no-ASCII (xinès/àrab/...)
            if _v and (len(_v) >= 5 or any(ord(c) > 127 for c in _v)):
                ALIAS2AUTHOR.setdefault(_v, _canon)


def detect_authors(query):
    """Retorna autors canònics anomenats a la consulta (en qualsevol idioma)."""
    ql = query.lower()
    found = []
    for alias, canon in ALIAS2AUTHOR.items():
        if alias in ql and canon not in found:
            found.append(canon)
    return found


def load_db():
    embeddings = HuggingFaceEmbeddings(model_name=EMBED_MODEL)
    return Chroma(
        collection_name=COLLECTION_NAME,
        embedding_function=embeddings,
        persist_directory=CHROMA_DIR,
    )


def retrieve(db, query):
    """Recupera amb filtre per autor si la consulta n'anomena algun; si no, normal."""
    authors = detect_authors(query)
    if authors:
        flt = {"author": authors[0]} if len(authors) == 1 else {"author": {"$in": authors}}
        docs = db.similarity_search(query, k=TOP_K, filter=flt)
        if docs:
            return docs
    return db.similarity_search(query, k=TOP_K)


def load_retriever():  # compat: retorna db (usar amb retrieve())
    return load_db()


def format_context(docs):
    sections = []
    for doc in docs:
        m = doc.metadata
        author = m.get("author", "Unknown")
        work = m.get("work", m.get("source", "unknown"))
        lang = m.get("language", "")
        note = (m.get("note", "") or "").strip()

        header = f"Source: {author} — {work}"
        if lang:
            header += f" ({lang})"
        if note and note != "—":
            header += f"\nCAVEAT: {note}"

        sections.append(f"[{header}]\n{doc.page_content}")
    return "\n\n---\n\n".join(sections)


def get_sources(docs):
    seen = set()
    sources = []
    for doc in docs:
        m = doc.metadata
        author = m.get("author", "")
        work = m.get("work", m.get("source", "desconegut"))
        label = f"{author} — {work}".strip(" —") if author else work
        # marca breu de cautela
        note = (m.get("note", "") or "").strip()
        if note and note != "—":
            comp = m.get("completeness", "")
            auth = m.get("authorship", "")
            flags = []
            if comp and comp != "Complete work":
                flags.append(comp.lower())
            if auth and auth != "Written by the author":
                flags.append(auth.lower())
            if flags:
                label += f" [⚠ {'; '.join(flags)}]"
        if label not in seen:
            seen.add(label)
            sources.append(label)
    return sources


def build_messages(history, question, context):
    messages = [SystemMessage(content=SYSTEM_PROMPT)]

    context_note = (
        f"Use the following context to answer the question:\n\n{context}"
    )
    messages.append(HumanMessage(content=context_note))
    messages.append(AIMessage(content="Understood. I will answer strictly based on the provided context."))

    for human_msg, ai_msg in history:
        messages.append(HumanMessage(content=human_msg))
        messages.append(AIMessage(content=ai_msg))

    messages.append(HumanMessage(content=question))
    return messages


def run_chatbot():
    print("=== SigPhi — Humanities RAG Assistant ===")
    print('Escriu "exit" o "quit" per sortir.\n')

    try:
        db = load_db()
    except Exception as e:
        print(f"Error carregant ChromaDB: {e}")
        print("Assegura't d'haver executat ingest.py primer.")
        return

    llm = ChatGoogleGenerativeAI(
        model="gemini-2.5-flash-lite",
        temperature=0.2,
    )

    history = []

    while True:
        try:
            question = input("Tu: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nAdéu!")
            break

        if not question:
            continue

        if question.lower() in {"exit", "quit"}:
            print("Adéu!")
            break

        docs = retrieve(db, question)
        if not docs:
            print("\nSigPhi: No hi ha documents indexats. Executa ingest.py primer.\n")
            continue

        context = format_context(docs)
        sources = get_sources(docs)

        messages = build_messages(history, question, context)

        try:
            response = llm.invoke(messages)
            answer = response.content
        except Exception as e:
            print(f"\nError de l'API: {e}\n")
            continue

        print(f"\nSigPhi: {answer}")
        print(f"\n[Fonts: {', '.join(sources)}]\n")

        history.append((question, answer))
        if len(history) > MAX_HISTORY:
            history.pop(0)


if __name__ == "__main__":
    run_chatbot()
