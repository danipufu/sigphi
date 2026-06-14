"""Desduplica obres amb CONTINGUT IDENTIC dins un mateix autor.

Molts textos es van baixar dues vegades amb dos convenis de nom (p. ex.
"X (French)" i "X by <Autor>") i totes dues versions es van ingestar -> el mateix
passatge surt dues vegades al retrieval (malgasta slots del top_k i redueix la
diversitat). Aqui agrupem les obres de cada autor pel HASH del seu text complet
(concatenat en ordre de chunk_id); per a cada grup amb >1 obra idEntica, en
conservem UNA (l'etiqueta mes curta/neta) i esborrem la resta.

SEGUR per construccio:
  - nomEs agrupa obres del MATEIX autor (no toca co-autories com el Manifest);
  - nomEs esborra obres el text de les quals Es BYTE-IDENTIC a una que es conserva;
  - mai deixa zero copies (sempre conserva una per grup);
  - dry-run per defecte (cal --apply per esborrar). NO re-embeggeix.

Us (al VPS, dins venv):
    VECTOR_DB_TYPE=qdrant python scripts/dedup.py          # dry-run
    VECTOR_DB_TYPE=qdrant python scripts/dedup.py --apply  # esborra els duplicats
"""
from __future__ import annotations
import argparse
import hashlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import get_settings
from app.infrastructure.chunk_store import ChunkStore
from app.infrastructure.vector_db import build_vector_db


def _id_sort_key(chunk_id: str):
    """Ordena 'fitxer.txt#3' < 'fitxer.txt#12' (numeric, no lexicografic)."""
    base, _, num = chunk_id.rpartition("#")
    try:
        return (base, int(num))
    except ValueError:
        return (base, 0)


def work_fingerprint(cs: ChunkStore, author: str, work: str) -> tuple[str, int]:
    """(md5 del text complet de l'obra, nombre de chunks)."""
    ids = cs.chunk_ids_of(author, work)
    chunks = cs.get_by_ids(ids)
    h = hashlib.md5()
    for cid in sorted(ids, key=_id_sort_key):
        c = chunks.get(cid)
        if c is not None:
            h.update(c.text.encode("utf-8", "replace"))
    return h.hexdigest(), len(ids)


def main() -> None:
    ap = argparse.ArgumentParser(description="Desduplicacio d'obres identiques per autor")
    ap.add_argument("--apply", action="store_true", help="esborra de debo (per defecte: dry-run)")
    args = ap.parse_args()

    s = get_settings()
    cs = ChunkStore(s.chunk_store_path)
    vdb = build_vector_db(s, chunk_store=cs)

    # (autor, hash) -> [(work, nchunks)]
    groups: dict[tuple[str, str], list[tuple[str, int]]] = {}
    for entry in cs.catalog():
        author = entry["author"]
        for work in entry["works"]:
            h, n = work_fingerprint(cs, author, work)
            if n == 0:
                continue
            groups.setdefault((author, h), []).append((work, n))

    # Per a cada grup amb duplicats: conserva l'etiqueta mes curta, esborra la resta.
    removals: list[tuple[str, str, int]] = []  # (author, work_to_remove, nchunks)
    for (author, _h), works in groups.items():
        if len(works) < 2:
            continue
        works_sorted = sorted(works, key=lambda wn: (len(wn[0]), wn[0]))
        keep = works_sorted[0][0]
        for work, n in works_sorted[1:]:
            removals.append((author, work, n))
        print(f"[{author}] CONSERVA «{keep}»; esborra: "
              + ", ".join(f"«{w}» ({n})" for w, n in works_sorted[1:]))

    total = sum(n for _, _, n in removals)
    print(f"\n=== {len(removals)} obres duplicades, {total} chunks a esborrar ===")

    if not args.apply:
        print(">>> DRY-RUN: no s'ha esborrat res. Repeteix amb --apply per esborrar.")
        cs.close()
        return

    print("\nEsborrant duplicats de Qdrant i ChunkStore...")
    for author, work, _n in removals:
        ids = cs.chunk_ids_of(author, work)
        if ids:
            vdb.delete_chunk_ids(ids)
            cs.delete_ids(ids)
            print(f"  esborrat: [{author}] {work}")
    cs.close()
    print(f"\nFet. {total} chunks duplicats eliminats. (No cal reiniciar el servei.)")


if __name__ == "__main__":
    main()
