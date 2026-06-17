"""Baixa el Greek New Testament (Nestle 1904, domini públic) des de GitHub
i el converteix en text pla vers a vers amb Unicode grec politònic real.

Nestle 1904 és la base directa del Westcott-Hort 1881 (ambdós domini públic)
i l'edició crítica estàndard disponible en Unicode grec real.

Font: https://github.com/biblicalhumanities/Nestle1904 (CC0)

Ús: python scripts/download_greek_nt.py
"""
from __future__ import annotations

import re
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

CORPUS = Path(__file__).resolve().parent.parent / "corpus"
BASE_URL = "https://raw.githubusercontent.com/biblicalhumanities/Nestle1904/master/xml/"

BOOKS = [
    ("01-matthew.xml",      "Matt",  "Κατὰ Ματθαῖον (Matthew)"),
    ("02-mark.xml",         "Mark",  "Κατὰ Μᾶρκον (Mark)"),
    ("03-luke.xml",         "Luke",  "Κατὰ Λουκᾶν (Luke)"),
    ("04-john.xml",         "John",  "Κατὰ Ἰωάννην (John)"),
    ("05-acts.xml",         "Acts",  "Πράξεις Ἀποστόλων (Acts)"),
    ("06-romans.xml",       "Rom",   "Πρὸς Ῥωμαίους (Romans)"),
    ("07-1corinthians.xml", "1Cor",  "Πρὸς Κορινθίους Αʹ (1 Corinthians)"),
    ("08-2corinthians.xml", "2Cor",  "Πρὸς Κορινθίους Βʹ (2 Corinthians)"),
    ("09-galatians.xml",    "Gal",   "Πρὸς Γαλάτας (Galatians)"),
    ("10-ephesians.xml",    "Eph",   "Πρὸς Ἐφεσίους (Ephesians)"),
    ("11-philippians.xml",  "Phil",  "Πρὸς Φιλιππησίους (Philippians)"),
    ("12-colossians.xml",   "Col",   "Πρὸς Κολοσσαεῖς (Colossians)"),
    ("13-1thessalonians.xml","1Th",  "Πρὸς Θεσσαλονικεῖς Αʹ (1 Thessalonians)"),
    ("14-2thessalonians.xml","2Th",  "Πρὸς Θεσσαλονικεῖς Βʹ (2 Thessalonians)"),
    ("15-1timothy.xml",     "1Tim",  "Πρὸς Τιμόθεον Αʹ (1 Timothy)"),
    ("16-2timothy.xml",     "2Tim",  "Πρὸς Τιμόθεον Βʹ (2 Timothy)"),
    ("17-titus.xml",        "Tit",   "Πρὸς Τίτον (Titus)"),
    ("18-philemon.xml",     "Phlm",  "Πρὸς Φιλήμονα (Philemon)"),
    ("19-hebrews.xml",      "Heb",   "Πρὸς Ἑβραίους (Hebrews)"),
    ("20-james.xml",        "Jas",   "Ἐπιστολὴ Ἰακώβου (James)"),
    ("21-1peter.xml",       "1Pet",  "Πέτρου Αʹ (1 Peter)"),
    ("22-2peter.xml",       "2Pet",  "Πέτρου Βʹ (2 Peter)"),
    ("23-1john.xml",        "1Jn",   "Ἰωάννου Αʹ (1 John)"),
    ("24-2john.xml",        "2Jn",   "Ἰωάννου Βʹ (2 John)"),
    ("25-3john.xml",        "3Jn",   "Ἰωάννου Γʹ (3 John)"),
    ("26-jude.xml",         "Jude",  "Ἐπιστολὴ Ἰούδα (Jude)"),
    ("27-revelation.xml",   "Rev",   "Ἀποκάλυψις Ἰωάννου (Revelation)"),
]

# Punctuation that attaches to the preceding word (no space before).
_ATTACH_BEFORE = set(".,;:·!?—")


def fetch_xml(filename: str) -> str:
    url = BASE_URL + filename
    req = urllib.request.Request(url, headers={"User-Agent": "SigPhi/1.0"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read().decode("utf-8")


def parse_book(xml_text: str, abbrev: str) -> list[str]:
    """Returns lines like 'Matt 1:1 Βίβλος γενέσεως ...'"""
    root = ET.fromstring(xml_text)
    ns = {"": ""}  # no namespace in these files

    lines: list[str] = []
    current_verse: str | None = None
    tokens: list[str] = []   # interleaved words and punctuation

    def flush():
        if current_verse and tokens:
            # Join: punctuation attaches to preceding word.
            parts = [tokens[0]] if tokens else []
            for tok in tokens[1:]:
                if tok in _ATTACH_BEFORE:
                    if parts:
                        parts[-1] += tok
                    else:
                        parts.append(tok)
                else:
                    parts.append(tok)
            # Convert "Book.Chap.Verse" -> "Book Chap:Verse"
            ref = re.sub(r"^(\w+)\.(\d+)\.(\d+)$", r"\1 \2:\3", current_verse)
            lines.append(f"{ref} {' '.join(parts)}")

    def walk(node: ET.Element) -> None:
        nonlocal current_verse, tokens

        tag = node.tag.split("}")[-1]  # strip namespace if any

        if tag == "milestone" and node.get("unit") == "verse":
            flush()
            current_verse = node.get("id", "")
            tokens = []

        elif tag == "w":
            if node.text:
                tokens.append(node.text.strip())

        elif tag == "pc":
            if node.text and node.text.strip() in _ATTACH_BEFORE:
                tokens.append(node.text.strip())

        for child in node:
            walk(child)

    walk(root)
    flush()
    return lines


def main() -> None:
    CORPUS.mkdir(parents=True, exist_ok=True)
    dest = CORPUS / "Bible__Greek_New_Testament_Nestle1904_el.txt"
    if dest.exists():
        print(f"[skip] ja existeix: {dest.name}")
        return

    print("Baixant Greek New Testament (Nestle 1904) des de GitHub (27 fitxers)...")
    all_lines: list[str] = []

    for filename, abbrev, title in BOOKS:
        print(f"  [{filename}]...", end=" ", flush=True)
        try:
            xml_text = fetch_xml(filename)
            lines = parse_book(xml_text, abbrev)
            all_lines.append(f"\n\n{'='*60}\n{title}\n{'='*60}\n")
            all_lines.extend(lines)
            print(f"{len(lines)} versos OK")
        except Exception as e:
            print(f"ERROR: {e}")

    body = "\n".join(all_lines).strip()
    if len(body) < 50_000:
        print(f"AVÍS: text molt curt ({len(body)} car.) — revisa la font")
        return

    header = (
        "=====SIGPHI=====\n"
        "author: Bible\n"
        "work: Greek New Testament (Nestle 1904)\n"
        "language: Greek\n"
        "completeness: Complete work\n"
        "authorship: Anonymous / composite\n"
        "note: Text grec politònic del Nou Testament; edició crítica de Eberhard Nestle "
        "(1904), domini públic, derivada directament del Westcott-Hort 1881. "
        "Font: biblicalhumanities/Nestle1904 (GitHub, CC0). No és una traducció: "
        "és el text grec original amb diacrítics politònics complets.\n"
        "=====\n\n"
    )

    dest.write_text(header + body, encoding="utf-8")
    verse_count = sum(1 for l in all_lines if re.match(r"^\w+ \d+:\d+ ", l))
    print(f"\nOK -> {dest.name} ({len(body)//1024} KB, {verse_count} versos)")
    print("Ara re-ingesta els nous:  bash deploy/run_ingest.sh")


if __name__ == "__main__":
    main()
