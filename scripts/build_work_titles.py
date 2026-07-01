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
# Idiomes d'escriptura no-llatina: un valor en ASCII pur és una fuita (títol anglès/
# llatí per una redirecció al concepte, article inexistent, etc.) -> es descarta.
_NONLATIN = {"ru", "zh", "ja", "ar", "hi"}
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
    ("Either/Or (Kierkegaard)", ["EitherOr"]),
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
    ("Cape Cod (Thoreau)", ["Cape Cod"]),
    # --- Voltaire ---
    ("Candide", ["Candide", "Candide, ou l'optimisme (French)"]),
    ("Philosophical Dictionary", ["Voltaire's Philosophical Dictionary"]),
    ("Letters on the English", ["Letters on England"]),
    ("Micromégas", ["Micromegas"]),
    ("Zadig", ["Zadig; Or, The Book of Fate"]),
    # --- William James ---
    ("Pragmatism: A New Name for Some Old Ways of Thinking", ["Pragmatism A New Name for Some Old Ways of Thinking"]),
    ("The Varieties of Religious Experience", ["The Varieties of Religious Experience A Study in Human Nature"]),
    ("The Will to Believe", ["The Will to Believe, and Other Essays in Popular Philosophy"]),
    ("The Principles of Psychology", ["The Principles of Psychology, Volume 1 (of 2)", "The Principles of Psychology, Volume 2 (of 2)"]),
    # --- Tocqueville ---
    ("Democracy in America", ["Democracy in America — Volume 1", "Democracy in America — Volume 2", "De la Démocratie en Amérique, tome premier", "De la Démocratie en Amérique, tome deuxième", "De la Démocratie en Amérique, tome troisième", "De la Démocratie en Amérique, tome quatrième", "American Institutions and Their Influence"]),
    # --- Anselm ---
    ("Proslogion", ["Proslogium, Monologium, and Cur Deus Homo (Deane)", "Proslogion (Discours sur l'existence de Dieu)"]),
    # --- Boeci ---
    ("The Consolation of Philosophy", ["De consolatione philosophiae (CSEL 67)", "The Consolation Of Philosophy"]),
    # --- Darwin ---
    ("On the Origin of Species", ["On the Origin of Species by Means of Natural Selection", "The Origin of Species by Means of Natural Selection"]),
    ("The Descent of Man, and Selection in Relation to Sex", ["The Descent of Man, and Selection in Relation to Sex"]),
    ("The Voyage of the Beagle", ["The Voyage of the Beagle"]),
    ("The Expression of the Emotions in Man and Animals", ["The Expression of the Emotions in Man and Animals"]),
    # --- Hume ---
    ("A Treatise of Human Nature", ["A Treatise of Human Nature"]),
    ("An Enquiry Concerning Human Understanding", ["An Enquiry Concerning Human Understanding"]),
    ("An Enquiry Concerning the Principles of Morals", ["An Enquiry Concerning the Principles of Morals"]),
    ("Dialogues Concerning Natural Religion", ["Dialogues Concerning Natural Religion"]),
    # --- Epicur ---
    ("Letter to Menoeceus", ["Letter to Menoeceus"]),
    ("Principal Doctrines", ["Principal Doctrines"]),
    # --- Berkeley ---
    ("A Treatise Concerning the Principles of Human Knowledge", ["A Treatise Concerning the Principles of Human Knowledge"]),
    ("Three Dialogues between Hylas and Philonous", ["Three Dialogues Between Hylas and Philonous in Opposition to Sceptics and Atheis"]),
    ("An Essay Towards a New Theory of Vision", ["An Essay Towards a New Theory of Vision"]),
    # --- Bergson ---
    ("Creative Evolution (book)", ["Creative Evolution"]),
    ("Matter and Memory", ["Matter and memory"]),
    ("Time and Free Will", ["Time and free will, an essay on the immediate data of consciousness"]),
    # --- Bentham ---
    ("Panopticon", ["Panopticon or the Inspection-House"]),
    # --- Fichte ---
    ("Addresses to the German Nation", ["Addresses to the German nation", "Reden an die deutsche Nation (German)"]),
    ("The Vocation of Man", ["The vocation of man"]),
    # --- Lucreci ---
    ("De rerum natura", ["On the Nature of Things", "De Rerum Natura EN", "De Rerum Natura LA", "Translations from Lucretius"]),
    # --- Wollstonecraft ---
    ("A Vindication of the Rights of Woman", ["A Vindication of the Rights of Woman"]),
    ("A Vindication of the Rights of Men", ["A vindication of the rights of men, in a letter to the Right Honourable Edmund B"]),
    # --- Plotí ---
    ("Enneads", ["Plotinos Complete Works, v. 1", "Plotinos Complete Works, v. 2", "Plotinos Complete Works, v. 3", "Plotinos Complete Works, v. 4", "Select Works of Plotinus"]),
    # --- Emerson ---
    ("Nature (essay)", ["Nature"]),
    ("Essays: First Series", ["Essays — First Series"]),
    ("Essays: Second Series", ["Essays — Second Series"]),
    ("Representative Men (Emerson)", ["Representative Men Seven Lectures"]),
    ("The Conduct of Life", ["The Conduct of Life"]),
    ("English Traits", ["English Traits"]),
    # --- Freud ---
    ("Civilization and Its Discontents", ["Civilization and Its Discontents"]),
    ("The Interpretation of Dreams", ["Die Traumdeutung (German)"]),
    ("The Future of an Illusion", ["The Future of an Illusion"]),
    ("Totem and Taboo", ["Totem und Tabu (German)"]),
    ("Three Essays on the Theory of Sexuality", ["Drei Abhandlungen zur Sexualtheorie (German)"]),
    ("Beyond the Pleasure Principle", ["Jenseits des Lustprinzips (German)"]),
    ("Group Psychology and the Analysis of the Ego", ["Massenpsychologie und Ich-Analyse (German)"]),
    # --- Paine ---
    ("Common Sense (pamphlet)", ["Common Sense"]),
    # --- Ciceró ---
    ("De Officiis", ["De Officiis EN"]),
    ("Cato Maior de Senectute", ["Cato Maior de Senectute with Introduction and Notes (Latin)", "Treatises on Friendship and Old Age"]),
    ("Laelius de Amicitia", ["Laelius de Amicitia"]),
    ("De Natura Deorum", ["De Natura Deorum EN"]),
    ("Tusculanae Disputationes", ["Cicero's Tusculan Disputations"]),
    ("De Oratore", ["De Oratore (On Oratory and Orators)"]),
    ("De re publica", ["The republic of Cicero"]),
    ("De Divinatione", ["On Divination and On the Laws (Yonge Treatises of Cicero)"]),
    ("Paradoxa Stoicorum", ["Paradoxa Stoicorum"]),
    # --- Sèneca ---
    ("Epistulae Morales ad Lucilium", ["Moral Letters to Lucilius (Epistulae Morales)", "Epistles EN", "Epistles LA"]),
    ("De Brevitate Vitae", ["De brevitate vitae"]),
    ("De Clementia", ["De clementia"]),
    ("De Constantia Sapientis", ["De constantia sapientis", "On the Firmness of the Wise Man"]),
    ("De Otio", ["De otio", "Of Leisure"]),
    ("De Providentia", ["De providentia", "Of Providence"]),
    ("De Tranquillitate Animi", ["De tranquillitate animi", "Of Peace of Mind"]),
    ("De Vita Beata", ["De vita beata"]),
    ("De Beneficiis", ["L. Annaeus Seneca on Benefits"]),
    ("Apocolocyntosis", ["Apocolocyntosis", "Apocolocyntosis divi Claudii"]),
    ("Thyestes (Seneca)", ["Thyestes"]),
    # --- Plutarc ---
    ("Parallel Lives", ["Plutarch's Lives, Volume 1 (of 4)", "Plutarch's Lives, Volume 2 (of 4)", "Plutarch's Lives, Volume 3 (of 4)", "Plutarch's Lives, Volume 4 (of 4)", "Plutarch Lives of the noble Grecians and Romans", "Lives EN vol1"]),
    ("Moralia", ["Plutarch's Morals", "Complete Works of Plutarch — Volume 3 Essays and Miscellanies"]),
    # --- Xenofont ---
    ("Anabasis (Xenophon)", ["Anabasis", "The First Four Books of Xenophon's Anabasis", "The retreat of the ten thousand"]),
    ("Cyropaedia", ["Cyropaedia The Education of Cyrus"]),
    ("Memorabilia (Xenophon)", ["The Memorabilia", "The Memorable Thoughts of Socrates"]),
    ("Hellenica (Xenophon)", ["Hellenica"]),
    ("Symposium (Xenophon)", ["The Symposium"]),
    ("Oeconomicus", ["The Economist"]),
    # --- Erasme ---
    ("In Praise of Folly", ["In Praise of Folly", "The Praise of Folly"]),
    # --- Thomas More ---
    ("Utopia (book)", ["Utopia"]),
    # --- Textos orientals / sagrats ---
    ("Tao Te Ching", ["The Tao Teh King, or the Tao and its Characteristics", "道德經 by Laozi"]),
    ("Mencius (book)", ["孟子 (Chinese)"]),
    ("Zhuangzi (book)", ["Chuang Tzu Mystic, Moralist, and Social Reformer"]),
    ("The Art of War", ["The Art of War", "Sun Tzŭ on the Art of War The Oldest Military Treatise in the World"]),
    ("Bhagavad Gita", ["Bhagavad Gita (The Song Celestial)"]),
    ("Dhammapada", ["The Dhammapada"]),
    ("Upanishads", ["The Upanishads"]),
    # --- Al-Ghazali ---
    ("Al-Munqidh min al-Dalal", ["The Confessions of Al Ghazzali"]),
    # --- Comte ---
    ("A General View of Positivism", ["A General View of Positivism"]),
    ("Course of Positive Philosophy", ["The positive philosophy of Auguste Comte;"]),
    # --- Peirce ---
    ("The Fixation of Belief", ["The Fixation of Belief"]),
    ("On a New List of Categories", ["On a New List of Categories"]),
    # --- Durkheim ---
    ("The Division of Labour in Society", ["De la division du travail social (1893)"]),
    ("Suicide (book)", ["Le Suicide: Étude de sociologie"]),
    ("The Rules of Sociological Method", ["Les Règles de la méthode sociologique (1895)"]),
    ("The Elementary Forms of the Religious Life", ["The Elementary Forms of the Religious Life"]),
    # --- Vico ---
    ("The New Science", ["La scienza nuova — Volume I", "La scienza nuova — Volume II", "La scienza nuova — Volume III"]),
    # --- Giordano Bruno ---
    ("De gli eroici furori", ["The Heroic Enthusiasts (Gli Eroici Furori) Part the First"]),
    # --- Herbert Spencer ---
    ("The Man Versus the State", ["The Man versus the State"]),
    ("The Study of Sociology", ["The Study of Sociology"]),
    ("Social Statics", ["Social Statics"]),
    ("First Principles (book)", ["First Principles"]),
    # --- Feuerbach ---
    ("The Essence of Christianity", ["The Essence of Christianity"]),
    # --- Wittgenstein ---
    ("Tractatus Logico-Philosophicus", ["Tractatus Logico-Philosophicus (Ogden)"]),
    # --- Maimònides ---
    ("The Guide for the Perplexed", ["The Guide of the Perplexed"]),
    ("Shemonah Perakim", ["The eight chapters of Maimonides on ethics (Shemonah perakim);"]),
    # --- Stirner ---
    ("The Ego and Its Own", ["The Ego and His Own"]),
    # --- Weber ---
    ("The Protestant Ethic and the Spirit of Capitalism", ["The Protestant ethic and the spirit of capitalism"]),
    ("Politics as a Vocation", ["Politik als Beruf (Politics as a Vocation)"]),
    ("Science as a Vocation", ["Wissenschaft als Beruf (Science as a Vocation)"]),
    # --- Kropotkin ---
    ("Mutual Aid: A Factor of Evolution", ["Mutual Aid: A Factor of Evolution"]),
    ("The Conquest of Bread", ["The Conquest of Bread"]),
    # --- Proudhon ---
    ("What Is Property?", ["What is Property? An Inquiry into the Principle of Right and of Government"]),
    # --- Textos sagrats/clàssics del món ---
    ("Quran", ["The Qur'an"]),
    ("Rigveda", ["The Rig Veda"]),
    ("Mahabharata", ["The Mahabharata, Vol. I (Books 1-3: Adi, Sabha, Vana) — Ganguli",
                     "The Mahabharata, Vol. II (Books 4-7: Virata...Drona) — Ganguli",
                     "The Mahabharata, Vol. III (Books 8-12) — Ganguli",
                     "The Mahabharata, Vol. IV (Books 13-18) — Ganguli"]),
    ("Ramayana", ["The Ramayan of Valmiki (Griffith)"]),
    ("Epic of Gilgamesh", ["The Epic of Gilgamesh"]),
    ("Popol Vuh", ["The Popol Vuh The Mythic and Heroic Sagas of the Kichés of Central America"]),
    ("Poetic Edda", ["The Poetic Edda"]),
    ("Prose Edda", ["The Prose Edda (Younger Edda)"]),
    ("Book of the Dead", ["The Egyptian Book of the Dead (Papyrus of Ani)"]),
    ("Mabinogion", ["The Mabinogion"]),
    ("Rubaiyat of Omar Khayyam", ["Rubaiyat of Omar Khayyam (FitzGerald)"]),
    ("Yoga Sutras of Patanjali", ["The Yoga Sutras of Patanjali"]),
    ("Manusmriti", ["The Laws of Manu (Manusmriti, SBE vol. XXV)"]),
    ("I Ching", ["The I Ching (Book of Changes)"]),
    ("Lotus Sutra", ["The Saddharma-Pundarika (Lotus of the True Law, SBE XXI)"]),
    ("Classic of Poetry", ["The Book of Poetry (Shih King, Legge)"]),
    ("Kojiki", ["Kojiki (Records of Ancient Matters)"]),
    ("Nihon Shoki", ["Nihongi: Chronicles of Japan, Vol. I (Aston)", "Nihongi: Chronicles of Japan, Vol. II (Aston)"]),
    ("Hebrew Bible", ["The Holy Scriptures according to the Masoretic Text (JPS 1917)"]),
    ("Bible", ["The Holy Bible (King James Version)"]),
    ("Guru Granth Sahib", ["The Adi Granth (Holy Scriptures of the Sikhs)"]),
    ("Hadith", ["Muhammad in the Hadees: Sayings of the Prophet (Mirza Abu'l-Fadl)",
               "The Speeches and Table-Talk of the Prophet Mohammad (Lane-Poole)"]),
    ("The Imitation of Christ", ["The Imitation of Christ"]),
    ("Historia Calamitatum", ["Historia Calamitatum (The Story of My Misfortunes)"]),
    ("Augsburg Confession", ["The Augsburg Confession (Confessio Augustana, 1530)"]),
    ("Apology of the Augsburg Confession", ["Apology of the Augsburg Confession (1531)"]),
    ("Works and Days", ["Theogony and Works and Days"]),
    ("Lives and Opinions of Eminent Philosophers", ["The Lives and Opinions of Eminent Philosophers"]),
    # --- Marx / Engels (grans obres que faltaven) ---
    ("Das Kapital", ["Capital, Vol. I: A Critical Analysis of Capitalist Production",
                     "Capital, Vol. II: The Process of Circulation of Capital",
                     "Capital, Vol. III: The Process of Capitalist Production as a Whole"]),
    ("Anti-Dühring", ["Landmarks of Scientific Socialism Anti-Duehring"]),
    ("Socialism: Utopian and Scientific", ["Socialism, Utopian and Scientific"]),
    ("The Origin of the Family, Private Property and the State", ["The origin of the family, private property, and the state"]),
    ("The Condition of the Working Class in England", ["The Condition of the Working-Class in England in 1844"]),
    ("The Accumulation of Capital", ["The Accumulation of Capital"]),
    # --- Altres obres majors disperses ---
    ("Discourse on Metaphysics", ["Discourse on Metaphysics, Correspondence with Arnauld, and Monadology (1902)"]),
    ("God and the State", ["God and the State"]),
    ("An Essay on the Principle of Population", ["An Essay on the Principle of Population"]),
    ("Principles of Political Economy and Taxation", ["On the Principles of Political Economy and Taxation"]),
    ("Prison Memoirs of an Anarchist", ["Prison Memoirs of an Anarchist"]),
    ("Anarchism and Other Essays", ["Anarchism and Other Essays"]),
    ("My Disillusionment in Russia", ["My Disillusionment in Russia"]),
    ("Reflections on Violence", ["Réflexions sur la violence"]),
    ("The Spirits' Book", ["The Spirits' Book"]),
    ("Discourse on Political Economy", ["A Discourse on Political Economy (tr. Cole)"]),
    ("De Ente et Essentia", ["De ente et essentia"]),
    ("De regno", ["De regno ad regem Cypri"]),
    ("Democracy and Education", ["Democracy and Education An Introduction to the Philosophy of Education"]),
    ("How We Think", ["How We Think"]),
    ("Human Nature and Conduct", ["Human Nature and Conduct An introduction to social psychology"]),
    ("The School and Society", ["The School and Society"]),
    ("Reconstruction in Philosophy", ["Reconstruction in Philosophy"]),
    ("The Public and Its Problems", ["The public and its problems"]),
    ("Wissenschaftslehre", ["The science of knowledge y J.G. Fichte. Tr. from the German A.E. Kroeger",
                           "Concerning the Conception of the Science of Knowledge Generally"]),
    ("Epistle of Othea", ["The epistle of Othea to Hector; or, The boke of knyghthode",
                         "Épître d'Othéa, déesse de la Prudence à Hector, chef des Troyens. Reproduction d"]),
    ("El Criticón", ["El Criticón (tom 1)", "El Criticón (tom 2)"]),
    ("Oráculo manual y arte de prudencia", ["Agudeza y arte de ingenio; Oráculo manual y arte de prudencia (1669)"]),
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
            if not val:
                continue
            c = clean(val)
            if lang in _NONLATIN and c.isascii():  # fuita -> descarta
                continue
            out[a] = c
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
