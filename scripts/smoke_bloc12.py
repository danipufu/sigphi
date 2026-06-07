"""Smoke test Bloc 12: ingest end-to-end amb mini-corpus temporal + Chroma local.

Crea 2 fitxers .txt amb capçalera SIGPHI, executa run_ingest cap a un Chroma
temporal, i comprova que els chunks s'indexen, es recuperen amb text NET (sense
el prefix d'àlies) i que els caveats es propaguen. No cal Pinecone ni corpus real.

Ús (al VPS, des de l'arrel):  python scripts/smoke_bloc12.py
"""
from __future__ import annotations
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Backend chroma + paths temporals ABANS de carregar settings.
_TMP = Path(tempfile.mkdtemp(prefix="sigphi_ingest_"))
os.environ["VECTOR_DB_TYPE"] = "chroma"
os.environ["CHROMA_DIR"] = str(_TMP / "chroma")
os.environ["CHUNK_STORE_PATH"] = str(_TMP / "chunks.sqlite")

from app.config import get_settings
from app.infrastructure.embedder import SentenceTransformersEmbedder
from app.infrastructure.vector_db.chroma_db import ChromaDB
from scripts.ingest import run_ingest

_EPICTET = """=====SIGPHI=====
author: Epictet
work: Enquiridió
language: ca
completeness: Complete work
authorship: Recorded/compiled by others
note: Epictet no va escriure res; recollit pel deixeble Arrià.
=====
No són les coses les que ens pertorben, sinó els judicis que en fem sobre elles.
Hi ha coses que depenen de nosaltres i coses que no depenen de nosaltres.
"""

_AURELI = """=====SIGPHI=====
author: Marc Aureli
work: Meditacions
language: ca
=====
Tens poder sobre la teva ment, no sobre els fets externs. Adona-te'n i trobaràs força.
"""


def main() -> None:
    corpus = _TMP / "corpus"
    corpus.mkdir(parents=True, exist_ok=True)
    (corpus / "epictetus_enchiridion.txt").write_text(_EPICTET, encoding="utf-8")
    (corpus / "marcus_aurelius_meditations.txt").write_text(_AURELI, encoding="utf-8")

    s = get_settings()
    print("1) Executant ingest sobre el mini-corpus...")
    n = run_ingest(s, corpus)
    assert n > 0, "No s'ha indexat cap chunk!"

    print("2) Consultant el que s'ha indexat...")
    emb = SentenceTransformersEmbedder(s.embed_model)
    db = ChromaDB(persist_dir=Path(os.environ["CHROMA_DIR"]))
    res = db.query_similarity(
        emb.embed_query("Què depèn de nosaltres segons Epictet?"), top_k=3
    )
    for r in res:
        print(f"   {r.score:.3f}  {r.chunk.author} — {r.chunk.work}: {r.chunk.text[:50]}...")

    assert res, "Cap resultat recuperat!"
    top = res[0]
    assert top.chunk.author == "Epictet", "El top-1 hauria de ser Epictet"
    # El text guardat ha de ser NET (sense el prefix d'àlies "Epictet / ... —")
    assert not top.chunk.text.lstrip().startswith("Epictet /"), \
        "El text guardat NO hauria de portar el prefix d'àlies!"
    # El caveat s'ha de propagar (Epictet -> recollit per Arrià)
    assert top.chunk.authorship == "Recorded/compiled by others", \
        "El caveat d'autoria d'Epictet no s'ha propagat"

    print("\n[OK] Bloc 12: ingest resumible + text net + caveats funcionen.")


if __name__ == "__main__":
    main()
