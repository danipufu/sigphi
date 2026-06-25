"""Elimina de la BD (ChunkStore SQLite + Qdrant) tots els chunks provinents de
FITXERS concrets del corpus, identificats pel NOM DE FITXER.

Per què existeix (complementa cleanup.py):
    cleanup.py esborra per autor+títol (LIKE, INSENSIBLE a majúscules). Però de
    vegades dues entrades comparteixen títol i només difereixen en majúscules
    ("Creative Evolution" net vs "Creative evolution" = brossa d'OCR) o una és
    prefix de l'altra; el LIKE no les pot separar. Com que el chunk_id és
    `{nom_fitxer}#{n}` (ingest.py), aquí discriminem pel FITXER d'origen, que sí
    és únic. (grep -l, sensible a majúscules, troba el fitxer correcte al disc.)

També treu els fitxers de ingest_done.txt: si el .txt s'ha esborrat del corpus,
una re-ingesta no el recuperarà; si encara hi és, el reprocessarà net.

SEGURETAT: dry-run per defecte. Cal --apply per esborrar.

Ús (al VPS, dins venv, des de l'arrel):
    VECTOR_DB_TYPE=qdrant python scripts/remove_files.py FITXER1.txt FITXER2.txt
    VECTOR_DB_TYPE=qdrant python scripts/remove_files.py --apply FITXER1.txt FITXER2.txt
"""
from __future__ import annotations
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import get_settings
from app.infrastructure.chunk_store import ChunkStore
from app.infrastructure.vector_db import build_vector_db


def main() -> None:
    ap = argparse.ArgumentParser(description="Esborra chunks pel fitxer d'origen")
    ap.add_argument("files", nargs="+", help="noms de fitxer del corpus (p.ex. X.txt)")
    ap.add_argument("--apply", action="store_true", help="esborra de debò (per defecte: dry-run)")
    args = ap.parse_args()

    s = get_settings()
    cs = ChunkStore(s.chunk_store_path)
    vdb = build_vector_db(s, chunk_store=cs)
    done_log = Path(s.chunk_store_path).parent / "ingest_done.txt"

    targets: list[tuple[str, list[str]]] = []
    for fname in args.files:
        ids = cs.chunk_ids_of_file(fname)
        targets.append((fname, ids))

    total = sum(len(ids) for _, ids in targets)
    print("=== CHUNKS QUE S'ELIMINARIEN (per fitxer d'origen) ===")
    for fname, ids in targets:
        flag = "" if ids else "  <-- CAP CHUNK (nom de fitxer correcte?)"
        print(f"  - {fname}: {len(ids)} chunks{flag}")
    print(f"\nTotal: {total} chunks de {len(targets)} fitxers.")

    if not args.apply:
        print("\n>>> DRY-RUN: no s'ha esborrat res. Torna amb --apply per esborrar.")
        cs.close()
        return

    print("\nEsborrant de Qdrant i ChunkStore...")
    for fname, ids in targets:
        if ids:
            vdb.delete_chunk_ids(ids)
            cs.delete_ids(ids)
        print(f"  esborrat: {fname} ({len(ids)} chunks)")

    if done_log.exists():
        drop = set(args.files)
        kept = [
            l for l in done_log.read_text(encoding="utf-8").splitlines()
            if l.strip() and l.strip() not in drop
        ]
        done_log.write_text("\n".join(kept) + ("\n" if kept else ""), encoding="utf-8")
        print(f"  ingest_done.txt: tretes {len(drop)} entrades (es reprocessaran si el .txt hi és)")

    cs.close()
    print(f"\nFet. {total} chunks eliminats.")


if __name__ == "__main__":
    main()
