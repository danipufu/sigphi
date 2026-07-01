"""Genera app/data/work_titles.json: títols d'obra traduïts per idioma.

Font autoritzada: els enllaços interlingües de Wikipedia (el títol de l'article
en cada idioma = el títol publicat real). Cura un mapa obra->article de Wikipedia
(WORKS, a sota) i el script baixa els langlinks en lots (50 títols/crida), els
neteja (treu desambiguadors entre parèntesis) i escriu el JSON. Reexecutable: per
ampliar la cobertura, afegeix entrades a WORKS i torna a córrer.

Ús:  python scripts/build_work_titles.py
Les obres NO presents aquí es mostren en el títol original (fallback a la UI).
"""
from __future__ import annotations
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "app" / "data" / "work_titles.json"
# Idiomes de la UI (en = original; no cal desar-lo).
LANGS = ["ca", "es", "fr", "de", "it", "ru", "zh", "ja", "ar", "hi"]
UA = {"User-Agent": "SigPhi-catalog-builder/1.0 (philosophy RAG; contact danipufu)"}
API = "https://en.wikipedia.org/w/api.php"

# Desambiguador final entre parèntesis (llatins o de doble amplada CJK): " (Plató)",
# " (dialogue)", " (книга)", "（対話篇）"... -> es treu. Es repeteix per si n'hi ha més d'un.
_DISAMB = re.compile(r"\s*[\(（][^()（）]*[\)）]\s*$")


def clean(t: str) -> str:
    prev = None
    while prev != t:
        prev = t
        t = _DISAMB.sub("", t).strip()
    return t


def _get(url: str) -> dict:
    """GET amb reintents i espera creixent davant 429 (límit de ritme de Wikipedia)."""
    for attempt in range(5):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code == 429 and attempt < 4:
                time.sleep(5 * (attempt + 1))
                continue
            raise


# (article de Wikipedia EN, [títols EXACTES tal com són a la nostra BD]).
# Regla: obres SENCERES; les parts/volums solts es deixen en l'original (fallback).
WORKS: list[tuple[str, list[str]]] = [
    # --- Plató ---
    ("Republic (Plato)", ["The Republic", "The Republic of Plato", "Republic GR"]),
    ("Apology (Plato)", ["Apology", "Apology EN"]),
    ("Charmides (dialogue)", ["Charmides"]),
    ("Cratylus (dialogue)", ["Cratylus"]),
    ("Critias (dialogue)", ["Critias"]),
    ("Euthydemus (dialogue)", ["Euthydemus"]),
    ("Euthyphro", ["Euthyphro"]),
    ("Gorgias (dialogue)", ["Gorgias"]),
    ("Ion (dialogue)", ["Ion"]),
    ("Laches (dialogue)", ["Laches"]),
    ("Laws (dialogue)", ["Laws"]),
    ("Hippias Minor", ["Lesser Hippias"]),
    ("Lysis (dialogue)", ["Lysis"]),
    ("Menexenus (dialogue)", ["Menexenus"]),
    ("Meno", ["Meno"]),
    ("Parmenides (dialogue)", ["Parmenides"]),
    ("Phaedo", ["Phaedo", "Phaedo EN"]),
    ("Phaedrus (dialogue)", ["Phaedrus"]),
    ("Philebus", ["Philebus"]),
    ("Protagoras (dialogue)", ["Protagoras"]),
    ("Sophist (dialogue)", ["Sophist"]),
    ("Statesman (dialogue)", ["Statesman"]),
    ("Symposium (Plato)", ["Symposium", "Symposium EN", "Symposium GR"]),
    ("Theaetetus (dialogue)", ["Theaetetus"]),
    ("Timaeus (dialogue)", ["Timaeus", "Timaeus EN"]),
    # --- Aristòtil ---
    ("Nicomachean Ethics", ["Nicomachean Ethics EN", "The Nicomachean ethics of Aristotle"]),
    ("Politics (Aristotle)", ["Politics EN", "Politics A Treatise on Government"]),
    ("Metaphysics (Aristotle)", ["Metaphysics EN"]),
    ("Poetics (Aristotle)", ["Poetics EN", "The Poetics of Aristotle", "Aristotle on the art of poetry"]),
    ("On the Soul", ["De Anima (On the Soul)", "De Anima EN"]),
    ("Physics (Aristotle)", ["The Physics, Vol. I (Books I-IV)", "The Physics, Vol. II (Books V-VIII)"]),
    ("Categories (Aristotle)", ["The Categories"]),
    ("De Interpretatione", ["On Interpretation (Organon)"]),
    ("Prior Analytics", ["Prior Analytics, Book 1 (Organon)", "Prior Analytics, Book 2 (Organon)"]),
    ("Posterior Analytics", ["Posterior Analytics (Bouchier)"]),
    ("Topics (Aristotle)", ["Topics (Organon)"]),
    ("Sophistical Refutations", ["Sophistical Refutations (Organon)"]),
    ("Rhetoric (Aristotle)", ["Rhetoric (Treatise on Rhetoric)"]),
    ("Constitution of the Athenians", ["The Athenian Constitution"]),
    ("History of Animals", ["Aristotle's History of Animals"]),
    # --- Marc Aureli ---
    ("Meditations", ["Meditations", "The Meditations of the Emperor Marcus Aurelius Antoninus",
                     "Thoughts of Marcus Aurelius Antoninus", "Meditations GR"]),
    # --- Nietzsche ---
    ("Thus Spoke Zarathustra", ["Thus Spake Zarathustra A Book for All and None"]),
    ("Beyond Good and Evil", ["Beyond Good and Evil"]),
    ("On the Genealogy of Morality", ["The Genealogy of Morals"]),
    ("The Antichrist (book)", ["The Antichrist"]),
    ("Ecce Homo (book)", ["Ecce Homo"]),
    ("The Birth of Tragedy", ["The Birth of Tragedy; or, Hellenism and Pessimism"]),
    ("Twilight of the Idols", ["The Twilight of the Idols; or, How to Philosophize with the Hammer. The Antichri"]),
    ("The Will to Power (manuscript)", ["The Will to Power"]),
    ("The Gay Science", ["The Joyful Wisdom (La Gaya Scienza)"]),
    ("Human, All Too Human", ["Human, All-Too-Human A Book for Free Spirits, Part 1",
                              "Human, All-Too-Human A Book for Free Spirits, Part 2"]),
    ("The Case of Wagner", ["The Case of Wagner, Nietzsche Contra Wagner, and Selected Aphorisms."]),
    # --- Kant ---
    ("Critique of Pure Reason", ["The Critique of Pure Reason"]),
    ("Critique of Practical Reason", ["The Critique of Practical Reason", "Critique of Practical Reason"]),
    ("Critique of Judgment", ["Kant's Critique of Judgement"]),
    ("Groundwork of the Metaphysics of Morals", ["Groundwork of the Metaphysics of Morals",
                                                 "Fundamental Principles of the Metaphysic of Morals"]),
    ("Prolegomena to Any Future Metaphysics", ["Kant's Prolegomena to Any Future Metaphysics"]),
    ("Perpetual Peace", ["Perpetual Peace A Philosophical Essay"]),
    ("The Metaphysics of Morals", ["The Metaphysical Elements of Ethics"]),
    ("The Conflict of the Faculties", ["Der Streit der Fakultäten (The Conflict of the Faculties)"]),
    # --- Descartes ---
    ("Discourse on the Method", ["Discourse on the Method of Rightly Conducting One's Reason and of Seeking Truth",
                                 "A Discourse of a Method for the Well Guiding of Reason"]),
    ("Meditations on First Philosophy", ["Six metaphysical meditations"]),
    ("Principles of Philosophy", ["Selections from the Principles of Philosophy"]),
    ("Rules for the Direction of the Mind", ["Rules for the Direction of the Mind"]),
    # --- Spinoza ---
    ("Ethics (Spinoza)", ["Ethics"]),
    ("Political Treatise", ["Tractatus Politicus"]),
    ("Treatise on the Emendation of the Intellect", ["On the Improvement of the Understanding"]),
    # --- Hobbes ---
    ("Leviathan (Hobbes book)", ["Leviathan"]),
    ("De Cive", ["De Cive"]),
    ("Behemoth (book)", ["Behemoth; or, The Long Parliament"]),
    # --- Rousseau ---
    ("The Social Contract", ["Du contrat social (Le contrat social)"]),
    ("Emile, or On Education", ["Emile", "Émile; Or, Concerning Education; Extracts"]),
    ("Discourse on Inequality", ["A Discourse Upon the Origin and the Foundation of the Inequality Among Mankind"]),
    ("Confessions (Rousseau)", ["The Confessions of Jean Jacques Rousseau — Complete"]),
    ("Discourse on the Arts and Sciences", ["Discours sur les sciences et les arts"]),
    ("Reveries of a Solitary Walker", ["Reveries of the Solitary Walker (Fletcher, Routledge)"]),
    ("Julie, or the New Heloise", ["Eloisa or, A series of original letters"]),
    # --- Maquiavel ---
    ("The Prince", ["The Prince"]),
    ("Discourses on Livy", ["Discourses on the First Decade of Titus Livius"]),
    ("Florentine Histories", ["History of Florence and of the Affairs of Italy"]),
    # --- Marx ---
    ("The Communist Manifesto", ["The Communist Manifesto", "Manifesto of the Communist Party"]),
    ("A Contribution to the Critique of Political Economy", ["A Contribution to the Critique of Political Economy"]),
    ("The Eighteenth Brumaire of Louis Napoleon", ["The Eighteenth Brumaire of Louis Bonaparte"]),
    ("Critique of the Gotha Programme", ["Critique of the Gotha Programme"]),
    ("The Poverty of Philosophy", ["Misère de la philosophie (The Poverty of Philosophy)"]),
    ("Theses on Feuerbach", ["Theses on Feuerbach"]),
    ("Value, Price and Profit", ["Wages, Price and Profit"]),
    # --- Mill ---
    ("On Liberty", ["On Liberty"]),
    ("Utilitarianism (book)", ["Utilitarianism"]),
    ("The Subjection of Women", ["The Subjection of Women"]),
    ("A System of Logic", ["A System of Logic, Ratiocinative and Inductive"]),
    ("Principles of Political Economy", ["Principles of Political Economy"]),
    ("Considerations on Representative Government", ["Considerations on Representative Government"]),
    # --- Agustí ---
    ("Confessions (Augustine)", ["Confessions EN", "The Confessions of St. Augustine"]),
    ("The City of God", ["City of God EN"]),
    ("On the Trinity (Augustine)", ["On the Trinity (De Trinitate)"]),
    # --- Aquino ---
    ("Summa contra Gentiles", ["Of God and His Creatures (Summa Contra Gentiles)"]),
    # --- Confuci ---
    ("Analects", ["The Analects of Confucius (from the Chinese Classics)", "The Sayings of Confucius"]),
    # --- Adam Smith ---
    ("The Wealth of Nations", ["An Inquiry into the Nature and Causes of the Wealth of Nations"]),
    ("The Theory of Moral Sentiments", ["The Theory of Moral Sentiments"]),
    # --- Epictet ---
    ("Enchiridion of Epictetus", ["The Enchiridion"]),
    # --- Francis Bacon ---
    ("New Atlantis", ["New Atlantis", "The New Atlantis"]),
    ("Novum Organum", ["Novum organum or, True suggestions for the interpretation of nature"]),
    ("The Advancement of Learning", ["The Advancement of Learning"]),
    ("Essays (Francis Bacon)", ["The Essays or Counsels, Civil and Moral", "Bacon's Essays, and Wisdom of the Ancients"]),
    # --- Hegel ---
    ("The Phenomenology of Spirit", ["The Phenomenology of Mind (Baillie)", "Phänomenologie des Geistes (German)"]),
    ("Elements of the Philosophy of Right", ["Philosophy of Right (Grundlinien der Philosophie des Rechts)"]),
    ("Science of Logic", ["Wissenschaft der Logik — Band 1 (German)", "Wissenschaft der Logik — Band 2 (German)"]),
    ("Lectures on the History of Philosophy", ["Hegel's Lectures on the History of Philosophy Volume 1 (of 3)", "Hegel's Lectures on the History of Philosophy Volume 2 (of 3)", "Hegel's Lectures on the History of Philosophy Volume 3 (of 3)"]),
    ("Lectures on Aesthetics", ["The Philosophy of Fine Art, volume 1 (of 4)", "The Philosophy of Fine Art, volume 2 (of 4)", "The Philosophy of Fine Art, volume 3 (of 4)", "The Philosophy of Fine Art, volume 4 (of 4)"]),
    # --- Kierkegaard ---
    ("The Concept of Anxiety", ["the concept of dread"]),
    ("Either/Or", ["EitherOr"]),
    # --- Leibniz ---
    ("Monadology", ["Leibnitz' Monadologie (German)"]),
    ("New Essays on Human Understanding", ["New Essays Concerning Human Understanding"]),
    ("Théodicée", ["Theodicy"]),
    # --- Locke ---
    ("A Letter Concerning Toleration", ["A Letter Concerning Toleration"]),
    ("An Essay Concerning Human Understanding", ["An Essay Concerning Humane Understanding, Volume 1", "An Essay Concerning Humane Understanding, Volume 2"]),
    ("Two Treatises of Government", ["Two Treatises of Government (First and Second)", "Second Treatise of Government"]),
    ("Some Thoughts Concerning Education", ["Some Thoughts Concerning Education (1902)"]),
    # --- Montesquieu ---
    ("The Spirit of Law", ["The Spirit of Laws, Volume 1", "The Spirit of Laws, Volume 2", "Esprit des lois (French)"]),
    ("Persian Letters", ["Persian Letters", "Lettres persanes, tome I (French)", "Lettres persanes, tome II (French)"]),
    # --- Pascal ---
    ("Pensées", ["Pascal's Pensées", "The Thoughts of Blaise Pascal"]),
    ("Lettres provinciales", ["Lettres Provinciales", "The provincial letters of Blaise Pascal A new translation, with historical intro"]),
    # --- Schopenhauer ---
    ("The World as Will and Representation", ["The World as Will and Idea (Vol. 1 of 3)", "The World as Will and Idea (Vol. 2 of 3)", "The World as Will and Idea (Vol. 3 of 3)"]),
    ("On the Fourfold Root of the Principle of Sufficient Reason", ["On the Fourfold Root of the Principle of Sufficient Reason, and On the Will in N"]),
    ("The Art of Being Right", ["The Art of Being Right", "The Art of Controversy"]),
    ("On the Basis of Morality", ["The Basis of Morality"]),
    # --- Thoreau ---
    ("Walden", ["Walden, and On The Duty Of Civil Disobedience"]),
    ("Civil Disobedience (Thoreau)", ["On the Duty of Civil Disobedience"]),
    ("A Week on the Concord and Merrimack Rivers", ["A Week on the Concord and Merrimack Rivers"]),
    ("The Maine Woods", ["The Maine Woods"]),
    ("Cape Cod (book)", ["Cape Cod"]),
    # --- Voltaire ---
    ("Candide", ["Candide", "Candide, ou l'optimisme (French)"]),
    ("Philosophical Dictionary", ["Voltaire's Philosophical Dictionary"]),
    ("Letters on the English", ["Letters on England"]),
    ("Micromégas", ["Micromegas"]),
    ("Zadig", ["Zadig; Or, The Book of Fate"]),
    # --- William James ---
    ("Pragmatism (book)", ["Pragmatism A New Name for Some Old Ways of Thinking"]),
    ("The Varieties of Religious Experience", ["The Varieties of Religious Experience A Study in Human Nature"]),
    ("The Will to Believe", ["The Will to Believe, and Other Essays in Popular Philosophy"]),
    ("The Principles of Psychology", ["The Principles of Psychology, Volume 1 (of 2)", "The Principles of Psychology, Volume 2 (of 2)"]),
]


def fetch_lang(articles: list[str], lang: str) -> dict[str, str]:
    """{article_demanat: titol_net} per a UN idioma (lots de 50). Es filtra per
    lllang -> com a molt 1 langlink per pàgina, així mai es topa amb lllimit."""
    out: dict[str, str] = {}
    for i in range(0, len(articles), 50):
        chunk = articles[i:i + 50]
        params = {
            "action": "query", "prop": "langlinks", "lllang": lang,
            "lllimit": "500", "redirects": "1", "format": "json",
            "titles": "|".join(chunk),
        }
        q = _get(API + "?" + urllib.parse.urlencode(params))["query"]
        norm = {n["from"]: n["to"] for n in q.get("normalized", [])}
        redir = {x["from"]: x["to"] for x in q.get("redirects", [])}
        by = {
            p["title"]: ((p.get("langlinks") or [{}])[0].get("*"))
            for p in q.get("pages", {}).values()
        }
        for a in chunk:
            t = redir.get(norm.get(a, a), norm.get(a, a))
            val = by.get(t)
            if val:
                out[a] = clean(val)
        time.sleep(1.0)
    return out


def main() -> None:
    arts = [a for a, _ in WORKS]
    titles: dict[str, dict[str, str]] = {a: {} for a in arts}
    for lang in LANGS:
        for a, t in fetch_lang(arts, lang).items():
            titles[a][lang] = t
    entries, empty = [], []
    for article, keys in WORKS:
        if titles[article]:
            entries.append({"keys": keys, "titles": titles[article]})
        else:
            empty.append(article)
    OUT.write_text(json.dumps(entries, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    nk = sum(len(e["keys"]) for e in entries)
    print(f"Escrites {len(entries)} obres ({nk} títols-clau) a {OUT.name}.")
    print(f"Mitjana d'idiomes/obra: {sum(len(e['titles']) for e in entries) / max(1, len(entries)):.1f}")
    if empty:
        print(f"SENSE langlinks ({len(empty)}) -> revisar el nom de l'article:")
        for a in empty:
            print(f"  - {a}")


if __name__ == "__main__":
    main()
