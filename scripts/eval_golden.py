"""Capa 2 del banc de proves: golden-set de qualitat de respostes (EXECUCIÓ SOTA
DEMANDA — cada pregunta gasta 1 crida a Gemini, i la quota gratuïta és de 20/dia).

Passa un conjunt curat de preguntes (eval/golden_set.json) contra el sistema EN VIU
(endpoint GET /api/ask) i les jutja amb REGLES deterministes (sense segon LLM):
comportament esperat (cita / refús de holdings / fora de corpus / refús de consell),
presència o absència de fonts i de suggeriments, idioma, frases obligatòries i fuites
de tags. Les CITES amb localitzador (Book/Chapter/§…) es marquen per a REVISIÓ MANUAL
(no es poden verificar automàticament contra la font).

Ús:
    ASK_API_KEY=... python scripts/eval_golden.py                  # tot el set
    python scripts/eval_golden.py --key XXX --limit 5              # només 5 (quota)
    python scripts/eval_golden.py --key XXX --filter luther,kant   # per id (subcadena)
    python scripts/eval_golden.py --key XXX --base-url http://localhost:8000
"""
from __future__ import annotations
import argparse
import json
import os
import re
import sys
import urllib.parse
import urllib.request
from pathlib import Path

GOLDEN = Path(__file__).resolve().parent.parent / "eval" / "golden_set.json"

_EN_STOP = {"the", "and", "of", "to", "is", "that", "with", "for", "this", "which"}
_LEAKED_TAGS = ("[[NO_SOURCES]]", "[NO_SOURCES]", "[[SUGGESTIONS]]", "[SUGGESTIONS]")
# Localitzadors de cita a verificar a mà (regla 2: mai inventar Book/Chapter/§/vers).
_LOCATOR_RE = re.compile(
    r"\b(?:Book|Llibre|Libro|Chapter|Cap[íi]tol|Cap[íi]tulo|Letter|Carta|Aphorism|"
    r"Aforisme|Aforismo|Section|Secci[óo]n?|Part|Fragment|verse|vers[íi]culo?)\s+"
    r"[\dIVXLC]+|§\s*\d+",
    re.IGNORECASE,
)


def ask(base_url: str, key: str, query: str, timeout: int = 60) -> dict:
    url = f"{base_url.rstrip('/')}/api/ask?" + urllib.parse.urlencode({"q": query, "key": key})
    req = urllib.request.Request(url, headers={"User-Agent": "SigPhi-eval/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def looks_english(text: str) -> bool:
    toks = re.findall(r"[a-zà-ÿ']+", text.lower())
    if len(toks) < 8:
        return False
    hits = sum(1 for t in toks if t in _EN_STOP)
    return hits / len(toks) > 0.10


def judge(item: dict, resp: dict) -> tuple[list[str], list[str], list[str]]:
    """Retorna (fails, warns, reviews) per a un cas."""
    answer = (resp.get("answer") or "").strip()
    sources = resp.get("sources") or []
    suggestions = resp.get("suggestions") or []
    expect = item.get("expect")
    fails: list[str] = []
    warns: list[str] = []
    reviews: list[str] = []

    if not answer:
        fails.append("resposta buida")
    for tag in _LEAKED_TAGS:
        if tag in answer:
            fails.append(f"tag filtrat a la resposta: {tag}")

    # Idioma (heurístic): si s'espera una llengua no-anglesa però la resposta sembla
    # anglesa -> fail (detecta el mode de fallada principal de la regla 7).
    if item.get("lang") in {"ca", "es", "de", "fr", "it"} and looks_english(answer):
        fails.append(f"idioma: sembla anglès però s'esperava {item['lang']}")

    if expect == "cited":
        if not sources:
            fails.append("s'esperaven FONTS i no n'hi ha cap")
        if item.get("expect_suggestions") and not suggestions:
            fails.append("s'esperaven SUGGERIMENTS (regla 21) i no n'hi ha")
        hay = (answer + " " + " ".join(sources)).lower()
        for m in item.get("must_mention", []):
            if m.lower() not in hay:
                fails.append(f"no esmenta l'autor/obra esperat: {m}")
        for m in item.get("must_include", []):
            if m.lower() not in answer.lower():
                fails.append(f"falta el text obligatori: {m!r}")

    elif expect == "no_sources":
        if sources:
            fails.append(f"NO s'esperaven fonts però n'hi ha {len(sources)}")
        if suggestions:
            fails.append("NO s'esperaven suggeriments en un cas NO_SOURCES")

    elif expect == "no_suggestions":  # refús de consell (regla 11): pot citar, sense suggeriments
        if suggestions:
            fails.append("refús de consell amb suggeriments (no n'hauria de tenir)")

    # must_include_any aplica a qualsevol expect que el declari
    any_list = item.get("must_include_any")
    if any_list and not any(s.lower() in answer.lower() for s in any_list):
        fails.append(f"cap de les frases esperades: {any_list}")

    # Cites amb localitzador -> revisió manual (no es pot verificar automàticament).
    locs = _LOCATOR_RE.findall(answer)
    if locs:
        reviews.append(f"verifica localitzadors de cita: {', '.join(sorted(set(locs))[:6])}")

    return fails, warns, reviews


def main() -> int:
    ap = argparse.ArgumentParser(description="Golden-set de qualitat (sota demanda)")
    ap.add_argument("--key", default=os.environ.get("ASK_API_KEY", ""))
    ap.add_argument("--base-url", default="https://sigphiai.com")
    ap.add_argument("--limit", type=int, default=None, help="màx. preguntes (estalvi de quota)")
    ap.add_argument("--filter", default="", help="només ids que continguin (coma-separat)")
    args = ap.parse_args()

    try:  # consoles no-UTF8 (p.ex. Windows cp1252) no han de petar amb ✓/accents
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    if not args.key:
        print("ERROR: cal --key o la variable ASK_API_KEY.", file=sys.stderr)
        return 2

    items = json.loads(GOLDEN.read_text(encoding="utf-8"))
    if args.filter:
        subs = [s.strip().lower() for s in args.filter.split(",") if s.strip()]
        items = [it for it in items if any(s in it["id"].lower() for s in subs)]
    if args.limit:
        items = items[: args.limit]

    print(f">>> Golden-set: {len(items)} preguntes contra {args.base_url}\n")
    n_pass = n_fail = 0
    review_all: list[tuple[str, str]] = []
    for it in items:
        try:
            resp = ask(args.base_url, args.key, it["query"])
        except Exception as e:
            print(f"  ✗ {it['id']}: ERROR de crida -> {e}")
            n_fail += 1
            continue
        fails, warns, reviews = judge(it, resp)
        for r in reviews:
            review_all.append((it["id"], r))
        if fails:
            n_fail += 1
            print(f"  ✗ FAIL {it['id']}  ({it['expect']})")
            for f in fails:
                print(f"        - {f}")
        else:
            n_pass += 1
            print(f"  ✓ pass {it['id']}")

    print(f"\n=== {n_pass} PASS / {n_fail} FAIL  (de {len(items)}) ===")
    if review_all:
        print("\n## REVISIÓ MANUAL (cites amb localitzador a verificar contra la font):")
        for cid, r in review_all:
            print(f"  - {cid}: {r}")
    return 1 if n_fail else 0


if __name__ == "__main__":
    raise SystemExit(main())
