"""A Markdown user guide split into sections (decision 13.13, open point 7).

A section is a heading and what follows it up to the next heading of the
same or a higher level. Its anchor is the heading's text as written, or
"Parent > Heading" when the text is used by more than one heading (the
parent is the nearest heading of a higher level). Headings are only read
outside fenced code blocks: the guide's code has `#` comments at line
starts.

math_images() replaces the $...$ and $$...$$ equations of a text by image
links (formula:N) that the help view draws with mathtext, after a few
rewrites mathtext needs; what mathtext cannot draw is shown as its LaTeX
source by the view.
"""
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

HEADING = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
FENCE = re.compile(r"^\s*(```|~~~)")
DISPLAY = re.compile(r"\$\$(.+?)\$\$", re.S)
INLINE = re.compile(r"(?<![\\$])\$([^$\n]+?)\$(?!\$)")
# what mathtext does not know, and its nearest equivalent
REWRITES = ((re.compile(r"\\tfrac"), r"\\frac"), (re.compile(r"\\dfrac"), r"\\frac"),
            (re.compile(r"\\frac\s*(\d)\s*(\d)"), r"\\frac{\1}{\2}"),
            (re.compile(r"\\sqrt\s*(\d)"), r"\\sqrt{\1}"),
            (re.compile(r"\\(mathbf|mathcal|mathrm|vec|hat|tilde|bar)\s+([A-Za-z0-9])"),
             r"\\\1{\2}"),
            (re.compile(r"\\mod\b"), r"\\ \\mathrm{mod}\\ "),
            (re.compile(r"\\qquad"), r"\\quad"), (re.compile(r"\\left\s*\\\{|\\left\s*\("), "("),
            (re.compile(r"\\right\s*\\\}|\\right\s*\)"), ")"),
            (re.compile(r"\\left\s*\[|\\left\s*\\\["), "["), (re.compile(r"\\right\s*\]"), "]"),
            (re.compile(r"\\left\s*\||\\right\s*\|"), "|"),
            (re.compile(r"\\left\s*\\langle"), r"\\langle"),
            (re.compile(r"\\right\s*\\rangle"), r"\\rangle"),
            (re.compile(r"\\left\.|\\right\."), ""))


class GuideError(KeyError):
    pass


@dataclass
class Section:
    title: str
    level: int
    anchor: str
    parent: str        # the anchor of the parent section, "" at the top
    start: int         # line numbers of the heading and of the end (exclusive)
    end: int


class Guide:
    def __init__(self, text, name=""):
        self.name = name
        self.lines = text.splitlines()
        self.sections = []
        headings, fenced = [], False
        for number, line in enumerate(self.lines):
            if FENCE.match(line):
                fenced = not fenced
                continue
            match = HEADING.match(line) if not fenced else None
            if match:
                headings.append((number, len(match.group(1)), match.group(2).strip()))
        counts = {}
        for _, _, title in headings:
            counts[title] = counts.get(title, 0) + 1
        stack = []       # (level, title) of the enclosing headings
        for i, (number, level, title) in enumerate(headings):
            while stack and stack[-1][0] >= level:
                stack.pop()
            parent_title = stack[-1][1] if stack else ""
            anchor = title if counts[title] == 1 or not parent_title else \
                f"{parent_title} > {title}"
            end = next((n for n, lv, _ in headings[i + 1:] if lv <= level), len(self.lines))
            parent = next((s.anchor for s in reversed(self.sections)
                           if s.level < level and s.start < number), "")
            self.sections.append(Section(title, level, anchor, parent, number, end))
            stack.append((level, title))
        self.by_anchor = {}
        for section in self.sections:
            self.by_anchor.setdefault(section.anchor, []).append(section)

    @classmethod
    def load(cls, path):
        path = Path(path)
        return cls(path.read_text(encoding="utf-8"), path.name)

    def anchors(self):
        return [s.anchor for s in self.sections]

    def find(self, anchor):
        """The section of an anchor; GuideError if there is none or it is
        ambiguous (a heading repeated under the same parent)."""
        found = self.by_anchor.get(anchor, [])
        if len(found) != 1:
            raise GuideError(f"{self.name or 'the guide'} has "
                             f"{'no section' if not found else f'{len(found)} sections'} "
                             f"{anchor!r}")
        return found[0]

    def text(self, anchor, with_heading=True):
        """The Markdown of a section (with its subsections)."""
        section = self.find(anchor)
        lines = self.lines[section.start + (0 if with_heading else 1):section.end]
        return "\n".join(lines).strip() + "\n"

    def calls(self, name):
        """Anchors of the sections whose own code (not their subsections')
        calls name, e.g. "add_zeeman"."""
        pattern = re.compile(rf"(?<![A-Za-z0-9_]){re.escape(name)}\s*\(")
        out = []
        for i, section in enumerate(self.sections):
            end = self.sections[i + 1].start if i + 1 < len(self.sections) else section.end
            fenced = False
            for line in self.lines[section.start:min(end, section.end)]:
                if FENCE.match(line):
                    fenced = not fenced
                elif fenced and pattern.search(line):
                    out.append(section.anchor)
                    break
        return out


def rewrite(tex):
    """An equation as mathtext can read it (one line, known commands)."""
    tex = " ".join(tex.split())
    for pattern, replacement in REWRITES:
        tex = pattern.sub(replacement, tex)
    return tex.strip()


def math_images(text):
    """(text with every equation outside code replaced by an image link
    ![equation](formula:N), [the equations]); display equations get a
    paragraph of their own."""
    equations, out, fenced = [], [], False

    def image(tex, display):
        equations.append(rewrite(tex))
        link = f"![equation](formula:{len(equations) - 1})"
        return f"\n\n{link}\n\n" if display else link
    blocks = re.split(r"(^\s*(?:```|~~~).*$)", text, flags=re.M)
    for block in blocks:
        if FENCE.match(block):
            fenced = not fenced
            out.append(block)
            continue
        if fenced:
            out.append(block)
            continue
        parts = re.split(r"(`[^`\n]*`)", block)            # inline code stays as it is
        for j, part in enumerate(parts):
            if j % 2 == 0:
                part = DISPLAY.sub(lambda m: image(m.group(1), True), part)
                part = INLINE.sub(lambda m: image(m.group(1), False), part)
            parts[j] = part
        out.append("".join(parts))
    return "".join(out), equations


@lru_cache(maxsize=4)
def load(path):
    """A Guide read once per path."""
    return Guide.load(path)
