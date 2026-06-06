import os
import re
from pathlib import Path
from dotenv import load_dotenv
from langchain_community.document_loaders import TextLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_chroma import Chroma
from corpus_meta import classify

load_dotenv()

CORPUS_DIR = Path(__file__).parent / "corpus"
CHROMA_DIR = str(Path(__file__).parent / "chroma_db")
COLLECTION_NAME = "sigphi_corpus"

CHUNK_SIZE = 1500
CHUNK_OVERLAP = 300
# MULTILINGÜE (384-dim): permet consultes en català/castellà que troben textos en
# anglès I en original (grec/llatí/alemany...). Test creuat CA→EN 0.79, CA→GR 0.84.
# A més va a ~16 chunks/s (més ràpid que mpnet 1.2 i MiniLM-L6 8.5).
EMBED_MODEL = "paraphrase-multilingual-MiniLM-L12-v2"

STOIC_AUTHORS = {"epictetus": "Epictetus", "marcus_aurelius": "Marcus Aurelius",
                 "seneca": "Seneca"}

# Àlies multilingües d'autor (en/ca/es/fr/ru/zh/ar/hi + original) generats amb Gemini
import json as _json
_ALIAS_PATH = Path(__file__).parent / "authors_aliases.json"
ALIASES = _json.loads(_ALIAS_PATH.read_text(encoding="utf-8")) if _ALIAS_PATH.exists() else {}


def author_alias_str(author):
    a = ALIASES.get(author, {})
    names = list(dict.fromkeys(v.strip() for v in a.values() if v and v.strip()))
    return " / ".join(names) if names else author


def parse_header(text):
    """Extreu les metadades de la capçalera SIGPHI si existeix; retorna (meta, body)."""
    m = re.match(r'^=====[^\n]*=====\n(.*?)\n=+\n+', text, re.S)
    if not m:
        return {}, text
    meta = {}
    for line in m.group(1).splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            meta[k.strip().lower()] = v.strip()
    return meta, text[m.end():]


def author_title_from_filename(name):
    low = name.lower()
    author = "Unknown"
    for key, val in STOIC_AUTHORS.items():
        if key in low:
            author = val
            break
    title = re.sub(r'\.txt$', '', name).replace('_', ' ')
    return author, title


DONE_LOG = Path(__file__).parent / "ingest_done.txt"
ADD_BATCH = 300          # chunks per lot d'inserció (més petit = menys pic de memòria)
MAX_FILES_PER_RUN = 200  # procés únic: fa tot el nucli (119) en una passada; si OOM, rellançar a mà (resumible)


def load_one(path):
    """Carrega un fitxer → llista de Documents amb metadades (capçalera treta)."""
    loader = TextLoader(str(path), encoding="utf-8")
    docs = loader.load()
    for doc in docs:
        meta, body = parse_header(doc.page_content)
        doc.page_content = body

        author = meta.get("author") or author_title_from_filename(path.name)[0]
        work = meta.get("work") or author_title_from_filename(path.name)[1]
        language = meta.get("language", "English")
        completeness = meta.get("completeness")
        authorship = meta.get("authorship")
        note = meta.get("note")
        if not (completeness and authorship and note):
            completeness, authorship, note = classify(author, work)

        doc.metadata.update({
            "source": path.name, "author": author, "work": work,
            "language": language, "completeness": completeness,
            "authorship": authorship, "note": note,
        })
    return docs


def index_corpus():
    print("=== SigPhi Ingest (per fitxer, en lots, resumible) ===\n")
    txt_files = sorted(CORPUS_DIR.glob("*.txt"))
    if not txt_files:
        print("No s'han trobat fitxers TXT a corpus/.")
        return
    # Mode NUCLI CURAT: si existeix core_list.txt, només indexa aquests fitxers
    core_path = Path(__file__).parent / "core_list.txt"
    if core_path.exists():
        core = set(l.strip() for l in core_path.read_text(encoding="utf-8").splitlines() if l.strip())
        txt_files = [f for f in txt_files if f.name in core]
        print(f">>> MODE NUCLI CURAT: {len(txt_files)} fitxers (de {core_path.name})")

    done = set(DONE_LOG.read_text(encoding="utf-8").splitlines()) if DONE_LOG.exists() else set()
    pending_all = [p for p in txt_files if p.name not in done]
    print(f"Fitxers totals: {len(txt_files)} | ja fets: {len(done)} | pendents: {len(pending_all)}")
    if not pending_all:
        print("Tot indexat. Res a fer.")
        return
    # Processa només un bloc per execució (evita OOM); el bucle extern rellança
    pending = pending_all[:MAX_FILES_PER_RUN]
    print(f"Aquesta execució: {len(pending)} fitxers (límit {MAX_FILES_PER_RUN})\n")

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE, chunk_overlap=CHUNK_OVERLAP)

    print(f"Inicialitzant embeddings locals ({EMBED_MODEL})...")
    embeddings = HuggingFaceEmbeddings(model_name=EMBED_MODEL)
    db = Chroma(collection_name=COLLECTION_NAME, embedding_function=embeddings,
                persist_directory=CHROMA_DIR)

    total_chunks = 0
    import time as _t
    import gc
    t0 = _t.time()
    for i, path in enumerate(pending, 1):
        try:
            docs = load_one(path)
            chunks = splitter.split_documents(docs)
            # Incrusta NOM EN 8 IDIOMES + obra a cada chunk → cerca pel nom funciona
            # en qualsevol idioma estratègic ("孫子兵法"/"L'art de la guerre"/"فن الحرب"...)
            for ch in chunks:
                names = author_alias_str(ch.metadata.get("author", ""))
                w = ch.metadata.get("work", "")
                ch.page_content = f"{names} — {w}:\n{ch.page_content}"
            for j in range(0, len(chunks), ADD_BATCH):
                db.add_documents(chunks[j:j + ADD_BATCH])
            total_chunks += len(chunks)
            with DONE_LOG.open("a", encoding="utf-8") as fh:
                fh.write(path.name + "\n")
            el = _t.time() - t0
            rate = total_chunks / el if el > 0 else 0
            print(f"[{i}/{len(pending)}] {path.name[:55]:55} +{len(chunks):4} chunks "
                  f"| acum {total_chunks:6} | {rate:4.0f} ch/s")
            del docs, chunks
            gc.collect()
        except Exception as e:
            print(f"[{i}/{len(pending)}] ERROR {path.name}: {e}")

    print(f"\nIndexació completada.")
    print(f"  Chunks indexats aquesta sessió: {total_chunks}")
    print(f"  Base de dades a: {CHROMA_DIR}")


if __name__ == "__main__":
    index_corpus()
