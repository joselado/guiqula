"""Assemble upstream pyqula's user guide, a MkDocs website since October
2026 (the pages of documentation/guide/ in the order of mkdocs.yml's nav),
into the one Markdown file the in-app help reads (vendor/pyqula_user_guide.md,
docs/guide.py). Each page is a chapter, its "# Title" kept; what the website
does with MkDocs extensions is written out plainly: an included snippet
(--8<-- "file.py", from documentation/figures/) becomes the file's text, a
collapsible block (??? example "Title") a bold line and its body unindented,
and a picture, which the help does not ship, is left out.

Usage: python tools/assemble_guide.py /path/to/pyqula out.md
"""
import re
import sys
from pathlib import Path

import yaml

SNIPPET = re.compile(r'^(\s*)--8<--\s+"([^"]+)"\s*$')
BLOCK = re.compile(r'^(\?\?\?\+?|!!!)\s+\w+(?:\s+"([^"]*)")?\s*$')
IMAGE = re.compile(r"^\s*!\[[^\]]*\]\([^)]*\)\s*$")


def pages(nav):
    """The page files of a nav, in order."""
    for item in nav:
        if isinstance(item, str):
            yield item
        elif isinstance(item, dict):
            for value in item.values():
                if isinstance(value, str):
                    yield value
                else:
                    yield from pages(value)


def plain(text, figures):
    """A page's Markdown without the MkDocs extensions (see the module)."""
    out, lines, i = [], text.splitlines(), 0
    while i < len(lines):
        line = lines[i]
        snippet = SNIPPET.match(line)
        block = BLOCK.match(line)
        if snippet:
            indent, name = snippet.groups()
            path = figures / name
            body = path.read_text() if path.exists() else f"# {name} is not in the copy\n"
            out += [indent + row if row else row for row in body.rstrip("\n").splitlines()]
        elif block:
            title = block.group(2)
            if title:
                out.append(f"**{title}**")
                out.append("")
            i += 1
            while i < len(lines) and (not lines[i].strip() or lines[i].startswith("    ")):
                out.append(lines[i][4:] if lines[i].startswith("    ") else lines[i])
                i += 1
            continue
        elif not IMAGE.match(line):
            out.append(line)
        i += 1
    return out


def assemble(source):
    source = Path(source)
    config = yaml.safe_load((source / "mkdocs.yml").read_text())
    docs = source / config.get("docs_dir", "documentation/guide")
    figures = source / "documentation" / "figures"
    chapters = []
    for page in pages(config["nav"]):
        # twice: a snippet inside a collapsible block is expanded once the block is unindented
        lines = plain("\n".join(plain((docs / page).read_text(), figures)), figures)
        chapters.append("\n".join(lines).strip("\n"))
    return "\n\n".join(chapters) + "\n"


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    Path(sys.argv[2]).write_text(assemble(sys.argv[1]))
