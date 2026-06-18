"""Bloc 12 — Ingest del corpus al vector DB (Pinecone/Chroma) + ChunkStore.

Característiques:
  - RESUMIBLE: `ingest_done.txt` (per fitxer) + chunk_id determinista
    (`{fitxer}#{n}`) => upsert idempotent. Si peta a mig (OOM, tall de xarxa),
    es rellança i continua on anava.
  - Separa el TEXT EMBEGUT (amb prefix de noms d'autor en 12 idiomes -> cerca
    cross-lingual pel nom) del TEXT GUARDAT (net -> generació de qualitat).
  - Capçalera SIGPHI (=====...=====) per a metadades; si falta completeness/
    authorship/note, els dedueix amb caveats.classify().

Ús (al VPS, des de l'arrel, dins venv):
    python scripts/ingest.py                      # tot el corpus/ segons settings
    python scripts/ingest.py --max-files 5        # prova: només 5 fitxers
    python scripts/ingest.py --corpus-dir /ruta   # un altre directori
    python scripts/ingest.py --reset-done         # reindexar des de zero
"""
from __future__ import annotations
import argparse
import json
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import Settings, get_settings
from app.domain.caveats import classify
from app.domain.models import Chunk
from app.infrastructure.chunk_store import ChunkStore
from app.infrastructure.embedder import SentenceTransformersEmbedder
from app.infrastructure.vector_db import build_vector_db

CHUNK_SIZE = 1500
CHUNK_OVERLAP = 300


def load_aliases(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def author_alias_str(author: str, aliases: dict) -> str:
    """Noms de l'autor en tots els idiomes disponibles, units per ' / '."""
    a = aliases.get(author, {})
    if isinstance(a, dict):
        names = list(dict.fromkeys(v.strip() for v in a.values() if v and v.strip()))
    else:
        names = [author]
    return " / ".join(names) if names else author


def parse_header(text: str) -> tuple[dict, str]:
    """Extreu metadades de la capçalera SIGPHI si existeix; retorna (meta, body)."""
    m = re.match(r"^=====[^\n]*=====\n(.*?)\n=+\n+", text, re.S)
    if not m:
        return {}, text
    meta = {}
    for line in m.group(1).splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            meta[k.strip().lower()] = v.strip()
    return meta, text[m.end() :]


# Àncora de la llicència Perseus: tanca el bloc de crèdits editorials inicial
# (títol "Machine readable text", noms del traductor/projecte, Annenberg/Tufts i,
# en algun cas, una plantilla EQUIVOCADA -p. ex. crèdits de Sòfocles en un text de
# Plató-). Sempre és DINS els crèdits inicials, abans del cos de l'obra.
_PERSEUS_LICENSE_ANCHOR = "You offer Perseus any modifications you make."

# Patró CVS/RCS $Log: blocks (historial de revisió del XML de Perseus Digital Library).
# Formats: "$Log: fitxer.xml,v $\nRevision X.Y  YYYY/MM/DD...\n...\n$\n"
# Aquests blocs estan escampats pel cos del text (no al front-matter) i generen
# soroll massiu als embeddings: dates, usernames, missatges de commit en anglès.
_CVS_LOG_RE = re.compile(
    r"\$Log:[^\n]*\n"        # línia inicial: $Log: fitxer.xml,v $
    r"(?:.*\n)*?"            # qualsevol nombre de línies (lazy)
    r"\$[ \t]*\n",           # línia final: $ solitari
    re.MULTILINE,
)


def _strip_cvs_logs(text: str) -> str:
    """Elimina blocs $Log: ... $ d'historial CVS/RCS (artefactes de Perseus XML)."""
    cleaned = _CVS_LOG_RE.sub("", text)
    # Neteja línies soltes que puguin quedar: "$ " o "$\n" sense context de bloc
    cleaned = re.sub(r"^\$[ \t]*$", "", cleaned, flags=re.MULTILINE)
    # Col·lapsa triples (o més) línies en blanc a doble salt de línia
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned


def strip_perseus_frontmatter(body: str) -> str:
    """Treu el front-matter de crèdits de Perseus + blocs CVS $Log: del cos.

    L'àncora de llicència viu sempre als crèdits inicials (mai dins l'obra), de
    manera que tallar-ne el principi és segur. Els blocs $Log: CVS estan escampats
    pel cos i generen soroll als embeddings; _strip_cvs_logs els elimina. Si no hi ha
    àncora (text no-Perseus), s'aplica igualment el strip CVS per si de cas. Idempotent."""
    idx = body.find(_PERSEUS_LICENSE_ANCHOR)
    if idx != -1:
        body = body[idx + len(_PERSEUS_LICENSE_ANCHOR):].lstrip("\n").lstrip()
    return _strip_cvs_logs(body)


def split_text(text: str, size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[str]:
    """Parteix el text. Usa RecursiveCharacterTextSplitter si està disponible;
    si no, fallback per longitud amb overlap."""
    try:
        from langchain_text_splitters import RecursiveCharacterTextSplitter

        sp = RecursiveCharacterTextSplitter(chunk_size=size, chunk_overlap=overlap)
        return [c for c in sp.split_text(text) if c.strip()]
    except Exception:
        text = text.strip()
        out, start = [], 0
        step = max(1, size - overlap)
        while start < len(text):
            out.append(text[start : start + size])
            start += step
        return [c for c in out if c.strip()]


def file_metadata(path: Path, meta: dict) -> dict:
    author = meta.get("author") or "Unknown"
    work = meta.get("work") or re.sub(r"\.txt$", "", path.name).replace("_", " ")
    language = meta.get("language", "English")
    completeness = meta.get("completeness")
    authorship = meta.get("authorship")
    note = meta.get("note")
    if not (completeness and authorship and note):
        completeness, authorship, note = classify(author, work)
    return {
        "author": author,
        "work": work,
        "language": language,
        "completeness": completeness,
        "authorship": authorship,
        "note": note,
    }


def _mark_done(done_log: Path, name: str) -> None:
    with done_log.open("a", encoding="utf-8") as fh:
        fh.write(name + "\n")


def run_ingest(
    settings: Settings,
    corpus_dir: str | Path,
    batch_size: int | None = None,
    max_files: int | None = None,
    reset_done: bool = False,
) -> int:
    corpus_dir = Path(corpus_dir)
    txt_files = sorted(corpus_dir.glob("*.txt"))
    if not txt_files:
        print(f"No s'han trobat fitxers .txt a {corpus_dir}")
        return 0

    # core_list.txt opcional (mode nucli curat)
    core_path = corpus_dir.parent / "core_list.txt"
    if core_path.exists():
        core = {
            l.strip()
            for l in core_path.read_text(encoding="utf-8").splitlines()
            if l.strip()
        }
        txt_files = [f for f in txt_files if f.name in core]
        print(f">>> MODE NUCLI CURAT: {len(txt_files)} fitxers (de core_list.txt)")

    done_log = Path(settings.chunk_store_path).parent / "ingest_done.txt"
    done_log.parent.mkdir(parents=True, exist_ok=True)
    if reset_done and done_log.exists():
        done_log.unlink()
    done = (
        set(done_log.read_text(encoding="utf-8").splitlines())
        if done_log.exists()
        else set()
    )
    pending = [p for p in txt_files if p.name not in done]
    if max_files:
        pending = pending[:max_files]
    print(f"Fitxers: {len(txt_files)} | ja fets: {len(done)} | aquesta passada: {len(pending)}")
    if not pending:
        print("Tot indexat. Res a fer.")
        return 0

    aliases = load_aliases(Path(settings.aliases_path))
    batch_size = batch_size or settings.ingest_batch_size

    print(f"Carregant embedder ({settings.embed_model})...")
    embedder = SentenceTransformersEmbedder(settings.embed_model)
    chunk_store = ChunkStore(settings.chunk_store_path)
    vector_db = build_vector_db(settings, chunk_store=chunk_store)
    vector_db.initialize_index(embedder.dimension)

    total = 0
    t0 = time.time()
    for i, path in enumerate(pending, 1):
        try:
            raw = path.read_text(encoding="utf-8")
            meta, body = parse_header(raw)
            body = strip_perseus_frontmatter(body)  # treu crèdits editorials Perseus (no-op si no n'hi ha)
            md = file_metadata(path, meta)
            pieces = split_text(body)
            if not pieces:
                _mark_done(done_log, path.name)
                continue

            prefix = f"{author_alias_str(md['author'], aliases)} — {md['work']}:"
            chunks: list[Chunk] = []
            embed_texts: list[str] = []
            for j, piece in enumerate(pieces):
                chunks.append(
                    Chunk(
                        chunk_id=f"{path.name}#{j}",
                        text=piece,  # NET (es guarda i es mostra a l'LLM)
                        author=md["author"],
                        work=md["work"],
                        language=md["language"],
                        completeness=md["completeness"],
                        authorship=md["authorship"],
                        note=md["note"],
                    )
                )
                embed_texts.append(f"{prefix}\n{piece}")  # AMB prefix (per l'embedding)

            for k in range(0, len(chunks), batch_size):
                cbatch = chunks[k : k + batch_size]
                tbatch = embed_texts[k : k + batch_size]
                vecs = embedder.embed_passages(tbatch)
                vector_db.upsert_batches(cbatch, vecs, batch_size=batch_size)

            total += len(chunks)
            _mark_done(done_log, path.name)
            el = time.time() - t0
            rate = total / el if el else 0
            print(
                f"[{i}/{len(pending)}] {path.name[:50]:50} "
                f"+{len(chunks):4} | acum {total:6} | {rate:4.0f} ch/s"
            )
        except Exception as e:
            print(f"[{i}/{len(pending)}] ERROR {path.name}: {e}")

    chunk_store.close()
    print(f"\nFet. Chunks indexats aquesta passada: {total}")
    return total


def main() -> None:
    root = Path(__file__).resolve().parent.parent
    ap = argparse.ArgumentParser(description="Ingest del corpus SigPhi")
    ap.add_argument("--corpus-dir", default=str(root / "corpus"))
    ap.add_argument("--max-files", type=int, default=None)
    ap.add_argument("--batch-size", type=int, default=None)
    ap.add_argument("--reset-done", action="store_true")
    args = ap.parse_args()
    run_ingest(
        get_settings(),
        args.corpus_dir,
        batch_size=args.batch_size,
        max_files=args.max_files,
        reset_done=args.reset_done,
    )


if __name__ == "__main__":
    main()
