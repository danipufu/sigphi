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

    # --- Lot 6 (QC del lot Perseus: TITOL != CONTINGUT, verificat per hash/keywords) ---
    # El lot "Perseus" (obres amb sufix " EN"/" LA"/" GR") tenia 5 fitxers amb el
    # contingut equivocat. La resta de Perseus (Phaedo EN, Symposium, De Officiis,
    # Metaphysics, Politics, Lucretius...) s'ha verificat correcta i es conserva.
    #
    # Plato "Apology EN": el fitxer es l'ELECTRA DE SOFOCLES (font XML soph.el_eng;
    # 184 'electra', 120 'orestes', 0 'meletus'). Conservem "Apology" i "Apology,
    # Crito, and Phaedo of Socrates" (l'Apologia real, neta):
    ("Plato", "Apology EN"),
    # Cicero "Tusculan Disputations EN": text LLATI amb aparat critic ("ita in
    # Gertz", "si Hense; sic MSS."), no angles. Conservem "Cicero's Tusculan
    # Disputations" (Yonge, angles net) i el bundle Academic Questions:
    ("Cicero", "Tusculan Disputations EN"),
    # Cicero "De Natura Deorum EN": cos BYTE-IDENTIC a "Tusculan Disputations EN"
    # (duplicat mal etiquetat, no es De Natura Deorum). El De Natura Deorum real ja
    # hi es dins "Cicero's Tusculan Disputations" (bundle Yonge que inclou "The
    # Nature of the Gods"):
    ("Cicero", "De Natura Deorum EN"),
    # Seneca "Epistles EN": text LLATI (Epistulae Morales) amb aparat critic, no
    # angles. Es reemplaca per "Moral Letters to Lucilius" (Gummere, Wikisource):
    ("Seneca", "Epistles EN"),
    # Seneca "Epistles LA": el fitxer es una introduccio ANGLESA sobre HIPOCRATES
    # (22 'hippocrates', ~16 KB), no les cartes llatines de Seneca:
    ("Seneca", "Epistles LA"),

    # --- Lot 7 (escaneig QC de tot el corpus: fitxers trencats; TITOL != CONTINGUT,
    # brossa OCR o stubs-index. Tots tenen copia neta tret de Sextus, verificat) ---
    # Augustine "Confessions EN" i "City of God EN": el cos es de CLAUDIA (poeta
    # llati: "Claudianus... In Eutropium" / "Panegyricus de tertio consulatu"), no
    # d'Agusti. Es conserven "The Confessions of St. Augustine" i "The City of God,
    # Volume I/II" (les versions angleses reals):
    ("Augustine", "Confessions EN"),
    ("Augustine", "City of God EN"),
    # Plotinus: edicio llatina escanejada amb OCR il·legible ("plotina platonicorum
    # facile coryphzi opervm philosophicorym..."), 2912 chunks de soroll. Es
    # conserven "Plotinos Complete Works v.1-4" i "Select Works of Plotinus":
    ("Plotinus", "Operum philosophicorum"),
    # Sextus Empiricus: edicio grega/llatina escanejada, OCR il·legible (2924 chunks
    # de soroll). UNICA copia -> queda forat (cal reemplacar per Bury, p. ex.):
    ("Sextus Empiricus", "Sexti Empirici opera"),
    # Thomas Aquinas "Summa Theologiae": nomes un INDEX (1.8 KB: "index *prooemium
    # *quaestio i..."), no la Summa. Es conserva "Summa Theologica, Part I-III":
    ("Thomas Aquinas", "Summa Theologiae"),
    # Aristotle "Organon": pagina-INDEX de navegacio (2 KB), no el text. Es
    # conserven els components ("The Categories", "Posterior Analytics"...):
    ("Aristotle", "Organon"),
    # Mencius "Chinese literature Comprising...": antologia multi-autor (mateixa que
    # ja es va treure de Confucius). Es conserva "孟子" (el Menci real en xines):
    ("Mencius", "Chinese literature Comprising"),

    # --- Lot 8 (trobat per la bateria de diagnostic RAG) ---
    # Spinoza "The Philosophy of Spinoza": edicio de Joseph Ratner (1927) que treu
    # l'Etica de la FORMA GEOMETRICA i la reescriu per al "lector profa" -> reelaboracio
    # EDITORIAL, no el text primari. Redundant: hi ha l'"Ethics" real (+ Parts 1-5),
    # el "Theological-Political Treatise", "On the Improvement of the Understanding", etc.
    ("Spinoza", "The Philosophy of Spinoza"),
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
