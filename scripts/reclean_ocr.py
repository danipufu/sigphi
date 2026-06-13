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
        path = corpus / fname
        if not path.exists():
            # No hi és (esborrat): treu de ingest_done perquè es baixi+ingesti net.
            print(f"[reclean]   {fname}: NO existeix -> es baixarà net")
            done_lines = [l for l in done_lines if l.strip() != fname]
            continue

        raw = path.read_text(encoding="utf-8")
        m = _HEADER_RE.match(raw)
        header, body = (m.group(1), raw[m.end():]) if m else ("", raw)
        before = _noise_count(body)

        # IDEMPOTENT: si ja està net, no toquem res (ni BD ni ingest_done) -> no es
        # re-ingesta. Així es pot repetir refresh_and_add.sh sense feina redundant.
        if before == 0:
            print(f"[reclean]   {fname}: ja net -> res a fer (salto)")
            continue

        # Encara brut: esborra els chunks vells de la BD, re-neteja in-place i
        # reseteja ingest_done perquè es re-ingesti net.
        deleted = 0
        for work in cs.find_works(author, frag):
            ids = cs.chunk_ids_of(author, work)
            if ids:
                vdb.delete_chunk_ids(ids)
                cs.delete_ids(ids)
                deleted += len(ids)
        cleaned = da.clean_ocr(body)
        path.write_text(header + cleaned + "\n", encoding="utf-8")
        done_lines = [l for l in done_lines if l.strip() != fname]
        print(f"[reclean]   {fname}: re-netejat ({deleted} chunks BD esborrats; "
              f"avisos {before}->{_noise_count(cleaned)})")

    cs.close()
    if done.exists():
        done.write_text("\n".join(done_lines) + ("\n" if done_lines else ""), encoding="utf-8")
    print("[reclean] Fet. add_sacred.sh re-ingestarà els .txt re-netejats.")


if __name__ == "__main__":
    main()
