"""A search of the help from a question in words (decision 159): the
registry entries, and the sections of pyqula's and guiqula's user guides,
ranked by BM25, with no model and no new dependency, so that it runs in the
UI process (13.15) and serves the Help panel's search line, the window's
help action and the remote help method alike.

An entry is a document of its label, kind, group, doc, parameters and the
docstrings of its pyqula calls, its label and kind counted three times; a
guide section is a document of its own text (up to its first subsection),
its heading counted three times and its parent's heading once. A word of the
question that no document holds is replaced by the words of the index close
to it (difflib's ratio, a typo) or starting with it (a word cut short), each
weighted by its closeness. The index is built at the first search and kept
until the registry or the guide in use changes.
"""
import difflib
import re
from dataclasses import dataclass
from functools import lru_cache
from math import log

from guiqula import vendoring
from guiqula.docs import docstrings, entries
from guiqula.registry import base as registry

K1, B = 1.2, 0.75          # BM25's usual constants
TITLE = 3                  # times a heading or an entry's label counts
CLOSE = 0.8                # difflib ratio from which a word stands for a mistyped one
PREFIX = 4                 # letters from which a word of the question may be cut short
EXPANSIONS = 3             # words of the index one word of the question may stand for
LIMIT = 12                 # results shown
SNIPPET = 160              # characters of the line shown under a result
WORD = re.compile(r"[a-z0-9]+")
CODE = re.compile(r"^\s*(```|~~~)")
STOP = frozenset("""a an and are as at be by can do does for from how i in into is it its
me my of on or that the this to what when where which with you your we our one there
then than so if not no use using used want""".split())


@dataclass(frozen=True)
class Hit:
    guide: str             # "entry", "pyqula" or "guiqula"
    anchor: str            # "family:kind" for an entry, a section's anchor otherwise
    title: str
    where: str             # the family of an entry, or the guide and the parent section
    score: float
    snippet: str


def stem(word):
    """A word as the index keeps it: plurals folded ("bands" and "band")."""
    if len(word) > 4 and word.endswith("ies"):
        return word[:-3] + "y"
    if len(word) > 3 and word.endswith("s") and not word.endswith(("ss", "us", "is")):
        return word[:-1]
    return word


def words(text):
    return [stem(w) for w in WORD.findall(text.lower().replace("_", " ")) if w not in STOP]


@dataclass
class Document:
    guide: str
    anchor: str
    title: str
    where: str
    text: str              # what a snippet is taken from
    counts: dict
    length: int


def _document(guide, anchor, title, where, weighted, text):
    counts = {}
    for words_of, times in weighted:
        for word in words(words_of):
            counts[word] = counts.get(word, 0) + times
    return Document(guide, anchor, title, where, text, counts, sum(counts.values()))


def _entry_documents():
    out = []
    for spec in registry.entries():
        params = " ".join(f"{p.name} {p.label} {p.doc or ''}" for p in spec.params)
        calls = " ".join(entries.pyqula_targets(spec))
        try:
            docs = " ".join(docstrings.docstring(t) or "" for t in entries.pyqula_targets(spec))
        except vendoring.VendoringError:
            docs = ""
        family = entries.FAMILY_NAMES.get(spec.family, spec.family)
        out.append(_document(
            "entry", f"{spec.family}:{spec.kind}", spec.label,
            family + (f" · {spec.group}" if spec.group else ""),
            [(f"{spec.label} {spec.kind}", TITLE),
             (f"{spec.group} {spec.doc} {params} {calls} {docs}", 1)],
            f"{spec.doc}\n{docs}"))
    return out


def _section_documents(which, guide):
    out = []
    titles = {s.anchor: s.title for s in guide.sections}
    for section in guide.sections:
        own = guide.own_text(section.anchor)
        body = own.split("\n", 1)[1] if "\n" in own else ""
        parent = titles.get(section.parent, "")
        out.append(_document(
            which, section.anchor, section.title,
            f"{which} guide" + (f" · {parent}" if parent else ""),
            [(section.title, TITLE), (parent, 1), (body, 1)], body))
    return out


class Index:
    def __init__(self, documents):
        self.documents = documents
        self.frequency = {}
        for document in documents:
            for word in document.counts:
                self.frequency[word] = self.frequency.get(word, 0) + 1
        self.vocabulary = sorted(self.frequency)
        self.average = sum(d.length for d in documents) / max(len(documents), 1)

    def idf(self, word):
        n = self.frequency.get(word, 0)
        return log(1 + (len(self.documents) - n + 0.5) / (n + 0.5))

    def expand(self, word):
        """{word of the index: weight} that a word of the question stands for."""
        if word in self.frequency:
            return {word: 1.0}
        found = {}
        if len(word) >= PREFIX:
            for other in self.vocabulary:
                if other.startswith(word):
                    found[other] = len(word) / len(other)
        for other in difflib.get_close_matches(word, self.vocabulary, EXPANSIONS, CLOSE):
            found[other] = max(found.get(other, 0.0),
                               difflib.SequenceMatcher(None, word, other).ratio())
        best = sorted(found.items(), key=lambda item: (-item[1], -self.frequency[item[0]]))
        return dict(best[:EXPANSIONS])

    def score(self, document, weights):
        total = 0.0
        norm = K1 * (1 - B + B * document.length / self.average)
        for word, weight in weights.items():
            tf = document.counts.get(word, 0)
            if tf:
                total += weight * self.idf(word) * tf * (K1 + 1) / (tf + norm)
        return total

    def search(self, question, limit=LIMIT):
        weights = {}
        for word in dict.fromkeys(words(question)):
            for other, weight in self.expand(word).items():
                weights[other] = max(weights.get(other, 0.0), weight)
        if not weights:
            return []
        scored = [(self.score(d, weights), i) for i, d in enumerate(self.documents)]
        scored = sorted((s for s in scored if s[0] > 0), key=lambda s: (-s[0], s[1]))
        return [self._hit(self.documents[i], score, weights) for score, i in scored[:limit]]

    def _hit(self, document, score, weights):
        return Hit(document.guide, document.anchor, document.title, document.where,
                   round(score, 3), snippet(document.text, weights))


def snippet(text, weights):
    """The line of a text, outside code, that holds the most of the words
    searched for, cut to SNIPPET characters around the first of them."""
    best, best_count, fenced = "", 0, False
    for line in text.splitlines():
        if CODE.match(line):
            fenced = not fenced
            continue
        if fenced or not line.strip() or line.lstrip().startswith(("#", "|", "$$")):
            continue
        found = set(words(line)) & set(weights)
        if len(found) > best_count:
            best, best_count = line.strip(), len(found)
    if not best:
        return ""
    lower = best.lower()
    first = min((lower.find(w) for w in weights if lower.find(w) >= 0), default=0)
    start = max(0, first - SNIPPET // 3)
    cut = best[start:start + SNIPPET]
    return ("..." if start else "") + cut + ("..." if start + SNIPPET < len(best) else "")


@lru_cache(maxsize=2)
def _index(key):
    documents = _entry_documents()
    guide = entries.pyqula_guide()
    if guide is not None:
        documents += _section_documents("pyqula", guide)
    documents += _section_documents("guiqula", entries.guiqula_guide())
    return Index(documents)


def index():
    """The index of the registry and the guides in use, built once."""
    found = vendoring.find_guide()
    return _index((tuple((s.family, s.kind) for s in registry.entries()),
                   str(found[1]) if found else ""))


def search(question, limit=LIMIT):
    """The entries and guide sections that answer a question, best first."""
    return index().search(question, limit)


def link(hit):
    return entries.link(hit.guide, hit.anchor, hit.title)


def page(question, limit=LIMIT):
    """(title, Markdown) of the results of a question, as the Help panel shows them."""
    hits = search(question, limit)
    title = f"Search: {question.strip()}"
    if not hits:
        return title, ("Nothing in the help matches. The guides' contents list every "
                       f"section: {entries.link('pyqula', '', 'pyqula')}, "
                       f"{entries.link('guiqula', '', 'guiqula')}.\n")
    # the panel's title names the search, so the page has no heading of its own;
    # a result is a paragraph, its snippet on a second line (a hard break)
    return title, "\n\n".join(f"**{link(hit)}** *({hit.where})*"
                               + (f"  \n{hit.snippet}" if hit.snippet else "")
                               for hit in hits) + "\n"
