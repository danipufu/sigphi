"""Força la RE-INGESTA (re-embedding) de fitxers concrets del corpus.

Quan una ingesta queda a mitges —el text entra a SQLite però els vectors a Qdrant
no (p. ex. un pic de memòria amb un llibre molt gros)— el catàleg veu l'obra però
la cerca semàntica no la troba mai. Aquest script treu els fitxers de
`ingest_done.txt` perquè el següent `ingest.py` els torni a processar: com que el
chunk_id és determinista (`{fitxer}#{n}`), el re-embedding SOBREESCRIU els vectors
trencats (INSERT OR REPLACE a SQLite + upsert a Qdrant), sense duplicats.

Ús (al VPS, dins venv):  VECTOR_DB_TYPE=qdrant python scripts/reembed.py
(Normalment des de deploy/reembed_vol3.sh, amb el servei aturat i swap actiu.)
"""
from __future__ import annotations
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import get_settings

# Fitxers a re-embeggear (es treuen de ingest_done; el .txt ha d'existir a corpus/).
FILES = [
    "Karl_Marx__Capital_Vol3_Untermann_en.txt",
]


def main() -> None:
    s = get_settings()
    done = Path(s.chunk_store_path).parent / "ingest_done.txt"
    if not done.exists():
        print(f"[reembed] No existeix {done} -> res a fer.")
        return
    lines = done.read_text(encoding="utf-8").splitlines()
    targets = set(FILES)
    kept = [l for l in lines if l.strip() not in targets]
    removed = len(lines) - len(kept)
    done.write_text("\n".join(kept) + ("\n" if kept else ""), encoding="utf-8")
    for f in FILES:
        print(f"[reembed]   tret de ingest_done: {f}")
    print(f"[reembed] Fet ({removed} línies tretes). El proper ingest.py els "
          "re-processarà i el re-embedding sobreescriurà els vectors trencats.")


if __name__ == "__main__":
    main()
