"""Re-neteja IN-PLACE els textos OCR del Lot 1 amb el clean_ocr arreglat de
download_archive.py.

A diferència d'esborrar+re-baixar (que depèn d'archive.org i pot saltar el fitxer
si encara existeix), aquí:
  1) torna a aplicar clean_ocr() AL COS del .txt ja descarregat (treu l'avís d'IA,
     boilerplate de Google, línies-escombraria) i el reescriu amb la mateixa
     capçalera SIGPHI -> NO depèn de tornar a baixar res;
  2) esborra els chunks vells de Qdrant+SQLite (perquè no quedin orfes);
  3) treu el fitxer de ingest_done.txt perquè add_sacred.sh el re-ingesti net.
Imprimeix què fa amb cada fitxer (incloent quants avisos quedaven abans/després).

Ús (al VPS, dins venv):  VECTOR_DB_TYPE=qdrant python scripts/reclean_ocr.py
(Normalment es crida des de deploy/refresh_and_add.sh.)
"""
from __future__ import annotations
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import get_settings
from app.infrastructure.chunk_store import ChunkStore
from app.infrastructure.vector_db import build_vector_db
import download_archive as da  # reutilitza el clean_ocr ARREGLAT (mateix directori)

# Capçalera SIGPHI: "=====SIGPHI=====\n ... \n=====\n\n"
_HEADER_RE = re.compile(r"\A(=====[^\n]*=====\n.*?\n=+\n+)", re.S)

# (autor exacte, fragment_del_titol, nom_del_fitxer a corpus/)
OCR = [
    ("Karl Marx", "Capital, Vol. I", "Karl_Marx__Capital_Vol1_Moore_Aveling_en.txt"),
    ("Aristotle", "Rhetoric (Treatise", "Aristotle__Rhetoric_Buckley_en.txt"),
    ("Cicero", "De Oratore (On Oratory", "Cicero__De_Oratore_Watson_en.txt"),
]


def _noise_count(text: str) -> int:
    return (text.count("Digitized by") + text.count("funding from")
            + text.count("Internet Archive"))


def main() -> None:
    s = get_settings()
    cs = ChunkStore(s.chunk_store_path)
    vdb = build_vector_db(s, chunk_store=cs)
    corpus = Path(__file__).resolve().parent.parent / "corpus"
    done = Path(s.chunk_store_path).parent / "ingest_done.txt"
    done_lines = done.read_text(encoding="utf-8").splitlines() if done.exists() else []
    print(f"[reclean] corpus={corpus} | ingest_done={done} (existeix={done.exists()})")

    for author, frag, fname in OCR:
        # 1) esborra els chunks vells de la BD (Qdrant + SQLite)
        deleted = 0
        for work in cs.find_works(author, frag):
            ids = cs.chunk_ids_of(author, work)
            if ids:
                vdb.delete_chunk_ids(ids)
                cs.delete_ids(ids)
                deleted += len(ids)
        print(f"[reclean] {author} / '{frag}': {deleted} chunks esborrats de la BD")

        # 2) re-neteja el .txt IN-PLACE (no depèn de re-baixar)
        path = corpus / fname
        if path.exists():
            raw = path.read_text(encoding="utf-8")
            m = _HEADER_RE.match(raw)
            header, body = (m.group(1), raw[m.end():]) if m else ("", raw)
            before, cleaned = _noise_count(body), da.clean_ocr(body)
            after = _noise_count(cleaned)
            path.write_text(header + cleaned + "\n", encoding="utf-8")
            print(f"[reclean]   {fname}: re-netejat in-place "
                  f"({len(body)}->{len(cleaned)} car.; avisos {before}->{after})")
        else:
            print(f"[reclean]   {fname}: NO existeix -> es re-baixarà net")

        # 3) treu de ingest_done perquè es re-ingesti
        done_lines = [l for l in done_lines if l.strip() != fname]

    cs.close()
    if done.exists():
        done.write_text("\n".join(done_lines) + ("\n" if done_lines else ""), encoding="utf-8")
    print("[reclean] Fet. add_sacred.sh re-ingestarà els .txt re-netejats.")


if __name__ == "__main__":
    main()
