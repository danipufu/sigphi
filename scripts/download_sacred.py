"""Baixa textos sagrats canònics en traducció de DOMINI PÚBLIC (Project Gutenberg),
els neteja (treu la capçalera/peu legal de Gutenberg) i els desa a corpus/ amb
capçalera SIGPHI: autor, obra, idioma + un caveat NEUTRAL (centrat en traducció i
transmissió textual, mai en la validesa religiosa).

Després, re-ingest (resumible, només els nous):  bash deploy/run_ingest.sh

Ús (al VPS, des de l'arrel):  python scripts/download_sacred.py
"""
from __future__ import annotations
import re
import urllib.request
from pathlib import Path

CORPUS = Path(__file__).resolve().parent.parent / "corpus"

# (gutenberg_id, author, work, language, completeness, authorship, note, filename)
TEXTS = [
    (10, "Bible", "The Holy Bible (King James Version)", "English",
     "Complete work", "Anonymous / composite",
     "Antologia de molts textos i autors recopilats al llarg de segles; "
     "versió King James (traducció anglesa de 1611), no els originals hebreu/grec.",
     "Bible__The_Holy_Bible_KJV_en.txt"),
    (2800, "Quran", "The Qur'an", "English",
     "Complete work", "Recorded/compiled by others",
     "Text sagrat de l'islam transmès i compilat pels seguidors de Mahoma; "
     "aquesta és una traducció anglesa (Rodwell, 1861), no l'àrab original.",
     "Quran__The_Quran_Rodwell_en.txt"),
    (2388, "Bhagavad Gita", "Bhagavad Gita (The Song Celestial)", "English",
     "Complete work", "Attributed (authorship debated)",
     "Episodi del poema èpic Mahabharata, tradicionalment atribuït a Vyasa; "
     "traducció poètica anglesa d'Edwin Arnold (1885), no el sànscrit original.",
     "Bhagavad_Gita__The_Song_Celestial_en.txt"),
    (2017, "Dhammapada", "The Dhammapada", "English",
     "Complete work", "Recorded/compiled by others",
     "Antologia de versos de la tradició budista, compilats pels deixebles; "
     "traducció anglesa de Max Müller (1881), no el pali original.",
     "Dhammapada__The_Dhammapada_en.txt"),

    # --- Lot 2 ---
    (4094, "Confucius",
     "The Four Books I: Analects, Great Learning, Doctrine of the Mean (Legge)",
     "English", "Complete work", "Recorded/compiled by others",
     "Clàssics confucians recollits i compilats pels deixebles; traducció de "
     "James Legge, no el xinès original.",
     "Confucius__The_Four_Books_I_Legge_en.txt"),
    (3283, "Upanishads", "The Upanishads", "English",
     "Selection / partial", "Anonymous / composite",
     "Textos vèdics de transmissió oral i autoria anònima; traducció anglesa, "
     "no el sànscrit original.",
     "Upanishads__The_Upanishads_en.txt"),
    (2526, "Patanjali", "The Yoga Sutras of Patanjali", "English",
     "Complete work", "Attributed (authorship debated)",
     "Aforismes atribuïts a Patañjali; traducció de Charles Johnston, no el "
     "sànscrit original.",
     "Patanjali__The_Yoga_Sutras_en.txt"),

    # --- Lot 3 ---
    (9394, "Shijing", "The Book of Poetry (Shih King, Legge)", "English",
     "Complete work", "Anonymous / composite",
     "Antologia de poemes de la Xina antiga, compilació anònima; un dels Cinc "
     "Clàssics confucians; traducció de James Legge, no el xinès original.",
     "Shijing__The_Book_of_Poetry_Legge_en.txt"),
    (18897, "Gilgamesh", "The Epic of Gilgamesh", "English",
     "Selection / partial", "Anonymous / composite",
     "Poema èpic mesopotàmic conservat en tauletes cuneïformes, autoria anònima; "
     "versió parcial de Langdon, no l'accadi original.",
     "Gilgamesh__The_Epic_of_Gilgamesh_en.txt"),
    (73533, "Poetic Edda", "The Poetic Edda", "English",
     "Complete work", "Anonymous / composite",
     "Poemes de la mitologia nòrdica de transmissió oral i autoria anònima; "
     "traducció de Bellows, no l'islandès original.",
     "Poetic_Edda__The_Poetic_Edda_en.txt"),
    (18947, "Snorri Sturluson", "The Prose Edda (Younger Edda)", "English",
     "Complete work", "Written by the author",
     "Compilació de la mitologia nòrdica per Snorri Sturluson (s.XIII); "
     "traducció anglesa, no l'islandès original.",
     "Snorri_Sturluson__The_Prose_Edda_en.txt"),
    (348, "Hesiod", "Theogony and Works and Days", "English",
     "Complete work", "Written by the author",
     "Poemes d'Hesíode (s.VIII aC); traducció d'Evelyn-White, no el grec "
     "original (el volum inclou també els himnes homèrics).",
     "Hesiod__Theogony_and_Works_and_Days_en.txt"),

    # --- Autors hispànics disponibles a Gutenberg ---
    (62691, "Baltasar Gracian", "El Criticón (tom 1)", "Spanish",
     "Complete work", "Written by the author", "—",
     "Baltasar_Gracian__El_Criticon_1_es.txt"),
    (63402, "Baltasar Gracian", "El Criticón (tom 2)", "Spanish",
     "Complete work", "Written by the author", "—",
     "Baltasar_Gracian__El_Criticon_2_es.txt"),
    (20321, "Bartolome de las Casas",
     "A Brief Account of the Destruction of the Indies", "English",
     "Complete work", "Written by the author",
     "Traducció anglesa de l'original castellà (1552).",
     "Las_Casas__Brief_Account_Destruction_Indies_en.txt"),

    # --- Lot 4: Mahabharata complet (trad. en prosa de Ganguli, 4 volums) ---
    (15474, "Mahabharata",
     "The Mahabharata, Vol. I (Books 1-3: Adi, Sabha, Vana) — Ganguli", "English",
     "Complete work", "Attributed (authorship debated)",
     "Poema èpic sànscrit tradicionalment atribuït a Vyasa, compost i ampliat al "
     "llarg de segles; traducció en prosa de Kisari Mohan Ganguli (1883-96), no el "
     "sànscrit original. Volum I de IV (llibres 1-3).",
     "Mahabharata__Ganguli_Vol1_en.txt"),
    (15475, "Mahabharata",
     "The Mahabharata, Vol. II (Books 4-7: Virata...Drona) — Ganguli", "English",
     "Complete work", "Attributed (authorship debated)",
     "Poema èpic sànscrit atribuït a Vyasa; traducció en prosa de K. M. Ganguli, "
     "no el sànscrit original. Volum II de IV (llibres 4-7; inclou la Bhagavad Gita "
     "en prosa dins el Bhishma Parva).",
     "Mahabharata__Ganguli_Vol2_en.txt"),
    (15476, "Mahabharata",
     "The Mahabharata, Vol. III (Books 8-12) — Ganguli", "English",
     "Complete work", "Attributed (authorship debated)",
     "Poema èpic sànscrit atribuït a Vyasa; traducció en prosa de K. M. Ganguli, "
     "no el sànscrit original. Volum III de IV (llibres 8-12).",
     "Mahabharata__Ganguli_Vol3_en.txt"),
    (15477, "Mahabharata",
     "The Mahabharata, Vol. IV (Books 13-18) — Ganguli", "English",
     "Complete work", "Attributed (authorship debated)",
     "Poema èpic sànscrit atribuït a Vyasa; traducció en prosa de K. M. Ganguli, "
     "no el sànscrit original. Volum IV de IV (llibres 13-18).",
     "Mahabharata__Ganguli_Vol4_en.txt"),

    # --- Lot 5: hispànics i analítics (Gutenberg) ---
    (28929, "Jaime Balmes", "El Criterio", "Spanish",
     "Complete work", "Written by the author", "—",
     "Jaime_Balmes__El_Criterio_es.txt"),

    # --- Lot 6: diàlegs de Plató que faltaven (trad. Jowett 1871, Gutenberg) ---
    # IDs verificats un a un a la pàgina de cada ebook (l'ID "de memòria" pot
    # col·lidir: p.ex. 6762 NO és la Retòrica d'Aristòtil sinó la Política).
    (1580, "Plato", "Charmides", "English",
     "Complete work", "Written by the author",
     "Diàleg de Plató sobre la temprança; traducció de Benjamin Jowett (1871), "
     "domini públic, no el grec original.",
     "Plato__Charmides_Jowett_en.txt"),
    (1584, "Plato", "Laches", "English",
     "Complete work", "Written by the author",
     "Diàleg de Plató sobre el valor; traducció de Benjamin Jowett (1871), domini "
     "públic, no el grec original.",
     "Plato__Laches_Jowett_en.txt"),
    (1598, "Plato", "Euthydemus", "English",
     "Complete work", "Written by the author",
     "Diàleg de Plató; traducció de Benjamin Jowett (1871), domini públic, no el "
     "grec original.",
     "Plato__Euthydemus_Jowett_en.txt"),
    (1616, "Plato", "Cratylus", "English",
     "Complete work", "Written by the author",
     "Diàleg de Plató sobre el llenguatge; traducció de Benjamin Jowett (1871), "
     "domini públic, no el grec original.",
     "Plato__Cratylus_Jowett_en.txt"),
    (1673, "Plato", "Lesser Hippias", "English",
     "Complete work", "Written by the author",
     "Diàleg de Plató (Hipies Menor); traducció de Benjamin Jowett (1871), domini "
     "públic, no el grec original.",
     "Plato__Lesser_Hippias_Jowett_en.txt"),
    (1682, "Plato", "Menexenus", "English",
     "Complete work", "Written by the author",
     "Diàleg de Plató; traducció de Benjamin Jowett (1871), domini públic, no el "
     "grec original.",
     "Plato__Menexenus_Jowett_en.txt"),
    (1744, "Plato", "Philebus", "English",
     "Complete work", "Written by the author",
     "Diàleg de Plató sobre el plaer i el bé; traducció de Benjamin Jowett (1871), "
     "domini públic, no el grec original.",
     "Plato__Philebus_Jowett_en.txt"),

    # --- Lot 7: Nietzsche (Consideracions intempestives I) ---
    (51710, "Nietzsche",
     "Thoughts Out of Season, Part I (David Strauss; Richard Wagner in Bayreuth)",
     "English", "Complete work", "Written by the author",
     "Consideracions intempestives I; conté 'David Strauss, the Confessor and "
     "Writer' i 'Richard Wagner in Bayreuth'. Traducció d'A. M. Ludovici (ed. Levy), "
     "domini públic. (Wagner in Bayreuth pot duplicar una entrada existent.)",
     "Nietzsche__Thoughts_Out_of_Season_I_en.txt"),

    # --- Lot 8: anarquistes restaurats com a autors propis (curació) ---
    # Aquests textos abans estaven MAL atribuïts a Emma Goldman (els vam treure);
    # ara entren amb l'autoria correcta.
    (34406, "Alexander Berkman", "Prison Memoirs of an Anarchist", "English",
     "Complete work", "Written by the author",
     "Memòries de presó d'Alexander Berkman (1912), domini públic. Abans estava mal "
     "atribuït a Emma Goldman al corpus.",
     "Alexander_Berkman__Prison_Memoirs_en.txt"),
    (43098, "Voltairine de Cleyre", "Selected Works of Voltairine de Cleyre", "English",
     "Complete work", "Written by the author",
     "Antologia d'assaigs i poemes de Voltairine de Cleyre (ed. Berkman, 1914), "
     "domini públic. Conté 'In Defense of Emma Goldman', abans mal atribuït a Goldman.",
     "Voltairine_de_Cleyre__Selected_Works_en.txt"),

    # --- Lot 9: hadits (dites del profeta Mahoma) — selecció PD ---
    (58426, "Hadith",
     "The Speeches and Table-Talk of the Prophet Mohammad (Lane-Poole)", "English",
     "Selection / partial", "Recorded/compiled by others",
     "Selecció de les dites i discursos del profeta Mahoma (hadits), transmesos i "
     "compilats pels seguidors; edició de Stanley Lane-Poole (1882), domini públic, "
     "no l'àrab original. (Els grans reculls -Bukhari, Muslim- només tenen traducció "
     "anglesa moderna amb copyright.)",
     "Hadith__Speeches_Table_Talk_Lane_Poole_en.txt"),

    # --- Lot 10: cluster B (anarquistes/polítics, filòsofs, mística) — Gutenberg PD ---
    (360, "Proudhon",
     "What is Property? An Inquiry into the Principle of Right and of Government",
     "English", "Complete work", "Written by the author",
     "Obra clàssica de l'anarquisme de P.-J. Proudhon (1840); trad. de Benjamin Tucker, "
     "domini públic. (És l'obra a què respon la 'Misèria de la filosofia' de Marx.)",
     "Proudhon__What_is_Property_en.txt"),
    (34580, "Max Stirner", "The Ego and His Own", "English",
     "Complete work", "Written by the author",
     "Obra fundacional de l'egoisme de Max Stirner (1844); trad. de S. Byington, domini públic.",
     "Max_Stirner__The_Ego_and_His_Own_en.txt"),
    (4341, "Peter Kropotkin", "Mutual Aid: A Factor of Evolution", "English",
     "Complete work", "Written by the author",
     "Tesi de Piotr Kropotkin sobre la cooperació com a factor evolutiu (1902), domini públic.",
     "Peter_Kropotkin__Mutual_Aid_en.txt"),
    (23428, "Peter Kropotkin", "The Conquest of Bread", "English",
     "Complete work", "Written by the author",
     "Obra anarcocomunista de Piotr Kropotkin (1892), domini públic.",
     "Peter_Kropotkin__Conquest_of_Bread_en.txt"),
    (36568, "Mikhail Bakunin", "God and the State", "English",
     "Complete work", "Written by the author",
     "Assaig antiteista i anarquista de M. Bakunin (1871, pòstum); trad. anglesa, domini públic.",
     "Mikhail_Bakunin__God_and_the_State_en.txt"),
    # Bertrand Russell (mort 1970): NO PD a Europa fins al 2041 (70 anys pma).
    # Publicat el 1912 (PD als EUA), però protegit al Regne Unit i UE fins al 2041.
    # (5827, "Bertrand Russell", "The Problems of Philosophy", ...)
    (47025, "Ludwig Feuerbach", "The Essence of Christianity", "English",
     "Complete work", "Written by the author",
     "Crítica de la religió de L. Feuerbach (1841); trad. de George Eliot (Mary Ann "
     "Evans), domini públic. (Influència clau en el jove Marx.)",
     "Ludwig_Feuerbach__Essence_of_Christianity_en.txt"),
    (1653, "Thomas a Kempis", "The Imitation of Christ", "English",
     "Complete work", "Written by the author",
     "Clàssic devocional cristià de Tomàs de Kempis (c. 1420); trad. anglesa, domini públic.",
     "Thomas_a_Kempis__Imitation_of_Christ_en.txt"),
    (4239, "Thomas Malthus", "An Essay on the Principle of Population", "English",
     "Complete work", "Written by the author",
     "Assaig de T. R. Malthus sobre població i recursos (1798), domini públic.",
     "Thomas_Malthus__Principle_of_Population_en.txt"),
    (33310, "David Ricardo", "On the Principles of Political Economy and Taxation",
     "English", "Complete work", "Written by the author",
     "Obra fonamental d'economia política de David Ricardo (1817), domini públic.",
     "David_Ricardo__Principles_Political_Economy_en.txt"),
    (246, "Omar Khayyam", "Rubaiyat of Omar Khayyam (FitzGerald)", "English",
     "Selection / partial", "Attributed (authorship debated)",
     "Quartetes perses atribuïdes a Omar Khayyam (s. XI-XII); cèlebre versió anglesa "
     "d'Edward FitzGerald (1859), domini públic, no el persa original.",
     "Omar_Khayyam__Rubaiyat_FitzGerald_en.txt"),
    (55046, "Herbert Spencer", "First Principles", "English",
     "Complete work", "Written by the author",
     "Obra fonamental del sistema filosòfic evolucionista de Herbert Spencer (1862), "
     "domini públic.",
     "Herbert_Spencer__First_Principles_en.txt"),
    (45159, "Rumi", "The Persian Mystics: Jalalu'd-din Rumi", "English",
     "Selection / partial", "Written by the author",
     "Selecció de la mística sufí de Jalal-ad-Din Rumi (s. XIII); versió anglesa de "
     "F. Hadland Davis (Wisdom of the East, 1907), domini públic, no el persa original.",
     "Rumi__Persian_Mystics_en.txt"),
    (33742, "Jacob Boehme", "Dialogues on the Supersensual Life", "English",
     "Selection / partial", "Written by the author",
     "Diàlegs místics de Jakob Böhme (s. XVII); traducció anglesa de domini públic.",
     "Jacob_Boehme__Supersensual_Life_en.txt"),

    # --- Lot 11: Locke (obres que faltaven; Gutenberg PD) ---
    (10616, "Locke", "An Essay Concerning Humane Understanding, Volume 2", "English",
     "Complete work", "Written by the author",
     "Volum 2 de l'Assaig (Llibres III-IV: de les paraules i del coneixement); "
     "text original de John Locke (1689), domini públic.",
     "Locke__An_Essay_Concerning_Humane_Understanding_Volume_2_en.txt"),

    # --- Lot 12: sociologia i psicoanàlisi (Gutenberg PD) ---
    # Durkheim mort 1917 -> PD. Traducció de Swain (1915) PD. Le Suicide original fr. PD.
    # Freud mort 1939 -> PD a EU des de 2010. Traduccions 1928/1930 PD als EUA (no renovades).
    (40489, "Emile Durkheim", "Le Suicide: Étude de sociologie", "French",
     "Complete work", "Written by the author",
     "Obra clàssica de sociologia de Durkheim (1897); original francès en domini públic. "
     "(La traducció anglesa de Spaulding/Simpson de 1951 no és PD.)",
     "Durkheim__Le_Suicide_fr.txt"),
    (41360, "Emile Durkheim", "The Elementary Forms of the Religious Life", "English",
     "Complete work", "Written by the author",
     "Obra mestra de Durkheim sobre la religió i el totemisme (1912); traducció anglesa "
     "de J. W. Swain (1915), domini públic.",
     "Durkheim__Elementary_Forms_Religious_Life_en.txt"),
    (76774, "Sigmund Freud", "The Future of an Illusion", "English",
     "Complete work", "Written by the author",
     "Assaig de Freud sobre la religió com a il·lusió col·lectiva (1927); traducció "
     "anglesa de W. D. Robson-Scott (1928), domini públic als EUA (copyright no renovat).",
     "Freud__The_Future_of_an_Illusion_en.txt"),
    (78221, "Sigmund Freud", "Civilization and Its Discontents", "English",
     "Complete work", "Written by the author",
     "Assaig de Freud sobre la tensió entre la civilització i els instints (1930); "
     "traducció anglesa de Joan Riviere (1930), domini públic als EUA (copyright no renovat).",
     "Freud__Civilization_and_Its_Discontents_en.txt"),

    # --- Lot 13: filòsofs hispànics (Gutenberg PD) ---
    # Balmes mort 1848 -> PD. Filosofia fundamental 4 vols (es originals, Gutenberg).
    # El Protestantismo: escrit en castellà 1842-1844 (PD), 2 vols en 1 ebook.
    (13608, "Jaime Balmes", "Filosofía fundamental, Tomo I", "Spanish",
     "Complete work", "Written by the author",
     "Obra filosòfica principal de Balmes (1846), vol. I. Original castellà, domini públic.",
     "Jaime_Balmes__Filosofia_fundamental_I_es.txt"),
    (16132, "Jaime Balmes", "Filosofía fundamental, Tomo II", "Spanish",
     "Complete work", "Written by the author",
     "Filosofia fundamental de Balmes (1846), vol. II. Original castellà, domini públic.",
     "Jaime_Balmes__Filosofia_fundamental_II_es.txt"),
    (17974, "Jaime Balmes", "Filosofía fundamental, Tomo III", "Spanish",
     "Complete work", "Written by the author",
     "Filosofia fundamental de Balmes (1846), vol. III. Original castellà, domini públic.",
     "Jaime_Balmes__Filosofia_fundamental_III_es.txt"),
    (28430, "Jaime Balmes", "Filosofía fundamental, Tomo IV", "Spanish",
     "Complete work", "Written by the author",
     "Filosofia fundamental de Balmes (1846), vol. IV. Original castellà, domini públic.",
     "Jaime_Balmes__Filosofia_fundamental_IV_es.txt"),
    (59797, "Jaime Balmes",
     "El Protestantismo comparado con el Catolicismo en sus relaciones con la Civilización Europea",
     "Spanish", "Complete work", "Written by the author",
     "Obra apologètica de Balmes (1842-1844) que compara protestantisme i catolicisme; "
     "original castellà, domini públic. (Volums 1-2 en un sol ebook.)",
     "Jaime_Balmes__El_Protestantismo_comparado_es.txt"),

    # --- Lot 14: Reformadors protestants (Gutenberg PD) ---
    # Luther mort 1546 -> PD. Traduccions Holman 1915-1916 (PD als EUA).
    # Calvin mort 1564 -> PD. Trad. Beveridge 1845 (PD als EUA).
    # Melanchthon mort 1560 -> PD.
    (31604, "Martin Luther", "Works of Martin Luther, Volume I", "English",
     "Complete work", "Written by the author",
     "Obres de Martí Luter vol. I (Holman, Philadelphia, 1915): inclou les 95 Tesis "
     "(Disputatio, 1517), Tractat del Baptisme (1519), Tractat de les Bones Obres "
     "(1520), La Papessa a Roma (1520), i altres escrits del període fundacional de "
     "la Reforma Protestant. Traducció anglesa PD.",
     "Martin_Luther__Works_Vol_I_en.txt"),
    (34904, "Martin Luther", "Works of Martin Luther, Volume II", "English",
     "Complete work", "Written by the author",
     "Obres de Martí Luter vol. II (Holman, 1916): inclou els tres grans tractats "
     "del 1520 — la Carta Oberta a la Noblesa Cristiana Alemanya, La Captivitat "
     "Babilònica de l'Església i Un Tractat sobre la Llibertat Cristiana — més "
     "els Sermons de Wittenberg (1522). Texts fonamentals de la Reforma. PD.",
     "Martin_Luther__Works_Vol_II_en.txt"),
    (273, "Martin Luther", "The Smalcald Articles (1537)", "English",
     "Complete work", "Written by the author",
     "Articles de Smalcalda (1537) de Martí Luter: definició luterana ortodoxa "
     "sobre el primat papal, la missa i els sagraments; redactats per encàrrec "
     "de l'Elector Joan Frederic de Saxònia. Text confessional fonamental del "
     "luteranisme. Traducció anglesa PD.",
     "Martin_Luther__Smalcald_Articles_en.txt"),
    (1549, "Martin Luther", "Commentary on the Epistle to the Galatians (1535)", "English",
     "Complete work", "Written by the author",
     "Comentari de Luter a l'Epístola als Gàlates (1535, ed. definitiva): la seva "
     "obra teològica més elaborada sobre la justificació per la fe sola (sola fide), "
     "la distinció llei/gràcia i la llibertat cristiana. Traducció anglesa PD.",
     "Martin_Luther__Commentary_on_Galatians_en.txt"),
    (45001, "John Calvin", "Institutes of the Christian Religion, Volume I", "English",
     "Complete work", "Written by the author",
     "Institució de la Religió Cristiana de Joan Calví (ed. def. 1559), vol. I "
     "(Llibres I-II): el coneixement de Déu Creador, l'autoritat de l'Escriptura, "
     "la Providència, el pecat original i la predestinació. Traducció anglesa "
     "d'Henry Beveridge (1845), domini públic. Obra mestra de la teologia reformada.",
     "John_Calvin__Institutes_Vol_I_en.txt"),
    (64392, "John Calvin", "Institutes of the Christian Religion, Volume II", "English",
     "Complete work", "Written by the author",
     "Institució de la Religió Cristiana de Joan Calví, vol. II (Llibres III-IV): "
     "la fe, la justificació per la gràcia, la predestinació, el govern de l'Església "
     "i els sagraments. Traducció anglesa d'Henry Beveridge (1845), domini públic.",
     "John_Calvin__Institutes_Vol_II_en.txt"),
    (275, "Philip Melanchthon", "The Augsburg Confession (Confessio Augustana, 1530)", "English",
     "Complete work", "Written by the author",
     "Confessió d'Augsburg (1530) de Filip Melanchthon: document confessional luterà "
     "presentat a l'emperador Carles V a la Dieta d'Augsburg; base dogmàtica del "
     "luteranisme i punt de referència per al diàleg catòlic-protestant. PD.",
     "Philip_Melanchthon__Augsburg_Confession_en.txt"),
    (6744, "Philip Melanchthon", "Apology of the Augsburg Confession (1531)", "English",
     "Complete work", "Written by the author",
     "Apologia de la Confessió d'Augsburg (1531) de Filip Melanchthon: defensa "
     "detallada dels 21 articles de la Confessió contra la Confutació Catòlica; "
     "text doctrinal fonamental del luteranisme primerenc. Traducció anglesa PD.",
     "Philip_Melanchthon__Apology_Augsburg_Confession_en.txt"),

    # --- Lot 15: medievals i renaixentistes (Gutenberg PD) ---
    (14268, "Peter Abelard", "Historia Calamitatum (The Story of My Misfortunes)", "English",
     "Complete work", "Written by the author",
     "Autobiografia epistolar de Pere Abelard (c. 1132) en la qual narra la seva "
     "vida intel·lectual, la relació amb Heloïsa i les seves persecucions. "
     "Traducció anglesa de Henry Adams Bellows (1922), domini públic.",
     "Abelard__Historia_Calamitatum_en.txt"),
    (35977, "Peter Abelard", "Letters of Abelard and Heloise", "English",
     "Complete work", "Written by the author",
     "Correspondència entre Pere Abelard i Heloïsa d'Argenteuil (s. XII): "
     "les cartes tracten la vida monàstica, l'amor, la filosofia i la teologia. "
     "Traducció anglesa de Scott Moncrieff (1925), domini públic.",
     "Abelard__Letters_of_Abelard_and_Heloise_en.txt"),
]

_START = re.compile(r"\*\*\*\s*START OF (THE|THIS) PROJECT GUTENBERG.*?\*\*\*", re.I | re.S)
_END = re.compile(r"\*\*\*\s*END OF (THE|THIS) PROJECT GUTENBERG.*?\*\*\*", re.I | re.S)


def fetch(gid: int) -> str | None:
    urls = [
        f"https://www.gutenberg.org/cache/epub/{gid}/pg{gid}.txt",
        f"https://www.gutenberg.org/files/{gid}/{gid}-0.txt",
        f"https://www.gutenberg.org/files/{gid}/{gid}.txt",
    ]
    for url in urls:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (SigPhi)"})
            with urllib.request.urlopen(req, timeout=90) as r:
                raw = r.read()
            try:
                return raw.decode("utf-8")
            except UnicodeDecodeError:
                return raw.decode("latin-1")  # edicions Gutenberg antigues (ISO-8859-1)
        except Exception:
            continue
    return None


def strip_gutenberg(text: str) -> str:
    m = _START.search(text)
    if m:
        text = text[m.end():]
    m = _END.search(text)
    if m:
        text = text[:m.start()]
    # Soroll editorial: crèdit "Produced by ..." del principi (només 1a aparició).
    text = re.sub(r"(?is)\A\s*Produced by .*?\n\s*\n", "", text, count=1)
    return text.strip()


def strip_jowett_intro(text: str) -> str:
    """Diàlegs de Plató (Jowett): talla la llarga INTRODUCTION/ANALYSIS del traductor
    i comença al diàleg pròpiament dit. Marcador fiable: la capçalera en MAJÚSCULES
    'PERSONS OF THE DIALOGUE'. Si no hi és, no toca res (zero risc de retallar el text)."""
    m = re.search(r"(?m)^PERSONS OF THE DIALOGUE", text)
    if m:
        return text[m.start():].strip()
    return text


def main() -> None:
    CORPUS.mkdir(parents=True, exist_ok=True)
    ok = 0
    for gid, author, work, lang, comp, auth, note, fname in TEXTS:
        dest = CORPUS / fname
        if dest.exists():
            print(f"[skip] ja existeix: {fname}")
            ok += 1
            continue
        print(f"[baixant] {work} (Gutenberg #{gid})...")
        raw = fetch(gid)
        if not raw:
            print(f"   ERROR: no s'ha pogut baixar #{gid}")
            continue
        body = strip_gutenberg(raw)
        if author == "Plato":  # treu la introducció del traductor (Jowett)
            body = strip_jowett_intro(body)
        if len(body) < 5000:
            print(f"   AVÍS: text molt curt ({len(body)} car.) -> revisa la font")
        header = (
            "=====SIGPHI=====\n"
            f"author: {author}\nwork: {work}\nlanguage: {lang}\n"
            f"completeness: {comp}\nauthorship: {auth}\nnote: {note}\n"
            "=====\n\n"
        )
        dest.write_text(header + body, encoding="utf-8")
        print(f"   OK -> {fname} ({len(body)//1024} KB)")
        ok += 1
    print(f"\n{ok}/{len(TEXTS)} textos a punt a corpus/.")
    print("Ara re-ingesta els nous (resumible):  bash deploy/run_ingest.sh")


if __name__ == "__main__":
    main()
