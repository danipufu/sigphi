"""Fusiona traduccions PRÒPIES (no font Wikipedia) a app/data/work_titles.json.

Llegeix un JSON d'entrada amb el format {clau_catalec: {codi_idioma: titol, ...}, ...}
i afegeix una entrada nova per cada clau que encara no existeixi al fitxer (no
sobreescriu les ja cobertes per Wikipedia). Ús intern del repàs de traducció manual.

Ús:  python scripts/merge_self_translations.py batch.json
"""
from __future__ import annotations
import json
import sys
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "app" / "data" / "work_titles.json"


def main() -> None:
    batch = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    wt = json.loads(OUT.read_text(encoding="utf-8"))
    covered = {k for e in wt for k in e["keys"]}
    added, skipped = 0, 0
    for key, titles in batch.items():
        if key in covered:
            skipped += 1
            continue
        wt.append({"keys": [key], "titles": titles})
        covered.add(key)
        added += 1
    OUT.write_text(json.dumps(wt, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"Afegides {added} entrades noves ({skipped} ja cobertes, saltades). Total: {len(wt)}")


if __name__ == "__main__":
    main()
