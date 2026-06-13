"""Re-neteja els textos OCR del Lot 1 amb la neteja millorada de download_archive.py.

Esborra cada text OCR de TOTES bandes (Qdrant + SQLite + corpus/*.txt + la seva
línia a ingest_done.txt), de manera que el següent add_sacred.sh el torni a baixar
amb la neteja nova (treu boilerplate de Google/IA + línies-escombraria) i el
re-ingesti net, SENSE deixar chunks orfes de la versió sorollosa.

Ús (al VPS, dins venv):
    VECTOR_DB_TYPE=qdrant python scripts/reclean_ocr.py
(Normalment es crida des de deploy/refresh_and_add.sh.)
"""
from __future__ import annotations
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import get_settings
from app.infrastructure.chunk_store import ChunkStore
from app.infrastructure.vector_db import build_vector_db

# (autor exacte, fragment_del_titol, nom_del_fitxer a corpus/)
OCR = [
    ("Karl Marx", "Capital, Vol. I", "Karl_Marx__Capital_Vol1_Moore_Aveling_en.txt"),
    ("Aristotle", "Rhetoric (Treatise", "Aristotle__Rhetoric_Buckley_en.txt"),
    ("Cicero", "De Oratore (On Oratory", "Cicero__De_Oratore_Watson_en.txt"),
]


def main() -> None:
    s = get_settings()
    cs = ChunkStore(s.chunk_store_path)
    vdb = build_vector_db(s, chunk_store=cs)
    corpus = Path(__file__).resolve().parent.parent / "corpus"
    done = Path(s.chunk_store_path).parent / "ingest_done.txt"
    done_lines = done.read_text(encoding="utf-8").splitlines() if done.exists() else []

    for author, frag, fname in OCR:
        for work in cs.find_works(author, frag):
            ids = cs.chunk_ids_of(author, work)
            if ids:
                vdb.delete_chunk_ids(ids)
                cs.delete_ids(ids)
                print(f"  BD esborrada: {author} -> {work} ({len(ids)} chunks)")
        (corpus / fname).unlink(missing_ok=True)
        done_lines = [l for l in done_lines if l.strip() != fname]
        print(f"  fitxer + ingest_done reset: {fname}")

    cs.close()
    if done.exists():
        done.write_text("\n".join(done_lines) + ("\n" if done_lines else ""), encoding="utf-8")
    print("\nFet. Ara add_sacred.sh els re-baixarà nets i els re-ingestarà.")


if __name__ == "__main__":
    main()
