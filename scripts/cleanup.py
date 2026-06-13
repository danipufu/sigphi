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
    ("Henri Bergson", "Legend in Japanese"),
    ("Henri Bergson", "Sansons"),
    ("Henri Bergson", "Mohammed"),
    ("Henri Bergson", "trigonom"),
    ("Henri Bergson", "Jewish world"),
    ("Henri Bergson", "Revue de Paris"),
    ("Henri Bergson", "Philosophy of Bergson"),  # de Russell, secundari

    # --- Lot 2 ---
    # Mary Wollstonecraft te barrejats llibres de Mary SHELLEY (la filla) i de Burke:
    ("Mary Wollstonecraft", "Frankenstein"),
    ("Mary Wollstonecraft", "Mathilda"),
    ("Mary Wollstonecraft", "The Last Man"),
    ("Mary Wollstonecraft", "Tales and Stories"),
    ("Mary Wollstonecraft", "Eminent literary and scientific men of Italy"),
    ("Mary Wollstonecraft", "Lives of the most eminent literary and scientific men of France"),
    ("Mary Wollstonecraft", "Reflections on the Revolution in France"),  # de Burke
    # Francis Bacon: llibre de David Francis Bacon (1836):
    ("Francis Bacon", "Lives of the apostles"),
    # Leibniz: una revista:
    ("Leibniz", "Atlantic Monthly"),
    # Pascal: teosofia + secundaries:
    ("Pascal", "Reincarnation"),
    ("Pascal", "Life and Writings of Blaise Pascal"),
    ("Pascal", "Notes de Voltaire"),
    # Karl Marx: pagines-index/brossa de l'scrape (no son textos):
    ("Karl Marx", "MarxEngels Biography"),
    ("Karl Marx", "Archive of eBooks"),
    ("Karl Marx", "Subject Archive"),
    ("Karl Marx", "Lawrence"),
    ("Karl Marx", "worksdateindex"),
    # Fichte: biografia + estudi sobre ell:
    ("Johann Fichte", "Memoir of Johann"),
    ("Johann Fichte", "Philosophy of Fichte in its Relation"),
    # Confucius: biografia:
    ("Confucius", "Life, Labours and Doctrines"),
    # Al-Ghazali: historia de Simon Ockley, no seva:
    ("Al-Ghazali", "History of the Saracens"),
    # Kierkegaard: pagina de navegacio danesa:
    ("Kierkegaard", "Forside"),
    # Plutarch: adaptacio infantil:
    ("Plutarch", "Boys' and Girls'"),

    # --- Lot 3 (tot verificat via /api/sample abans d'afegir-ho) ---
    # Charles Darwin: volums EDITATS per Francis Darwin (biografia + correspondencia
    # amb narrativa de l'editor), no son llibres escrits per Darwin. Es conserven
    # les seves obres propies (Origin, Descent, Voyage, Autobiography, etc.):
    ("Charles Darwin", "Life and Letters of Charles Darwin"),
    ("Charles Darwin", "More Letters of Charles Darwin"),
    ("Charles Darwin", "His Life Told in an Autobiographical Chapter"),
    # Thoreau: pagina-portal de Wikisource de la revista (markup, no text de Thoreau):
    ("Thoreau", "The Atlantic Monthly"),
    # Plutarch: bundle del traductor C. W. Super (Seneca "De Providentia" + Plutarc);
    # el titol no anomena cap dels dos. Ja tenim "on the Delay of the Divine Justice":
    ("Plutarch", "Between Heathenism and Christianity"),
    # Karl Marx: pagines-index / avis de copyright de marxists.org (llistes d'enllacos,
    # no son textos llegibles). Les obres reals de Marx es conserven:
    ("Karl Marx", "Selected Works"),    # "Marx & Engels Selected Works"
    ("Karl Marx", "Collected Works"),   # "Marx and Engels Collected Works"
    ("Karl Marx", "MarxEngels Letters"),
    # Proclus: bundles de Thomas Taylor d'ALTRES autors (Ocellus Lucanus; Sal·lusti
    # "On the Gods and the World"). Es conserven els comentaris i la teologia de Proclus:
    ("Proclus", "Ocellus Lucanus"),
    ("Proclus", "Sallust On the Gods"),
    # Teresa d'Avila: "An Appreciation" d'Alexander Whyte, llibre SOBRE ella (secundari).
    # Es conserva "The Life of St. Teresa of Jesus" (autobiografia seva):
    ("Teresa of Avila", "Santa Teresa An Appreciation"),
    # Emma Goldman: textos d'ALTRES autors mal atribuits + index de revista:
    ("Emma Goldman", "Prison Memoirs of an Anarchist"),   # es d'Alexander Berkman
    ("Emma Goldman", "In Defense of Emma Goldman"),        # es de Voltairine de Cleyre (1894)
    ("Emma Goldman", "Mother Earth"),                      # index/masthead de la revista

    # --- Lot 4 (trobat auditant els 7 autors prolifics; verificat via /api/sample) ---
    # Kant: "Literary and Philosophical Essays" es l'antologia Harvard Classics v32
    # (Montaigne, Lessing, Schiller, Mazzini...), NO una obra de Kant:
    ("Kant", "Literary and Philosophical Essays"),
    # Seneca: dues obres pseudo-senequianes (no son de Seneca):
    ("Seneca", "Epistulae Pauli"),      # correspondencia apocrifa Pau-Seneca (medieval)
    ("Seneca", "Proverbia Senecae"),    # maximes pseudo-senequianes (estil Publili Sir)

    # --- Lot 5 (curacio: traduccions arcaiques, antologies, pseudo-autors) ---
    # Boethius: traduccions arcaiques que foregrounden el traductor (Chaucer en angles
    # mitja, Alfred en angles antic) i que l'embedder mapeja malament; es conserven
    # 3+ Consolacions modernes netes:
    ("Boethius", "Chaucer"),
    ("Boethius", "King Alfred"),
    # Confucius: antologia multi-autor (Confuci + Menci + Shi-King...); ja tenim els Analectes:
    ("Confucius", "Chinese literature Comprising"),
    # Seneca: Octavia es una praetexta pseudo-senequiana (no es seva; ja es dins
    # "The Tragedies of Seneca"):
    ("Seneca", "Octavia"),
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
