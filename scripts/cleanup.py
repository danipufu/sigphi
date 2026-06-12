"""Elimina de la BD (ChunkStore SQLite + Qdrant) obres/autors mal classificats de la
importacio inicial (col·lisions de noms, fonts secundaries, junk). NO re-embeggeix res:
nomes esborra els chunks afectats, aixi que es rapid i barat.

SEGURETAT: dry-run per defecte (nomes mostra que esborraria). Cal --apply per esborrar.
El servei pot seguir actiu (Qdrant i SQLite-WAL admeten esborrats concurrents).

Us (al VPS, dins venv):
    VECTOR_DB_TYPE=qdrant python scripts/cleanup.py          # dry-run
    VECTOR_DB_TYPE=qdrant python scripts/cleanup.py --apply  # esborra
"""
from __future__ import annotations
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import get_settings
from app.infrastructure.chunk_store import ChunkStore
from app.infrastructure.vector_db import build_vector_db

# Autors sencers a eliminar (tot l'autor es equivocat o junk).
REMOVE_AUTHORS = [
    "Hildegard of Bingen",  # = Hildegarde HAWTHORNE (Camp Fire Girls / Girls in Bookland)
    "Unknown",              # = Enchiridion d'Epictet duplicat, sense metadades d'autor
]

# Obres concretes a eliminar: (autor, fragment_del_titol). Match per "conte" (LIKE),
# robust a titols truncats. L'autor conserva la resta de les seves obres (correctes).
REMOVE_WORKS_CONTAINS = [
    # Erasmus de Rotterdam te barrejat Erasmus DARWIN:
    ("Erasmus", "Botanic Garden"),
    ("Erasmus", "Zoonomia"),
    ("Erasmus", "Temple of Nature"),
    # John Locke te barrejat el novel·lista W. J. Locke:
    ("Locke", "Beast and Man in India"),
    ("Locke", "Simon the Jester"),
    ("Locke", "golden journey"),
    ("Locke", "Aristide Pujol"),
    ("Locke", "Marcus Ordeyne"),
    ("Locke", "Rough Road"),
    # Henri Bergson te llibres sense relacio (o secundaris sobre ell):
    ("Bergson", "Legend in Japanese"),
    ("Bergson", "Sansons"),
    ("Bergson", "Mohammed"),
    ("Bergson", "trigonom"),
    ("Bergson", "Jewish world"),
    ("Bergson", "Revue de Paris"),
    ("Bergson", "Philosophy of Bergson"),  # de Russell, secundari
]


def main() -> None:
    ap = argparse.ArgumentParser(description="Neteja d'obres mal classificades")
    ap.add_argument("--apply", action="store_true", help="esborra de debo (per defecte: dry-run)")
    args = ap.parse_args()

    s = get_settings()
    cs = ChunkStore(s.chunk_store_path)
    vdb = build_vector_db(s, chunk_store=cs)

    targets: list[tuple[str, list[str]]] = []
    for author in REMOVE_AUTHORS:
        ids = cs.chunk_ids_of(author)
        if ids:
            targets.append((f"[AUTOR SENCER] {author}", ids))
    for author, frag in REMOVE_WORKS_CONTAINS:
        for work in cs.find_works(author, frag):
            ids = cs.chunk_ids_of(author, work)
            if ids:
                targets.append((f"{author} -> {work}", ids))

    total = sum(len(ids) for _, ids in targets)
    print("=== OBRES/AUTORS QUE S'ELIMINARIEN ===")
    for label, ids in targets:
        print(f"  - {label}  ({len(ids)} chunks)")
    print(f"\nTotal: {len(targets)} entrades, {total} chunks.")

    if not args.apply:
        print("\n>>> DRY-RUN: no s'ha esborrat res.")
        print(">>> Si la llista et sembla be, torna a executar amb  --apply  per esborrar.")
        cs.close()
        return

    print("\nEsborrant de Qdrant i ChunkStore...")
    for label, ids in targets:
        vdb.delete_chunk_ids(ids)
        cs.delete_ids(ids)
        print(f"  esborrat: {label}")
    cs.close()
    print(f"\nFet. {total} chunks eliminats. (No cal reiniciar el servei.)")


if __name__ == "__main__":
    main()
