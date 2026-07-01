"""Baixa textos en DOMINI PÚBLIC d'Internet Archive (text complet OCR `_djvu.txt`),
neteja el soroll de l'OCR (salts de pàgina, espais sobrants) i els desa a corpus/
amb la MATEIXA capçalera SIGPHI que download_sacred.py (autor, obra, idioma + un
caveat NEUTRAL centrat en traducció/transmissió i en el fet que és una
digitalització OCR; mai en la validesa religiosa).

Per a fonts que NO són a Project Gutenberg (escriptura sij, I Ching de Legge,
Zend-Avesta de Darmesteter...). Internet Archive serveix el text complet a:
    https://archive.org/download/<identifier>/<fitxer>_djvu.txt
(el `urllib` segueix sol el redirect 302 cap al node de dades; el nom del fitxer
_djvu.txt no sempre coincideix amb l'identifier, per això es desa explícit).

Ús (al VPS, des de l'arrel):  python scripts/download_archive.py
"""
from __future__ import annotations
import re
import time
import urllib.parse
import urllib.request
from pathlib import Path

CORPUS = Path(__file__).resolve().parent.parent / "corpus"

# Per a miralls de Project Gutenberg allotjats a archive.org: treure capçalera/peu legal.
_GUT_START = re.compile(r"\*\*\*\s*START OF (THE|THIS) PROJECT GUTENBERG.*?\*\*\*", re.I | re.S)
_GUT_END = re.compile(r"\*\*\*\s*END OF (THE|THIS) PROJECT GUTENBERG.*?\*\*\*", re.I | re.S)

# (identifier, djvu_filename, author, work, language, completeness, authorship, note, out_filename)
TEXTS = [
    ("TheAdiGranthOrTheHolyScripturesOfTheSikhs",
     "TheAdiGranthOrTheHolyScripturesOfTheSikhs_djvu.txt",
     "Adi Granth", "The Adi Granth (Holy Scriptures of the Sikhs)", "English",
     "Selection / partial", "Recorded/compiled by others",
     "Escriptura sij compilada per Guru Arjan (1604) amb himnes dels gurus sikhs i "
     "de diversos bhagats; traducció anglesa parcial d'Ernest Trumpp (1877), no el "
     "gurmukhi original. Digitalització OCR d'Internet Archive.",
     "Adi_Granth__Trumpp_en.txt"),
    ("iching00jame", "iching00jame_djvu.txt",
     "I Ching", "The I Ching (Book of Changes)", "English",
     "Complete work", "Anonymous / composite",
     "Clàssic xinès endevinatori i filosòfic, de formació anònima i composta (nucli "
     "Zhou Yi més les 'Deu Ales' atribuïdes a Confuci); traducció de James Legge "
     "(1882, SBE vol. XVI), no el xinès original. Digitalització OCR.",
     "I_Ching__Legge_en.txt"),
    ("in.ernet.dli.2015.500448", "2015.500448.The-Zend-Avesta_djvu.txt",
     "Avesta", "The Zend-Avesta, Part I: The Vendidad (SBE vol. IV)", "English",
     "Selection / partial", "Anonymous / composite",
     "Escriptura zoroastriana; aquest volum és la Part I (el Vendidad), de composició "
     "sacerdotal; traducció de James Darmesteter (1880, SBE vol. IV), no l'avèstic "
     "original. Digitalització OCR. Els Gathes, atribuïts a Zaratustra, són en altres volums.",
     "Avesta__Vendidad_Darmesteter_en.txt"),

    # --- Lot 5 ---
    ("kautilyasarthash00sham", "kautilyasarthash00sham_djvu.txt",
     "Kautilya", "Arthashastra (Treatise on Statecraft)", "English",
     "Complete work", "Written by the author",
     "Tractat sànscrit de política i economia atribuït a Kautilya (Chanakya, s. IV aC); "
     "traducció de R. Shamasastry (1915), no el sànscrit original. Digitalització OCR.",
     "Kautilya__Arthashastra_Shamasastry_en.txt"),
    ("ideariumespaol01gani", "ideariumespaol01gani_djvu.txt",
     "Angel Ganivet", "Idearium español", "Spanish",
     "Complete work", "Written by the author",
     "Assaig d'Ángel Ganivet (1897). Digitalització OCR de l'edició original; "
     "pot contenir errades de reconeixement de text.",
     "Angel_Ganivet__Idearium_espanol_es.txt"),
    ("in.ernet.dli.2015.495279", "2015.495279.THA-SACRED_djvu.txt",
     "Avesta", "The Zend-Avesta, Part III: Yasna, Visparad, Gathas (SBE vol. XXXI)",
     "English", "Selection / partial", "Anonymous / composite",
     "Escriptura zoroastriana; Part III: el Yasna i sobretot els Gathes, himnes "
     "atribuïts directament a Zaratustra (el nucli més antic); traducció de L. H. Mills "
     "(1887, SBE vol. XXXI), no l'avèstic original. Digitalització OCR.",
     "Avesta__Yasna_Gathas_Mills_en.txt"),
    ("LesProlegomenesDIbnKhaldounVolume1",
     "Les Prolégomènes d'Ibn Khaldoun - Volume 1_djvu.txt",
     "Ibn Khaldun", "Les Prolégomènes (Muqaddimah), Volume I", "French",
     "Selection / partial", "Written by the author",
     "Introducció a la història universal d'Ibn Khaldun (1377); traducció francesa "
     "de W. M. de Slane (1863), no l'àrab original. Volum I de III. Digitalització OCR.",
     "Ibn_Khaldun__Prolegomenes_Vol1_de_Slane_fr.txt"),
    # Wittgenstein: el #5740 de Gutenberg NO té .txt directe (només PDF/TeX); fem
    # servir el mirall del text net de Gutenberg allotjat a Internet Archive.
    ("tractatuslogicop05740gut", "tloph10.txt",
     "Ludwig Wittgenstein", "Tractatus Logico-Philosophicus (Ogden)", "English",
     "Complete work", "Written by the author",
     "Traducció anglesa de C. K. Ogden (1922) del Tractatus (original alemany de 1921). "
     "Text de Project Gutenberg (#5740) via mirall d'Internet Archive.",
     "Wittgenstein__Tractatus_Ogden_en.txt"),

    # --- Lot 6 ---
    ("zendavesta02darm", "zendavesta02darm_djvu.txt",
     "Avesta", "The Zend-Avesta, Part II: Sirozahs, Yasts, Nyayis (SBE vol. XXIII)",
     "English", "Selection / partial", "Anonymous / composite",
     "Escriptura zoroastriana; Part II: els Yasts (himnes a divinitats) i els Sirozahs; "
     "traducció de James Darmesteter (1883, SBE vol. XXIII), no l'avèstic original. "
     "Digitalització OCR.",
     "Avesta__Yasts_Darmesteter_en.txt"),
    ("logischeuntersuc01hussuoft", "logischeuntersuc01hussuoft_djvu.txt",
     "Edmund Husserl", "Logische Untersuchungen, Band I (Prolegomena zur reinen Logik)",
     "German", "Selection / partial", "Written by the author",
     "Obra fundacional de la fenomenologia; original alemany d'Edmund Husserl (1900), "
     "en domini públic. Volum I de II (Prolegòmens a la lògica pura). Digitalització "
     "OCR (tipografia romana, no gòtica).",
     "Husserl__Logische_Untersuchungen_I_de.txt"),
    ("nihongi1asto", "nihongi1asto_djvu.txt",
     "Nihongi", "Nihongi: Chronicles of Japan, Vol. I (Aston)", "English",
     "Complete work", "Recorded/compiled by others",
     "Crònica xintoista del Japó compilada per la cort imperial (720 dC); traducció "
     "anglesa de W. G. Aston (1896), no el japonès clàssic original. Volum I de II. "
     "Digitalització OCR.",
     "Nihongi__Aston_Vol1_en.txt"),
    ("nihongi2asto", "nihongi2asto_djvu.txt",
     "Nihongi", "Nihongi: Chronicles of Japan, Vol. II (Aston)", "English",
     "Complete work", "Recorded/compiled by others",
     "Crònica xintoista del Japó compilada per la cort imperial (720 dC); traducció "
     "anglesa de W. G. Aston (1896), no el japonès clàssic original. Volum II de II. "
     "Digitalització OCR.",
     "Nihongi__Aston_Vol2_en.txt"),
    ("TheBookOfTheDead-Budge-1895", "TheBookOfTheDead-Budge-1895_djvu.txt",
     "Book of the Dead", "The Egyptian Book of the Dead (Papyrus of Ani)", "English",
     "Selection / partial", "Anonymous / composite",
     "Textos funeraris de l'antic Egipte, de composició anònima i acumulats al llarg "
     "de segles; recensió del Papir d'Ani. Edició d'E. A. W. Budge (1895) amb traducció "
     "anglesa, introducció i transliteració (l'OCR inclou aquest aparat). No l'egipci original.",
     "Book_of_the_Dead__Papyrus_of_Ani_Budge_en.txt"),

    # --- Lot 7 ---
    ("in.ernet.dli.2015.65699", "2015.65699.The-Rig-Veda_djvu.txt",
     "Rig Veda", "The Rig Veda", "English",
     "Selection / partial", "Anonymous / composite",
     "Himnes vèdics de transmissió oral i autoria anònima (els textos més antics de "
     "l'hinduisme); traducció anglesa de domini públic (s. XIX), no el sànscrit "
     "original. Digitalització OCR.",
     "Rig_Veda__en.txt"),
    ("lawsofmanu00manuuoft", "lawsofmanu00manuuoft_djvu.txt",
     "Laws of Manu", "The Laws of Manu (Manusmriti, SBE vol. XXV)", "English",
     "Complete work", "Attributed (authorship debated)",
     "Tractat de dret i deure hindú (dharmaśāstra) atribuït tradicionalment a Manu; "
     "traducció de Georg Bühler (1886, SBE vol. XXV), no el sànscrit original. "
     "Digitalització OCR.",
     "Laws_of_Manu__Buhler_en.txt"),
    # Anne Conway: l'ítem principlesofmost00conw d'archive.org falla sempre (403/500)
    # i no hi ha cap font PD neta alternativa -> entrada retirada (autora absent).
    ("discursoenelcong00boli", "discursoenelcong00boli_djvu.txt",
     "Simon Bolivar", "Discurso de Angostura (1819)", "Spanish",
     "Complete work", "Written by the author",
     "Discurs de Simón Bolívar al Congrés d'Angostura (1819); edició de Caracas (1922). "
     "Digitalització OCR.",
     "Simon_Bolivar__Discurso_de_Angostura_es.txt"),
    ("ramayanofvlm00valmrich", "ramayanofvlm00valmrich_djvu.txt",
     "Ramayana", "The Ramayan of Valmiki (Griffith)", "English",
     "Complete work", "Attributed (authorship debated)",
     "Poema èpic sànscrit atribuït a Valmiki; traducció en vers de Ralph T. H. Griffith "
     "(1895), no el sànscrit original. Digitalització OCR.",
     "Ramayana__Griffith_en.txt"),
    ("TristanPeregrinations01BNF", "TristanPeregrinations01BNF_djvu.txt",
     "Flora Tristan", "Pérégrinations d'une paria, tome I", "French",
     "Selection / partial", "Written by the author",
     "Memòries i crítica social de Flora Tristan (1838), volum I. Original francès en "
     "domini públic. Digitalització OCR.",
     "Flora_Tristan__Peregrinations_I_fr.txt"),
    ("the-spirits-book-by-allan-kardec", "The Spirits Book by Allan Kardec _djvu.txt",
     "Allan Kardec", "The Spirits' Book", "English",
     "Complete work", "Written by the author",
     "Obra fundacional de l'espiritisme, d'Allan Kardec (original francès 1857); "
     "traducció anglesa de domini públic (Blackwell). Digitalització OCR.",
     "Allan_Kardec__The_Spirits_Book_en.txt"),

    # --- Lot 8 ---
    ("holyscripturesac028077mbp", "holyscripturesac028077mbp_djvu.txt",
     "Tanakh", "The Holy Scriptures according to the Masoretic Text (JPS 1917)", "English",
     "Complete work", "Anonymous / composite",
     "Bíblia hebrea (Tanakh), antologia de molts textos i autors recopilats al llarg de "
     "segles; traducció anglesa jueva de la Jewish Publication Society (1917), no l'hebreu "
     "original. Digitalització OCR.",
     "Tanakh__JPS_1917_en.txt"),
    ("taoistteachings00liehuoft", "taoistteachings00liehuoft_djvu.txt",
     "Liezi", "Taoist Teachings from the Book of Lieh-Tzu", "English",
     "Selection / partial", "Attributed (authorship debated)",
     "Clàssic taoista atribuït a Lie Zi; traducció (selecció) de Lionel Giles (1912), no "
     "el xinès original complet. Digitalització OCR.",
     "Liezi__Giles_en.txt"),
    ("wg949", "WG949-1894 -The Sacred Books of East - Vol 49 of 50 - Buddhism-Mahâyâna Texts_djvu.txt",
     "Mahayana Sutras",
     "Buddhist Mahayana Texts: Diamond Sutra, Heart Sutra, Sukhavativyuha (SBE XLIX)",
     "English", "Selection / partial", "Anonymous / composite",
     "Sutres budistes mahayana de composició anònima; inclou el Sutra del Diamant "
     "(Vajracchedika) i el Sutra del Cor; traduccions de Müller, Cowell i Takakusu (1894, "
     "SBE vol. XLIX), no el sànscrit original. Digitalització OCR.",
     "Mahayana_Sutras__SBE49_en.txt"),
    ("wg921", "WG921-1884 -The Sacred Books of East - Vol 21 of 50-Buddhism-The Saddharma- Pundarika or The Lotus of the True Law_djvu.txt",
     "Lotus Sutra", "The Saddharma-Pundarika (Lotus of the True Law, SBE XXI)", "English",
     "Complete work", "Anonymous / composite",
     "Sutra mahayana de composició anònima; traducció de Hendrik Kern (1884, SBE vol. XXI), "
     "no el sànscrit original. Digitalització OCR.",
     "Lotus_Sutra__Kern_en.txt"),
    ("wg922", "WG922-1884 -The Sacred Books of East - Vol 22 of 50 - Jain Sutras - Part 1 Of 2_djvu.txt",
     "Jaina Sutras", "Jaina Sutras, Part I: Acaranga and Kalpa Sutra (SBE XXII)", "English",
     "Selection / partial", "Anonymous / composite",
     "Escriptures jainistes (Acaranga i Kalpa Sutra) de transmissió i autoria tradicional; "
     "traducció de Hermann Jacobi (1884, SBE vol. XXII), no el prakrit original. Part I de "
     "II. Digitalització OCR.",
     "Jaina_Sutras__Jacobi_I_en.txt"),

    # --- Lot 9: filosofia clàssica que faltava (OCR d'Internet Archive; la neteja
    # del soroll OCR/aparat es refinarà mirant /api/sample després del 1r ingest) ---
    ("capitalcriticala00marxrich", "capitalcriticala00marxrich_djvu.txt",
     "Karl Marx", "Capital, Vol. I: A Critical Analysis of Capitalist Production",
     "English", "Complete work", "Written by the author",
     "Obra magna de Marx (1867); traducció anglesa de Samuel Moore i Edward Aveling "
     "(1887, supervisada per Engels), no l'alemany original. Digitalització OCR.",
     "Karl_Marx__Capital_Vol1_Moore_Aveling_en.txt"),
    ("treatiseonrhetor00arisuoft", "treatiseonrhetor00arisuoft_djvu.txt",
     "Aristotle", "Rhetoric (Treatise on Rhetoric)", "English",
     "Complete work", "Written by the author",
     "Retòrica d'Aristòtil; traducció anglesa de Theodore Buckley (Bohn, 1906), no el "
     "grec original. Digitalització OCR; l'edició porta aparat escolar (anàlisi de "
     "Hobbes, preguntes d'examen, apèndix grec) que caldrà netejar després.",
     "Aristotle__Rhetoric_Buckley_en.txt"),
    ("ciceroonoratory00cicegoog", "ciceroonoratory00cicegoog_djvu.txt",
     "Cicero", "De Oratore (On Oratory and Orators)", "English",
     "Complete work", "Written by the author",
     "De Oratore de Ciceró; traducció de J. S. Watson (Bohn, 1878), no el llatí "
     "original. El volum inclou també Brutus i Orator (que ja són al corpus). "
     "Digitalització OCR.",
     "Cicero__De_Oratore_Watson_en.txt"),

    # --- Lot 10: forats verificats (djvu + edició PD comprovats via metadata) ---
    # Ciceró: l'únic PD que conté De divinatione + De legibus és el volum Bohn de
    # Yonge; ATENCIÓ: també reinclou De natura deorum / De fato / De re publica
    # (que ja són al corpus) -> duplicació acceptada per tenir Div. + Lleis.
    ("treatisescicero00ciceuoft", "treatisescicero00ciceuoft_djvu.txt",
     "Cicero",
     "On Divination and On the Laws (Yonge Treatises of Cicero)", "English",
     "Complete work", "Written by the author",
     "Volum Bohn amb De Divinatione i De Legibus (el motiu d'afegir-lo); traducció "
     "de C. D. Yonge (1853), no el llatí original. El volum també conté De natura "
     "deorum, De fato i De re publica, que ja són al corpus (duplicació). OCR.",
     "Cicero__Divination_Laws_Yonge_en.txt"),
    # Kant: original alemany PD (l'anglès tardà té copyright). Edició Kirchmann
    # (Philosophische Bibliothek, 1880, tipografia Antiqua -> OCR net esperat).
    ("anthropologieinp00kant", "anthropologieinp00kant_djvu.txt",
     "Kant", "Anthropologie in pragmatischer Hinsicht (German)", "German",
     "Complete work", "Written by the author",
     "Antropologia de Kant; original alemany (ed. J. H. von Kirchmann, 1880), en "
     "domini públic. Digitalització OCR; verificar el cos després de l'ingest.",
     "Kant__Anthropologie_Kirchmann_de.txt"),

    # --- Lot 11: deep-cuts via ORIGINAL (l'anglès modern té copyright) ---
    # Marx "La misèria de la filosofia": original FRANCÈS (1847; ed. 1896). El va
    # escriure en francès; l'anglès PD net no apareix. Francès s'indexa bé:
    ("misredelaphilo00marxuoft", "misredelaphilo00marxuoft_djvu.txt",
     "Karl Marx", "Misère de la philosophie (The Poverty of Philosophy)", "French",
     "Complete work", "Written by the author",
     "Resposta de Marx a Proudhon; original francès (1847; ed. 1896), domini públic "
     "(l'anglès està protegit per drets). Digitalització OCR.",
     "Karl_Marx__Misere_de_la_philosophie_fr.txt"),
    # Kant "El conflicte de les facultats": original ALEMANY (Reclam). El cos és
    # Antiqua llegible; la portada porta soroll d'OCR (es neteja en part):
    ("11891496bsb", "11891496bsb_djvu.txt",
     "Kant", "Der Streit der Fakultäten (The Conflict of the Faculties)", "German",
     "Complete work", "Written by the author",
     "El conflicte de les facultats; original alemany (Reclam), domini públic. Cos "
     "en Antiqua llegible; la portada té soroll d'OCR. Digitalització OCR.",
     "Kant__Streit_der_Fakultaeten_de.txt"),

    # --- Lot 12: El Capital, Vols. II i III (completen l'obra; tr. Untermann, Kerr, PD) ---
    ("capitalcritiqueo02marxiala", "capitalcritiqueo02marxiala_djvu.txt",
     "Karl Marx", "Capital, Vol. II: The Process of Circulation of Capital", "English",
     "Complete work", "Written by the author",
     "Volum II d'El Capital (editat per Engels); traducció anglesa d'Ernest Untermann "
     "(Kerr, 1907), no l'alemany original. Digitalització OCR (llibre llarg).",
     "Karl_Marx__Capital_Vol2_Untermann_en.txt"),
    ("capitalcritiqueo03marx", "capitalcritiqueo03marx_djvu.txt",
     "Karl Marx", "Capital, Vol. III: The Process of Capitalist Production as a Whole",
     "English", "Complete work", "Written by the author",
     "Volum III d'El Capital (editat per Engels); traducció anglesa d'Ernest Untermann "
     "(Kerr, 1909), no l'alemany original. Digitalització OCR (llibre llarg).",
     "Karl_Marx__Capital_Vol3_Untermann_en.txt"),

    # --- Lot 13: cluster B, autors PD només en OCR/anglès d'època ---
    ("worksofphilojuda01yonguoft", "worksofphilojuda01yonguoft_djvu.txt",
     "Philo of Alexandria", "The Works of Philo Judaeus, Vol. I (Yonge)", "English",
     "Selection / partial", "Written by the author",
     "Obres del filòsof jueu-hel·lenístic Filó d'Alexandria (s. I); traducció de "
     "C. D. Yonge (Bohn), no el grec original. Volum I de IV. Digitalització OCR.",
     "Philo__Works_Vol1_Yonge_en.txt"),
    ("enquiryconcernin01godw", "enquiryconcernin01godw_djvu.txt",
     "William Godwin", "An Enquiry Concerning Political Justice, Vol. I", "English",
     "Selection / partial", "Written by the author",
     "Obra precursora de l'anarquisme filosòfic de William Godwin (1793); anglès "
     "d'època, domini públic. Volum I. Digitalització OCR (ortografia antiga).",
     "William_Godwin__Political_Justice_Vol1_en.txt"),

    # --- Lot 14: col·lecció de hadís més àmplia (el Lane-Poole no recull les
    # pràctiques; aquesta cobreix oració/almoina/dejuni/peregrinació -> el bot pot
    # respondre què són els "cinc pilars" per síntesi). Autor "Hadith" perquè entri
    # al clúster de tradició islàmica del retrieval. OCR verificat net. ---
    ("muhammadinhadees0000abul", "muhammadinhadees0000abul_djvu.txt",
     "Hadith", "Muhammad in the Hadees: Sayings of the Prophet (Mirza Abu'l-Fadl)",
     "English", "Selection / partial", "Recorded/compiled by others",
     "Recull de dites del Profeta Mahoma (hadís) compilat i traduït a l'anglès per "
     "Mirza Abu'l-Fadl (principis del s. XX), en domini públic; no l'àrab original. "
     "Cobreix les pràctiques centrals (oració, almoina, dejuni, peregrinació). "
     "Digitalització OCR.",
     "Hadith__Muhammad_in_the_Hadees_AbulFadl_en.txt"),

    # --- Lot 15: Hegel i Weber (OCR Archive.org; edicions PD verificades) ---
    # Hegel mort 1831 -> PD. Baillie (1910) i Dyde (1896): translators PD.
    # Weber mort 1920 -> PD. Original alemany 1919.
    ("phenomenologyofm02hege", "phenomenologyofm02hege_djvu.txt",
     "Hegel", "The Phenomenology of Mind (Baillie)", "English",
     "Complete work", "Written by the author",
     "Obra central de Hegel (Phänomenologie des Geistes, 1807); traducció anglesa "
     "de J. B. Baillie (1910), domini públic. Digitalització OCR.",
     "Hegel__Phenomenology_of_Mind_Baillie_en.txt"),
    ("in.ernet.dli.2015.36249", "2015.36249.Hegel--S-Philosophy-Of-Right_djvu.txt",
     "Hegel", "Philosophy of Right (Grundlinien der Philosophie des Rechts)",
     "English", "Complete work", "Written by the author",
     "Filosofia del dret de Hegel (1820); traducció anglesa de S. W. Dyde (1896), "
     "domini públic. Digitalització OCR.",
     "Hegel__Philosophy_of_Right_Dyde_en.txt"),
    ("politikalsberuf00webe", "politikalsberuf00webe_djvu.txt",
     "Max Weber", "Politik als Beruf (Politics as a Vocation)", "German",
     "Complete work", "Written by the author",
     "Conferència de Weber sobre la política com a vocació (Munich, 1919); original "
     "alemany en domini públic. Digitalització OCR.",
     "Weber__Politik_als_Beruf_de.txt"),

    # --- Lot 16: Durkheim (originals francesos PD) + Freud (GW XIII alemany PD) ---
    # Durkheim mort 1917 -> PD. Weber Wissenschaft: conferenciad 1917, pub. 1919, PD.
    # Freud mort 1939 -> PD a EU des del 2010. GW XIII (1923): ed. pòstuma 1940, PD.
    ("deladivisiondutr00durkuoft", "deladivisiondutr00durkuoft_djvu.txt",
     "Emile Durkheim", "De la division du travail social (1893)", "French",
     "Complete work", "Written by the author",
     "Tesi doctoral i primera obra major de Durkheim (1893); original francès en domini "
     "públic (la traducció anglesa de 1984 no ho és). Digitalització OCR.",
     "Durkheim__De_la_division_du_travail_social_fr.txt"),
    ("lesrglesdelam00durkuoft", "lesrglesdelam00durkuoft_djvu.txt",
     "Emile Durkheim", "Les Règles de la méthode sociologique (1895)", "French",
     "Complete work", "Written by the author",
     "Manifesto metodològic de Durkheim (1895); original francès en domini públic. "
     "Digitalització OCR (edició de 1919).",
     "Durkheim__Les_Regles_de_la_methode_sociologique_fr.txt"),
    ("max-weber-1919-wissenschaft-als-beruf",
     "Max Weber (1919) Wissenschaft als Beruf_djvu.txt",
     "Max Weber", "Wissenschaft als Beruf (Science as a Vocation)", "German",
     "Complete work", "Written by the author",
     "Conferència de Weber sobre la ciència com a vocació (Munich, 1917; pub. 1919); "
     "original alemany en domini públic. Digitalització OCR.",
     "Weber__Wissenschaft_als_Beruf_de.txt"),
    ("freud-1940-gw-13", "Freud_1940_GW_13_djvu.txt",
     "Sigmund Freud",
     "Das Ich und das Es / Jenseits des Lustprinzips / Massenpsychologie (GW XIII)",
     "German", "Complete work", "Written by the author",
     "Gesammelte Werke Band XIII: 'Das Ich und das Es' (1923), 'Jenseits des Lustprinzips' "
     "(1920) i 'Massenpsychologie und Ich-Analyse' (1921); originals alemanys en domini "
     "públic (Freud mort 1939). Digitalització OCR.",
     "Freud__GW_XIII_Ich_Lustprinzip_Massen_de.txt"),

    # --- Lot 17: Locke (obres que faltaven), Agustí (De Trinitate + De Doctrina)
    # i Rousseau Reveries (tot PD) ---
    # Locke mort 1704 -> PD. Edinburgh Works ed. 1821: PD. Some Thoughts 1902 ed.: PD.
    # Agustí mort 430 dC; traduccions s. XIX: PD. Rousseau mort 1778 -> PD.
    ("twotreatisesofg00lockuoft", "twotreatisesofg00lockuoft_djvu.txt",
     "Locke", "Two Treatises of Government (First and Second)", "English",
     "Complete work", "Written by the author",
     "Edició de 1821 que conté TOTS DOS tractats: el Primer (contra Filmer) i el Segon "
     "(teoria liberal del govern civil). Domini públic. El Segon Tractat ja és al corpus "
     "per separat; el Primer Tractat és nou. Digitalització OCR.",
     "Locke__Two_Treatises_of_Government_en.txt"),
    ("somethoughtscon05lockgoog", "somethoughtscon05lockgoog_djvu.txt",
     "Locke", "Some Thoughts Concerning Education (1902)", "English",
     "Complete work", "Written by the author",
     "Tractat pedagògic de John Locke (1693); edició de 1902, domini públic. "
     "Digitalització OCR (Google Books, tipografia romana llegible).",
     "Locke__Some_Thoughts_Concerning_Education_en.txt"),
    ("worksofaureliu07augu", "worksofaureliu07augu_djvu.txt",
     "Augustine", "On the Trinity (De Trinitate)", "English",
     "Complete work", "Written by the author",
     "Volum 7 de les Obres d'Aureli Agustí (T&T Clark, Edinburgh, 1871); traducció anglesa "
     "de Marcus Dods, domini públic. Conté el De Trinitate sencer. Digitalització OCR.",
     "Augustine__On_the_Trinity_Dods_en.txt"),
    ("aselectlibraryn02augugoog", "aselectlibraryn02augugoog_djvu.txt",
     "Augustine",
     "On Christian Doctrine / City of God (NPNF First Series Vol. 2)", "English",
     "Complete work", "Written by the author",
     "NPNF vol. 2 (Schaff/Dods, Eerdmans, 1908): conté 'De Doctrina Christiana' (De la "
     "doctrina cristiana) i la Ciutat de Déu. La Ciutat de Déu ja és al corpus (duplicació "
     "acceptada; el motiu d'afegir-lo és De Doctrina Christiana). Digitalització OCR.",
     "Augustine__NPNF_Vol2_City_of_God_Christian_Doctrine_en.txt"),
    ("dli.ministry.22007", "E13534_The_reveries_Of_A_Solitary_djvu.txt",
     "Rousseau", "Reveries of the Solitary Walker (Fletcher, Routledge)", "English",
     "Complete work", "Written by the author",
     "Traducció anglesa de John Gould Fletcher (ed. Routledge, 'Broadway Library of "
     "XVIII Century French Literature', ~1927), domini públic als EUA (copyright no "
     "renovat). Original de Rousseau (pòstum, 1782). Digitalització OCR (DLI).",
     "Rousseau__Reveries_of_the_Solitary_Walker_Fletcher_en.txt"),

    # --- Lot 18: Leibniz en anglès (Open Court, 1902; PD) ---
    # Leibniz mort 1716 -> PD. Traducció de 1902 (Open Court, La Salle, IL): PD als EUA.
    # Conté: Discourse on Metaphysics (nou) + Correspondence with Arnauld (nou) +
    # Monadology en anglès (complement de la Monadologie alemanya que ja és al corpus).
    ("discourseonmetap00leib2", "discourseonmetap00leib2_djvu.txt",
     "Leibniz",
     "Discourse on Metaphysics, Correspondence with Arnauld, and Monadology (1902)",
     "English", "Complete work", "Written by the author",
     "Tres obres filosòfiques de Leibniz (1686-1714): el Discurs de Metafísica, "
     "la correspondència amb Arnauld i la Monadologia; traducció anglesa (Open Court, "
     "1902), domini públic. La Monadologia en alemany ja és al corpus. OCR.",
     "Leibniz__Discourse_Arnauld_Monadology_en.txt"),

    # --- Lot 19: escolàstica espanyola, pensament conservador i hispànic s. XVII-XX ---
    # Vitoria mort 1546 -> PD. Trad. J.P. Bate per Carnegie Endowment, 1917: PD.
    # Donoso Cortés mort 1853 -> PD. Ed. original 1851: PD.
    # Gracián mort 1658 -> PD. Ed. 1900 (Farinelli) i ed. 1669: PD.
    # Unamuno mort 1936 -> PD a EU des del 2007; ed. 1933: PD.
    # Feijóo mort 1764 -> PD. Ed. 1773: PD.
    ("franciscidevicto0000vito", "franciscidevicto0000vito_djvu.txt",
     "Francisco de Vitoria",
     "De Indis et De iure belli relectiones (Carnegie Classics, Bate tr., 1917)",
     "English", "Complete work", "Written by the author",
     "Dues relectiones de Vitoria (1532): 'De Indis' (sobre el dret a la conquesta d'Amèrica) "
     "i 'De iure belli' (sobre el dret de guerra); text llatí amb traducció anglesa de J. P. Bate "
     "(Carnegie Endowment for International Peace, 1917), domini públic. OCR.",
     "Francisco_de_Vitoria__De_Indis_De_iure_belli_Bate_en.txt"),
    ("ensayo-sobre-el-catolicismo-el-liberalismo-y-el-socialismo",
     "Ensayo sobre el catolicismo, el liberalismo y el socialismo_djvu.txt",
     "Juan Donoso Cortes",
     "Ensayo sobre el catolicismo, el liberalismo y el socialismo (1851)",
     "Spanish", "Complete work", "Written by the author",
     "Obra mestra del pensament conservador catòlic de Donoso Cortés (1851); "
     "edició original en castellà, domini públic. OCR.",
     "Juan_Donoso_Cortes__Ensayo_catolicismo_liberalismo_socialismo_es.txt"),
    ("elhroeeldiscreto00grac", "elhroeeldiscreto00grac_djvu.txt",
     "Baltasar Gracian", "El Héroe; El Discreto (Farinelli, 1900)", "Spanish",
     "Complete work", "Written by the author",
     "Dos tractats morals de Gracián: 'El Héroe' (1637, model de l'home d'excepció) i "
     "'El Discreto' (1646, prudència i discreció); ed. d'Arturo Farinelli (1900), PD. OCR.",
     "Baltasar_Gracian__El_Heroe_El_Discreto_es.txt"),
    ("bub_gb_SmBLAAAAcAAJ", "bub_gb_SmBLAAAAcAAJ_djvu.txt",
     "Baltasar Gracian",
     "Agudeza y arte de ingenio; Oráculo manual y arte de prudencia (1669)",
     "Spanish", "Complete work", "Written by the author",
     "Edició de 1669 (A. Lacavallerìa, Barcelona) que conté dues obres de Gracián: "
     "'Agudeza y arte de ingenio' (1648, teoria de l'enginy i l'estil) i "
     "'Oráculo manual' (1647, aforismes de prudència i saviesa pràctica). "
     "Tipografia del s. XVII: l'OCR pot contenir soroll (s llarga, lligadures). "
     "Domini públic.",
     "Baltasar_Gracian__Agudeza_Oraculo_1669_es.txt"),
    ("san-manuel-bueno-martir-unamuno",
     "San Manuel Bueno mártir, Unamuno_djvu.txt",
     "Miguel de Unamuno", "San Manuel Bueno, mártir (1933)", "Spanish",
     "Complete work", "Written by the author",
     "Novel·la breu d'Unamuno (1931); edició de 1933, domini públic (CC Public Domain Mark). "
     "Tema central: la fe com a necessitat vital, el dubte i el fingiment del creient. OCR.",
     "Miguel_de_Unamuno__San_Manuel_Bueno_martir_es.txt"),
    ("laagoniadelcrist0000unam", "laagoniadelcrist0000unam_djvu.txt",
     "Miguel de Unamuno", "La agonía del cristianismo (1986 ed.)", "Spanish",
     "Complete work", "Written by the author",
     "Assaig teològic d'Unamuno (escrit en francès 1924, pub. esp. 1931); ed. 1986 Alianza. "
     "Text de l'autor en domini públic (mort 1936); la descàrrega pot fallar si l'ed. és CDL. "
     "OCR.",
     "Miguel_de_Unamuno__La_agonia_del_cristianismo_es.txt"),
    ("b30532139_0001", "b30532139_0001_djvu.txt",
     "Benito Feijoo",
     "Cartas eruditas y curiosas, Vol. I (1773)", "Spanish",
     "Selection / partial", "Written by the author",
     "Primer volum de les Cartes erudites de Feijóo (1742-1760); ed. 1773, CC Public Domain. "
     "Complement del Teatro crítico universal. OCR (Tesseract, es).",
     "Benito_Feijoo__Cartas_eruditas_Vol1_es.txt"),

    # --- Lot 20: textos papals patrístics i clàssics (OCR Archive.org; PD) ---
    # Climent I (~96 dC), Lleó I (mort 461), Gregori I (mort 604), Pius V (mort 1572) -> PD.
    # Traduccions del s. XIX: Chevallier 1846, NPNF 1895, Bliss 1844 -> PD.
    # NOTA: els reculls multi-autor del fitxer de Climent (Chevallier: Climent +
    # Policarp + Ignasi + Justí) i del NPNF Vol.12 (Lleó I + Gregori I) NO van aquí:
    # es parteixen per autor a SPLIT_TEXTS (vegeu més avall) per no atribuir l'obra
    # d'un autor a un altre.
    ("moralsonbookofj01greg", "moralsonbookofj01greg_djvu.txt",
     "Gregory I",
     "Moralia in Job (Morals on the Book of Job), Vol. I",
     "English", "Complete work", "Written by the author",
     "Magna Moralia de Gregori I el Gran (~578-595 dC), comentari moral sobre Job; "
     "traducció de James Bliss (Oxford: Parker, 1844). Vol. I. PD. OCR.",
     "Gregory_I__Moralia_in_Job_Vol1_Bliss_en.txt"),
    ("moralsonbookofj02greg", "moralsonbookofj02greg_djvu.txt",
     "Gregory I",
     "Moralia in Job (Morals on the Book of Job), Vol. II",
     "English", "Complete work", "Written by the author",
     "Magna Moralia de Gregori I el Gran; traducció James Bliss (Oxford: Parker, 1844). "
     "Vol. II. PD. OCR.",
     "Gregory_I__Moralia_in_Job_Vol2_Bliss_en.txt"),
    ("moralsonbookofj03greg", "moralsonbookofj03greg_djvu.txt",
     "Gregory I",
     "Moralia in Job (Morals on the Book of Job), Vol. III",
     "English", "Complete work", "Written by the author",
     "Magna Moralia de Gregori I el Gran; traducció James Bliss (Oxford: Parker, 1844). "
     "Vol. III. PD. OCR.",
     "Gregory_I__Moralia_in_Job_Vol3_Bliss_en.txt"),
    ("PopeSt.GregoryTheGreatDialogues", "Pope St. Gregory the Great - Dialogues_djvu.txt",
     "Gregory I",
     "Dialogi de vita et miraculis patrum Italicorum",
     "English", "Complete work", "Written by the author",
     "Diàlegs de Gregori I (~593-94 dC) sobre les vides i miracles dels sants italians; "
     "inclou la vida de Sant Benet (Diàleg II, font principal sobre la Regla Benedictina). "
     "Traducció anglesa PD. OCR d'Archive.org.",
     "Gregory_I__Dialogi_en.txt"),
    ("catechism-of-the-council-of-trent", "Catechism_of_the_Council of_Trent_djvu.txt",
     "Pius V",
     "Catechismus Romanus ad Parochos (Catechism of the Council of Trent)",
     "English", "Complete work", "Written by the author",
     "Catecisme Romà (1566) encarregat per Pius V per implementar els decrets "
     "del Concili de Trento (1545-63); síntesi doctrinal catòlica posconciliar "
     "i manual estàndard per als capellans catòlics durant segles. Traducció anglesa PD. OCR.",
     "Pius_V__Catechismus_Romanus_en.txt"),

    # --- Lot 21: textos papals en llatí (edicions PD) ---
    # Innocenci III (1194-95, com a cardenal Lotario dei Conti) -> PD.
    # Ed. crít. Achterfeldt 1855: PD.
    # NOTA: Nicolau I / PL 119 (patrologiaecursu0119mign) RETIRAT: un volum de la
    # Patrologia Latina és una compilació de MOLTS autors, no atribuïble a un sol papa
    # (atribució incorrecta). La Responsa ad consulta Bulgarorum es pot re-incorporar
    # més endavant des d'una font d'un sol text. Tret també de la BD via cleanup.py.
    ("decontemptumund00achtgoog", "decontemptumund00achtgoog_djvu.txt",
     "Innocent III",
     "De miseria humanae conditionis (De contemptu mundi)",
     "Latin", "Complete work", "Written by the author",
     "Tractat de Lotario dei Conti (futur Innocenci III) escrit ~1194-95 sobre la misèria "
     "de la condició humana; un dels textos medievals més difosos. "
     "Ed. crítica J. H. Achterfeldt (Bonn, 1855), text llatí complet. OCR.",
     "Innocent_III__De_miseria_humanae_conditionis_la.txt"),

    # --- Lot 22: Reforma Protestant - textos no disponibles a Gutenberg ---
    # Zwingli mort 1531 -> PD. Ed. Jackson 1901 (U. of Pennsylvania): PD.
    # Luther "On the Jews..." (1543) -> PD. Avís de contingut discriminatori obligatori.
    ("huldreichzwingli00jackuoft", "huldreichzwingli00jackuoft_djvu.txt",
     "Ulrich Zwingli",
     "Selected Works of Huldreich Zwingli (1484-1531)",
     "English", "Selection / partial", "Written by the author",
     "Selecció d'obres d'Ulric Zwingli (ed. Samuel Macaulay Jackson, University of "
     "Pennsylvania, 1901), domini públic; conté texts clau de la Reforma Suïssa "
     "(escrits sobre reforma eclesiàstica, providència divina, sagraments). OCR.",
     "Ulrich_Zwingli__Selected_Works_en.txt"),
    ("OnTheJewsAndTheirLiesMartinLuther1543",
     "On the Jews and Their Lies, Martin Luther (1543)_djvu.txt",
     "Martin Luther",
     "On the Jews and Their Lies (Von den Juden und ihren Lügen, 1543)",
     "English", "Complete work", "Written by the author",
     "Tractat antisemita violent de Martí Luter (1543): proposa cremar sinagogues, "
     "confiscar béns i expulsar els jueus d'Alemanya. Va ser citat directament per "
     "la propaganda nazi. Repudiat formalment per la Federació Luterana Mundial "
     "(LWF) el 2015. Inclòs únicament per al seu valor historiogràfic i per a la "
     "comprensió crítica de l'antisemitisme cristià precursor. Trad. anglesa PD. OCR.",
     "Martin_Luther__On_the_Jews_and_Their_Lies_en.txt"),

    # --- Lot 23: buits canònics d'autors majors (auditoria de cobertura) ---
    # Tots amb traducció en DOMINI PÚBLIC verificada. Fonts no disponibles a Gutenberg.
    ("philosophyofhist00hegerich", "philosophyofhist00hegerich_djvu.txt",
     "Hegel", "The Philosophy of History (Lectures, Sibree)", "English",
     "Complete work", "Recorded/compiled by others",
     "Lliçons sobre la filosofia de la història de G. W. F. Hegel (impartides 1822-31, "
     "publicades pòstumament): la història universal entesa com el desplegament racional "
     "de la llibertat de l'esperit. Traducció anglesa de J. Sibree (revisió de 1899, "
     "Colonial Press), domini públic, no l'alemany original. Lliçons recollides i "
     "editades pels deixebles a partir dels apunts de Hegel. OCR d'Archive.org.",
     "Hegel__Philosophy_of_History_Sibree_en.txt"),
    ("in.ernet.dli.2015.185285", "2015.185285.Aristotle-The-Organon_djvu.txt",
     "Aristotle",
     "The Organon (Categories, On Interpretation, Prior & Posterior Analytics, Topics, Sophistical Refutations)",
     "English", "Complete work", "Written by the author",
     "Els sis tractats de lògica d'Aristòtil (l'Organon) en un sol volum; traducció "
     "d'Octavius Freire Owen (Bohn's Classical Library, 1853), domini públic, no el grec "
     "original. Aporta els Primers Analítics, De la Interpretació, els Tòpics i les "
     "Refutacions sofístiques, que faltaven al corpus. OCR d'Archive.org.",
     "Aristotle__The_Organon_Owen_en.txt"),
    ("in.ernet.dli.2015.183335", "2015.183335.Aristotle-The-Physics-Vol-i_djvu.txt",
     "Aristotle", "The Physics, Vol. I (Books I-IV)", "English",
     "Complete work", "Written by the author",
     "La Física d'Aristòtil, vol. I (llibres I-IV): la naturalesa, les quatre causes, "
     "el moviment, l'infinit, el lloc, el buit i el temps. Traducció de P. H. Wicksteed "
     "i F. M. Cornford (Loeb, 1929), no el grec original; tradudors morts fa més de 70 "
     "anys (domini públic a la UE). OCR d'Archive.org.",
     "Aristotle__Physics_Vol1_en.txt"),
    ("in.ernet.dli.2015.183610", "2015.183610.Aristotle-The-Physics-Voll-Ii_djvu.txt",
     "Aristotle", "The Physics, Vol. II (Books V-VIII)", "English",
     "Complete work", "Written by the author",
     "La Física d'Aristòtil, vol. II (llibres V-VIII): el canvi, el continu i el primer "
     "motor immòbil. Traducció de Wicksteed i Cornford (Loeb, 1934), no el grec original. "
     "Domini públic a la UE (tradudors +70 anys); als EUA no és PD fins al 2030. OCR.",
     "Aristotle__Physics_Vol2_en.txt"),
    ("OfGodAndHisCreatures", "OfGodAndHisCreatures_djvu.txt",
     "Thomas Aquinas", "Of God and His Creatures (Summa Contra Gentiles)", "English",
     "Selection / partial", "Written by the author",
     "Summa Contra Gentiles de Tomàs d'Aquino (1259-65), la seva segona gran síntesi: "
     "defensa racional de la fe cristiana davant dels no-creients, sobre Déu, la creació, "
     "la providència i la fi última de l'home. Traducció anotada de Joseph Rickaby (1905), "
     "domini públic; és una traducció amb cert abreujament (no íntegra). OCR d'Archive.org.",
     "Thomas_Aquinas__Summa_Contra_Gentiles_Rickaby_en.txt"),

    # --- Lot 24: tram Mitjà (Hobbes i Spencer) — edicions autònomes amb títol clar ---
    ("cu31924028063893", "cu31924028063893_djvu.txt",
     "Thomas Hobbes", "Behemoth; or, The Long Parliament", "English",
     "Complete work", "Written by the author",
     "Behemoth (escrit ~1668, publicat 1681) de Thomas Hobbes: anàlisi de les causes "
     "de la Guerra Civil anglesa (1640-60) en forma de diàleg, on aplica la seva teoria "
     "política a un cas històric concret. Text original anglès, domini públic. OCR d'Archive.org.",
     "Thomas_Hobbes__Behemoth_en.txt"),
    ("manversusstate00spen", "manversusstate00spen_djvu.txt",
     "Herbert Spencer", "The Man versus the State", "English",
     "Complete work", "Written by the author",
     "L'home contra l'Estat (1884) de Herbert Spencer: assaigs (incl. 'The New Toryism', "
     "'The Coming Slavery', 'The Sins of Legislators') que defensen el liberalisme "
     "individualista i critiquen l'expansió de l'Estat. Text original anglès, domini públic. OCR.",
     "Herbert_Spencer__Man_versus_the_State_en.txt"),

    # --- Lot 25: obres angleses de Montesquieu (només teníem el francès; els
    # antics "..._en" eren stubs-índex de Wikisource, trets per remove_stubs.sh).
    # Nugent mort 1772, Davidson mort 1909 -> traduccions en domini públic. ---
    ("spiritoflaws01montuoft", "spiritoflaws01montuoft_djvu.txt",
     "Montesquieu", "The Spirit of Laws, Volume 1", "English",
     "Complete work", "Written by the author",
     "L'esperit de les lleis (1748) de Montesquieu, vol. I; traducció anglesa de "
     "Thomas Nugent (ed. Colonial Press, 1899), domini públic. Complementa l'Esprit "
     "des lois francès ja present. Digitalització OCR.",
     "Montesquieu__The_Spirit_of_Laws_Volume_1_en.txt"),
    ("spiritoflaws02montuoft", "spiritoflaws02montuoft_djvu.txt",
     "Montesquieu", "The Spirit of Laws, Volume 2", "English",
     "Complete work", "Written by the author",
     "L'esperit de les lleis (1748) de Montesquieu, vol. II; traducció anglesa de "
     "Thomas Nugent (ed. Colonial Press, 1899), domini públic. Digitalització OCR.",
     "Montesquieu__The_Spirit_of_Laws_Volume_2_en.txt"),
    ("in.ernet.dli.2015.97067", "2015.97067.Montesquieu-Persian-Letters_djvu.txt",
     "Montesquieu", "Persian Letters", "English",
     "Complete work", "Written by the author",
     "Cartes perses (1721) de Montesquieu: novel·la epistolar (161 cartes) de crítica "
     "social i política; traducció anglesa de John Davidson (1891), domini públic. "
     "Complementa les Lettres persanes franceses ja presents. Digitalització OCR.",
     "Montesquieu__Persian_Letters_Davidson_en.txt"),

    # --- Lot 26: omplir forats d'autors (obres canòniques que faltaven, totes PD) ---
    ("proslogiummonol00deangoog", "proslogiummonol00deangoog_djvu.txt",
     "Anselm of Canterbury", "Proslogium, Monologium, and Cur Deus Homo (Deane)", "English",
     "Complete work", "Written by the author",
     "Obres principals d'Anselm de Canterbury (s. XI): Proslogium (argument ontològic), "
     "Monologium, l'apèndix de Gaunilo i Cur Deus Homo (per què Déu es va fer home); "
     "traducció anglesa de Sidney Norton Deane (1903), domini públic. Digitalització OCR.",
     "Anselm_of_Canterbury__Proslogium_Monologium_Cur_Deus_Homo_Deane_en.txt"),
    ("studyofsociology12spenuoft", "studyofsociology12spenuoft_djvu.txt",
     "Herbert Spencer", "The Study of Sociology", "English",
     "Complete work", "Written by the author",
     "L'estudi de la sociologia (1873) de Herbert Spencer: el mètode, els biaixos i les "
     "dificultats de la ciència social. Original anglès, domini públic. Digitalització OCR.",
     "Herbert_Spencer__The_Study_of_Sociology_en.txt"),
    ("cu31924077682825", "cu31924077682825_djvu.txt",
     "Herbert Spencer", "Social Statics", "English",
     "Complete work", "Written by the author",
     "Social Statics (1851) de Herbert Spencer: les condicions per a la felicitat humana "
     "i la llei de la igual llibertat. Original anglès, domini públic. Digitalització OCR.",
     "Herbert_Spencer__Social_Statics_en.txt"),

    # --- Lot 27: reforçar autors prims amb obres canòniques que faltaven (totes PD) ---
    ("newessaysconcern00leibuoft", "newessaysconcern00leibuoft_djvu.txt",
     "Leibniz", "New Essays Concerning Human Understanding", "English",
     "Complete work", "Written by the author",
     "Resposta de Leibniz a l'Assaig de Locke (obra major, publicada pòstumament): "
     "defensa de les idees innates i de l'apercepció. Traducció d'Alfred G. Langley "
     "(1896), domini públic. Digitalització OCR.",
     "Leibniz__New_Essays_Concerning_Human_Understanding_Langley_en.txt"),
    ("alciphron00berk", "alciphron00berk_djvu.txt",
     "George Berkeley", "Alciphron, or the Minute Philosopher", "English",
     "Complete work", "Written by the author",
     "Sèrie de diàlegs (1732) de George Berkeley en defensa de la religió cristiana "
     "contra els lliurepensadors ('minute philosophers'); inclou la seva teoria del "
     "llenguatge i dels signes. Original anglès, domini públic. Digitalització OCR.",
     "George_Berkeley__Alciphron_en.txt"),

    # --- Lot 28: reforçar autors prims (anarquistes/socialistes), totes PD verificades ---
    ("reflectionsonvio00soreuoft", "reflectionsonvio00soreuoft_djvu.txt",
     "Georges Sorel", "Reflections on Violence", "English",
     "Complete work", "Written by the author",
     "Assaig de Georges Sorel (1908) sobre el paper de la vaga general revolucionària "
     "i el mite social; obra fundacional del sindicalisme revolucionari. Traducció "
     "anglesa de T. E. Hulme (1915; Hulme va morir el 1917 -> domini públic). "
     "Digitalització OCR.",
     "Georges_Sorel__Reflections_on_Violence_Hulme_en.txt"),
    ("memoirsofrevolut00krop_1", "memoirsofrevolut00krop_1_djvu.txt",
     "Peter Kropotkin", "Memoirs of a Revolutionist", "English",
     "Complete work", "Written by the author",
     "Autobiografia de Piotr Kropotkin (1899), escrita originalment en anglès per a "
     "The Atlantic Monthly; recorre la seva vida com a científic, geògraf i "
     "revolucionari anarquista. Original anglès, domini públic (Kropotkin †1921). "
     "Digitalització OCR.",
     "Peter_Kropotkin__Memoirs_of_a_Revolutionist_en.txt"),

    # --- Lot 30: obra en idioma ORIGINAL quan la traducció anglesa no és PD/lliure ---
    ("philosophiederzu00feue", "philosophiederzu00feue_djvu.txt",
     "Ludwig Feuerbach", "Grundsätze der Philosophie der Zukunft", "German",
     "Complete work", "Written by the author",
     "Principis de la filosofia del futur (1843) de Feuerbach: crítica de l'idealisme "
     "hegelià i fonamentació del materialisme antropològic. Alemany original (les "
     "traduccions angleses modernes no són PD; Feuerbach †1872 -> l'original sí). "
     "Digitalització OCR.",
     "Ludwig_Feuerbach__Grundsaetze_der_Philosophie_der_Zukunft_de.txt"),
]


# Fitxers que contenen DIVERSES obres/autors i s'han de PARTIR en fitxers separats
# (si no, tots els chunks s'atribueixen a un sol autor -> atribució incorrecta).
# El tall és per MARCADORS DE TEXT (incipits/títols) verificats localment contra el
# text NET (clean_ocr); com que el VPS baixa el mateix fitxer, el tall és reproduïble.
# Cada secció va del seu marcador fins al marcador següent (l'última fins a end_marker,
# o fins al final si és None). El text abans del 1r marcador (front matter editorial)
# i a partir d'end_marker (índex final) es descarta.
#   (identifier, djvu, language, end_marker|None,
#    [ (start_marker, author, work, completeness, authorship, note, out_filename), ... ])
SPLIT_TEXTS = [
    # Recull de Chevallier (1846): Climent + Policarp + Ignasi + Justí. Només ~25% és
    # de Climent; es parteix pels incipits de cada obra (verificats; marcadors únics
    # en ordre de document; Ignasi reutilitza "Theophorus" a cada carta -> s'agafa la 1a).
    ("TranslationOfTheEpistlesOfClement", "TranslationOfTheEpistlesOfClement_djvu.txt",
     "English", "INDEX.", [
        ("Church of God which is at Rome",
         "Clement I", "Epistle to the Corinthians (1 Clement)",
         "Complete work", "Written by the author",
         "1a Carta de Climent de Roma als Corintis (~96 dC); trad. anglesa de T. Chevallier "
         "(1846), domini públic. OCR. Separada del recull patrístic original (un sol autor).",
         "Clement_I__Epistle_to_the_Corinthians_en.txt"),
        ("Polycarp, and the Presbyters that are with him",
         "Polycarp", "Epistle to the Philippians",
         "Complete work", "Written by the author",
         "Carta de Policarp d'Esmirna als Filipencs (s. II dC); trad. Chevallier (1846), PD. OCR.",
         "Polycarp__Epistle_to_the_Philippians_en.txt"),
        ("who is also called Theophorus",
         "Ignatius of Antioch",
         "Epistles (Ephesians, Magnesians, Trallians, Romans, Philadelphians, Smyrneans, "
         "to Polycarp); Martyrdom of Ignatius; Martyrdom of Polycarp",
         "Complete work", "Written by the author",
         "Cartes d'Ignasi d'Antioquia (s. II dC) i els relats del martiri d'Ignasi i de "
         "Policarp (anònims, de la comunitat d'Esmirna); trad. Chevallier (1846), PD. OCR.",
         "Ignatius_of_Antioch__Epistles_en.txt"),
        ("FIRST APOLOGY",
         "Justin Martyr", "First Apology",
         "Complete work", "Written by the author",
         "1a Apologia de Justí Màrtir (~155 dC) adreçada a l'emperador Antoní Pius; "
         "trad. Chevallier (1846), PD. OCR.",
         "Justin_Martyr__First_Apology_en.txt"),
     ]),
    # NPNF 2a sèrie, Vol. 12 (Sage Digital, text net): Lleó I (Feltoe) + Gregori I
    # (Barmby). Es parteix al títol de la secció de Gregori; sense índex final.
    ("LeoTheGreat.GregoryTheGreat", "leo_the_great_gregory_the_great_djvu.txt",
     "English", None, [
        ("LETTERS AND SERMONS",
         "Leo I", "Letters and Sermons (incl. the Tome to Flavian)",
         "Complete work", "Written by the author",
         "Cartes i sermons de Lleó I el Gran, incl. el Tomus ad Flavianum (base cristològica "
         "del Concili de Calcedònia, 451); trad. C. L. Feltoe (NPNF 2a sèrie, Vol. 12, 1895), "
         "PD. OCR. Separat del volum combinat amb Gregori I.",
         "Leo_I__Letters_and_Sermons_Feltoe_en.txt"),
        ("BOOK OF PASTORAL RULE",
         "Gregory I", "The Book of Pastoral Rule and Selected Epistles",
         "Complete work", "Written by the author",
         "Regula Pastoralis i epístoles seleccionades de Gregori I el Gran; trad. James Barmby "
         "(NPNF 2a sèrie, Vol. 12, 1895), PD. OCR. Separat del volum combinat amb Lleó I.",
         "Gregory_I__Pastoral_Rule_Barmby_en.txt"),
     ]),
]


def fetch(identifier: str, djvu: str) -> str | None:
    # Els noms de fitxer poden contenir espais/accents -> cal codificar-los per a la URL.
    url = (
        "https://archive.org/download/"
        + urllib.parse.quote(identifier)
        + "/"
        + urllib.parse.quote(djvu)
    )
    for attempt in range(3):  # reintents: archive.org pot fallar transitòriament
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (SigPhi)"})
            with urllib.request.urlopen(req, timeout=180) as r:  # urllib segueix el 302
                return r.read().decode("utf-8", errors="replace")
        except Exception as e:
            print(f"   intent {attempt + 1}/3 fallit ({identifier}): {e}")
            time.sleep(3)
    return None


def _drop_scan_garbage_lines(text: str) -> str:
    """Treu línies CURTES dominades per símbols/dígits: números de pàgina, segells i
    artefactes d'escaneig tipus "^^'';  H>„". Conserva la prosa (línies llargues o
    amb molta lletra) i el text no-llatí (el grec compta com a lletra a isalpha)."""
    out = []
    for ln in text.split("\n"):
        s = ln.strip()
        if 3 <= len(s) <= 40:
            alpha = sum(c.isalpha() for c in s)
            if alpha / len(s) < 0.4:  # més del 60% són símbols/dígits -> soroll
                continue
        out.append(ln)
    return "\n".join(out)


def clean_ocr(text: str) -> str:
    # Si és un mirall de Project Gutenberg, treu la capçalera/peu legal.
    m = _GUT_START.search(text)
    if m:
        text = text[m.end():]
    m = _GUT_END.search(text)
    if m:
        text = text[:m.start()]
    text = text.replace("\x0c", "\n")        # salts de pàgina DjVu -> PRIMER de tot,
    #                                          perquè els regex de sota casin per línia.
    # Boilerplate legal inicial de Google Books (només si hi és, ancorat a l'inici).
    if "This is a digital copy of a book" in text[:3000]:
        text = re.sub(r"(?is)\A.*?https?://books\.google\.com/?\S*\s*", "", text, count=1)
    # Avisos d'escàner / provinença de biblioteca (línia a línia). Tolerant a
    # errors d'OCR: n'hi ha prou amb veure "Digitized by", "funding from",
    # "Internet Archive" o "From the Bequest" en qualsevol punt de la línia.
    text = re.sub(
        r"(?im)^.*(?:Digitized by|funding from|Internet Archive|From the Bequest|"
        r"Staatsbibliothek).*$",
        "",
        text,
    )
    text = _drop_scan_garbage_lines(text)    # números de pàgina + artefactes OCR
    text = re.sub(r"[ \t]+\n", "\n", text)   # espais a final de línia
    text = re.sub(r"\n{3,}", "\n\n", text)   # col·lapsa blocs de línies en blanc
    return text.strip()


def _write_section(author, work, lang, comp, auth, note, fname, seg) -> bool:
    dest = CORPUS / fname
    if dest.exists():
        print(f"[skip] ja existeix: {fname}")
        return True
    if len(seg) < 2000:
        print(f"   AVÍS: secció curta ({len(seg)} car.) -> {fname}; revisa els marcadors")
        if not seg:
            return False
    header = (
        "=====SIGPHI=====\n"
        f"author: {author}\nwork: {work}\nlanguage: {lang}\n"
        f"completeness: {comp}\nauthorship: {auth}\nnote: {note}\n"
        "=====\n\n"
    )
    dest.write_text(header + seg, encoding="utf-8")
    print(f"   OK split -> {fname} ({len(seg)//1024} KB)")
    return True


def process_split(ident, djvu, lang, end_marker, sections) -> int:
    """Baixa un fitxer multi-autor i el parteix en N fitxers (un per autor/obra) pels
    marcadors de text. Si algun marcador no es troba, NO parteix (evita escriure
    fitxers mal tallats)."""
    if all((CORPUS / s[6]).exists() for s in sections):
        print(f"[skip] split ja fet: {ident}")
        return len(sections)
    print(f"[baixant+partint] {ident}...")
    raw = fetch(ident, djvu)
    if not raw:
        return 0
    body = clean_ocr(raw)
    starts, cur = [], 0
    for sec in sections:  # marcadors en ordre de document (cada un després de l'anterior)
        p = body.find(sec[0], cur)
        if p == -1:
            print(f"   ERROR: marcador no trobat {sec[0]!r} a {ident} -> NO es parteix")
            return 0
        starts.append(p)
        cur = p + len(sec[0])
    if end_marker:
        e = body.find(end_marker, starts[-1] + 1)
        last_end = e if e != -1 else len(body)
    else:
        last_end = len(body)
    ok = 0
    for i, sec in enumerate(sections):
        _, author, work, comp, auth, note, fname = sec
        seg_end = starts[i + 1] if i + 1 < len(sections) else last_end
        seg = body[starts[i]:seg_end].strip()
        if _write_section(author, work, lang, comp, auth, note, fname, seg):
            ok += 1
    return ok


def main() -> None:
    CORPUS.mkdir(parents=True, exist_ok=True)
    ok = 0
    for ident, djvu, author, work, lang, comp, auth, note, fname in TEXTS:
        dest = CORPUS / fname
        if dest.exists():
            print(f"[skip] ja existeix: {fname}")
            ok += 1
            continue
        print(f"[baixant] {work} (archive.org/{ident})...")
        raw = fetch(ident, djvu)
        if not raw:
            continue
        body = clean_ocr(raw)
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
    print(f"\n{ok}/{len(TEXTS)} textos d'archive.org a punt a corpus/.")
    nsplit = 0
    for ident, djvu, lang, end_marker, sections in SPLIT_TEXTS:
        nsplit += process_split(ident, djvu, lang, end_marker, sections)
    if SPLIT_TEXTS:
        print(f"{nsplit} fitxers de SPLIT_TEXTS a punt a corpus/.")
    print("Ara re-ingesta els nous (resumible):  bash deploy/run_ingest.sh")


if __name__ == "__main__":
    main()
