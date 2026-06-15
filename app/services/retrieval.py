"""RetrievalService: detecció d'autors (12 idiomes) + cerca semàntica amb filtre.

Per què la detecció d'autors:
    Sense filtre, una pregunta sobre "Epictet" podia recuperar fragments de
    Nietzsche per proximitat semàntica. Detectant l'autor anomenat a la consulta
    (en qualsevol dels 12 idiomes dels àlies) i passant-lo com author_filter,
    la cerca queda restringida a aquell autor. Si el filtre no retorna res,
    es fa una segona cerca sense filtre (fallback) per no deixar l'usuari sense
    resposta.
"""
from __future__ import annotations
import json
import re
import unicodedata
from pathlib import Path

from app.domain.interfaces import EmbedderInterface, VectorDBInterface
from app.domain.models import RetrievedChunk


def _norm(s: str) -> str:
    """Minúscules + sense accents (NFKD, treu marques combinants).

    Fa la detecció d'autor insensible a accents: 'Alcora' troba 'Alcorà',
    'Aristotil' troba 'Aristòtil'. Els scripts no-llatins (xinès, àrab, ciríl·lic)
    no tenen marques combinants aquí i es conserven intactes.
    """
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(c for c in s if not unicodedata.combining(c))
    return s.strip().lower()


# Paraules comunes que NO s'han d'indexar com a "cognom" (finals de títols
# multi-paraula que podrien donar falsos positius).
_SURNAME_STOP = {
    "dead", "war", "world", "life", "good", "soul", "mind", "love", "rights",
    "song", "book", "laws", "gods", "duty", "things", "nature", "state", "man",
    "king", "james",  # "Shi King" (Shijing) i "King James"/nom comú -> falsos positius
}


# === Detecció de TRADICIONS ===
# Preguntes com "els 5 pilars de l'islam" no anomenen cap autor concret, així que
# sense això la cerca no s'enfocava a l'escriptura corresponent (l'Alcorà no diu
# "pilar"). Mapem arrels de tradició/religió -> textos i autors d'aquella tradició
# al corpus, perquè s'incloguin al filtre. Les claus han de coincidir amb els
# autors del catàleg.
_ISLAM = ["Quran", "Hadith", "Al-Ghazali", "Averroes", "Avicenna", "Rumi"]
_CHRISTIANITY = ["Bible", "Augustine", "Thomas Aquinas", "Pistis Sophia"]
_JUDAISM = ["Tanakh", "Maimonides"]
_HINDUISM = ["Bhagavad Gita", "Upanishads", "Mahabharata", "Ramayana", "Rig Veda",
             "Laws of Manu", "Patanjali", "Shankaracharya"]
_BUDDHISM = ["Dhammapada", "Lotus Sutra", "Mahayana Sutras"]
_CONFUCIANISM = ["Confucius", "Mencius"]
_TAOISM = ["Laozi", "Zhuangzi", "Liezi"]
_ZOROASTRIANISM = ["Avesta"]
_SIKHISM = ["Adi Granth"]
# Sòcrates no va escriure res: el seu pensament sobreviu a través de Plató i
# Xenofont. Mapem el seu nom (idiomes principals) a aquests dos autors, com si fos
# una "tradició", perquè una pregunta sobre Sòcrates filtri i recuperi d'ells.
_SOCRATES = ["Plato", "Xenophon"]

# (arrel a buscar dins la consulta normalitzada, claus canòniques). Arrels
# distintives perquè el match per subcadena no doni falsos positius.
_TRADITION_ROOTS: list[tuple[str, list[str]]] = [
    ("socrat", _SOCRATES), ("sokrat", _SOCRATES), ("σωκρατ", _SOCRATES),
    ("сократ", _SOCRATES), ("苏格拉底", _SOCRATES), ("ソクラテス", _SOCRATES),
    ("سقراط", _SOCRATES), ("सुकरात", _SOCRATES),
    ("islam", _ISLAM), ("muslim", _ISLAM), ("musulm", _ISLAM), ("alcora", _ISLAM),
    ("cristian", _CHRISTIANITY), ("christian", _CHRISTIANITY),
    ("evangel", _CHRISTIANITY), ("gospel", _CHRISTIANITY), ("jesus", _CHRISTIANITY),
    ("judaism", _JUDAISM), ("judaisme", _JUDAISM), ("jewish", _JUDAISM),
    ("hinduism", _HINDUISM), ("hindu", _HINDUISM), ("vedic", _HINDUISM),
    ("vedas", _HINDUISM), ("vedes", _HINDUISM),
    ("budism", _BUDDHISM), ("buddhism", _BUDDHISM), ("budista", _BUDDHISM),
    ("buddhist", _BUDDHISM),
    ("confucian", _CONFUCIANISM),
    ("taoism", _TAOISM), ("taoisme", _TAOISM), ("taoista", _TAOISM),
    ("zoroastr", _ZOROASTRIANISM), ("zaratustra", _ZOROASTRIANISM),
    ("sikh", _SIKHISM),
]


class RetrievalService:
    def __init__(
        self,
        embedder: EmbedderInterface,
        vector_db: VectorDBInterface,
        aliases_path: Path,
        top_k: int = 15,
    ) -> None:
        self._embedder = embedder
        self._vector_db = vector_db
        self._top_k = top_k
        self._alias2author = self._load_aliases(Path(aliases_path))

    @staticmethod
    def _load_aliases(path: Path) -> dict[str, str]:
        """Construeix el mapa àlies(qualsevol idioma) -> autor canònic.

        Indexa àlies ASCII de >=4 caràcters (per incloure cognoms curts com
        Marx, Kant, Hume, Mill) o qualsevol cadena amb caràcters no-ASCII
        (xinès, àrab, etc.). El risc de falsos positius dels noms curts es controla
        a detect_authors amb límit de paraula.
        """
        alias2author: dict[str, str] = {}
        if not path.exists():
            return alias2author
        data = json.loads(path.read_text(encoding="utf-8"))
        for canon, names in data.items():
            if isinstance(names, dict):
                items = list(names.items())
            else:
                items = [("_", v) for v in names]
            for key, v in items + [("_canon", canon)]:
                n = _norm(v)
                if not n:
                    continue
                if len(n) >= 4 or any(ord(c) > 127 for c in n):
                    alias2author.setdefault(n, canon)
                # Els camps de TÍTOL D'OBRA (claus 'w...': w_en, wm_en, work_en...)
                # només s'indexen com a frase sencera, MAI per última paraula: si no,
                # "Nicomachean Ethics" generaria l'àlies genèric "ethics" -> Aristotle
                # i "Consolation of Philosophy" -> "philosophy" -> Boethius.
                if key.startswith("w"):
                    continue
                # COGNOM (última paraula) de NOMS multi-paraula, perquè 'Marx'
                # detecti 'Karl Marx', 'Витгенштейн' 'Людвиг Витгенштейн' i
                # '维特根斯坦' '路德维希·维特根斯坦'. Separadors: espais i punts medials
                # (· ・). Min 4 lletres en alfabets (evita falsos positius), 2 en CJK.
                parts = [p for p in re.split(r"[\s·・]+", n) if p]
                if 2 <= len(parts) <= 4:
                    last = parts[-1]
                    is_cjk = any(
                        "぀" <= c <= "鿿" or "가" <= c <= "힣"
                        for c in last
                    )
                    if n.isascii():
                        if len(last) >= 4 and last not in _SURNAME_STOP:
                            alias2author.setdefault(last, canon)
                    elif len(last) >= (2 if is_cjk else 4):
                        alias2author.setdefault(last, canon)
        return alias2author

    def detect_authors(self, query: str) -> list[str]:
        """Retorna els autors canònics anomenats a la consulta (qualsevol idioma).

        Per a àlies ASCII fa match per LÍMIT DE PARAULA (així 'mill' no casa amb
        'million' ni 'kant' amb 'decant'); per als scripts no-llatins (sense límit
        de paraula útil) manté el match de subcadena.
        """
        ql = _norm(query)
        found: list[str] = []
        for alias, canon in self._alias2author.items():
            if canon in found:
                continue
            if alias.isascii():
                if re.search(r"\b" + re.escape(alias) + r"\b", ql):
                    found.append(canon)
            elif alias in ql:
                found.append(canon)
        # Tradicions/religions: afegeix les escriptures i autors de la tradició
        # esmentada (encara que no s'anomeni cap autor concret).
        for root, canons in _TRADITION_ROOTS:
            if root in ql:
                for c in canons:
                    if c not in found:
                        found.append(c)
        return found

    def _tradition_core(self, ql: str) -> list[str]:
        """Escriptures NUCLI de les tradicions esmentades a la consulta (les 2
        primeres claus de cada clúster: p. ex. islam -> Quran, Hadith). Serveixen
        per garantir-ne la representació al retrieval (si no, el text més voluminós
        de la tradició —el Coran— acapara el top_k i els hadissos de les pràctiques
        no hi surten mai)."""
        core: list[str] = []
        for root, canons in _TRADITION_ROOTS:
            if root in ql:
                for c in canons[:2]:
                    if c not in core:
                        core.append(c)
        return core

    def retrieve(self, query: str) -> list[RetrievedChunk]:
        """Vectoritza la consulta i recupera top_k; filtra per autor si n'hi ha.

        Per a consultes de TRADICIÓ (islam, budisme...) garanteix que les
        escriptures nucli hi siguin representades (top-3 de cadascuna) abans
        d'omplir amb el millor general; així preguntes de resum doctrinal ("els 5
        pilars") tenen a context els passatges de les pràctiques, no només el
        fragment del Coran millor classificat.
        """
        qv = self._embedder.embed_query(query)
        ql = _norm(query)
        authors = self.detect_authors(query)
        core = self._tradition_core(ql)
        if core:
            seen: set[str] = set()
            merged: list[RetrievedChunk] = []
            for a in core:  # representació garantida de cada escriptura nucli
                for rc in self._vector_db.query_similarity(qv, 3, author_filter=[a]):
                    if rc.chunk.chunk_id not in seen:
                        seen.add(rc.chunk.chunk_id)
                        merged.append(rc)
            for rc in self._vector_db.query_similarity(  # omple amb el millor general
                qv, self._top_k, author_filter=authors
            ):
                if rc.chunk.chunk_id not in seen:
                    seen.add(rc.chunk.chunk_id)
                    merged.append(rc)
            if merged:
                return merged[: self._top_k + 6]
        if authors:
            res = self._vector_db.query_similarity(
                qv, self._top_k, author_filter=authors
            )
            if res:
                return res
        return self._vector_db.query_similarity(qv, self._top_k)
