"""The Help dock (decision 13.13; PLAN.md section 11, open point 7): the help
of the selected entry, and pyqula's and guiqula's user guides, as the
docs package puts them together (pyqula's own text, never written again).

The Markdown is drawn by Qt's QTextBrowser; its equations become images
drawn with mathtext (ui/formulas.py), served under formula:N by
loadResource, and one mathtext cannot draw is shown as its LaTeX source.
Links help:<guide>/<anchor> open a section (an empty anchor: the guide's
contents), help:entry/<family>:<kind> a registry entry's help; the search
line (decision 159) shows the entries and sections that answer a question,
as docs/search.py ranks them; Back returns to the page before.
"""
from urllib.parse import unquote

from PySide6.QtCore import QEvent, QUrl, Signal
from PySide6.QtGui import QImage, QTextBlockFormat, QTextCursor, QTextDocument
from PySide6.QtWidgets import (QHBoxLayout, QLabel, QLineEdit, QPushButton, QTextBrowser,
                               QVBoxLayout, QWidget)

from guiqula.docs import entries, guide as guides, search
from guiqula.registry import base as registry
from guiqula.ui import formulas


WRAP_SLACK = 4       # pixels between the wrapped text and the viewport's right edge


class HelpBrowser(QTextBrowser):
    link_activated = Signal(str, str)      # guide ("pyqula" or "guiqula"), anchor

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("helpBrowser")
        self.setOpenLinks(False)
        self.anchorClicked.connect(self._clicked)
        self.equations = []
        self.markdown = ""
        # the text wraps a little inside the viewport: wrapped at its very width, Qt's
        # rounding left some pages a pixel wider than it, with a scroll bar for that pixel
        self.setLineWrapMode(QTextBrowser.LineWrapMode.FixedPixelWidth)

    def show_markdown(self, text):
        """Draw Markdown with $...$ equations."""
        text, equations = guides.math_images(text)
        for i, tex in enumerate(equations):        # what mathtext cannot draw: its source
            try:
                formulas.png(tex)
            except formulas.FormulaError:
                text = text.replace(f"![equation](formula:{i})", f"`{tex}`")
        self.equations = equations
        self.markdown = text
        self.setMarkdown(text)
        self._wrap_code()
        self._fit_equations()

    def _wrap_code(self):
        """Let the lines of the code blocks wrap at the panel's width, as the
        prose does: Qt keeps a code block's lines whole, and one line longer
        than the panel gave the whole page a horizontal scroll bar."""
        cursor = QTextCursor(self.document())
        wrapping = QTextBlockFormat()
        wrapping.setNonBreakableLines(False)
        block = self.document().begin()
        while block.isValid():
            if block.blockFormat().nonBreakableLines():
                cursor.setPosition(block.position())
                cursor.mergeBlockFormat(wrapping)
            block = block.next()

    def _fit_equations(self):
        """Scale an equation's image wider than the panel down to the
        panel's width (its height in proportion), and give one that fits its
        own size back, so that no page scrolls sideways; called after each
        page and at each change of the panel's width."""
        document = self.document()
        room = self.viewport().width() - WRAP_SLACK - 2 * document.documentMargin()
        if room <= 0:
            return
        changes = []
        block = document.begin()
        while block.isValid():
            indent = block.blockFormat().leftMargin() + \
                block.blockFormat().indent() * document.indentWidth()
            fragments = block.begin()
            while not fragments.atEnd():
                fragment = fragments.fragment()
                look = fragment.charFormat()
                if look.isImageFormat() and look.toImageFormat().name().startswith("formula:"):
                    changes.append((fragment.position(), fragment.length(),
                                    look.toImageFormat(), room - indent))
                fragments += 1
            block = block.next()
        cursor = QTextCursor(document)
        for position, length, image, width in changes:
            natural = self._natural_size(image.name())
            if natural is None:
                continue
            scale = min(1.0, width / natural.width()) if natural.width() > 0 else 1.0
            wanted = (natural.width() * scale, natural.height() * scale) if scale < 1.0 \
                else (0.0, 0.0)                            # 0: the image's own size
            if (image.width(), image.height()) == wanted:
                continue
            image.setWidth(wanted[0])
            image.setHeight(wanted[1])
            cursor.setPosition(position)
            cursor.setPosition(position + length, QTextCursor.MoveMode.KeepAnchor)
            cursor.setCharFormat(image)

    def _natural_size(self, name):
        """The size an equation's image is drawn at, or None."""
        image = self.loadResource(QTextDocument.ResourceType.ImageResource.value, QUrl(name))
        return image.size() / image.devicePixelRatio() if isinstance(image, QImage) and \
            not image.isNull() else None

    def viewportEvent(self, event):
        # the viewport, not the browser: it narrows too when the vertical scroll bar appears
        if event.type() == QEvent.Type.Resize and \
                event.size().width() != event.oldSize().width():
            self.setLineWrapColumnOrWidth(max(event.size().width() - WRAP_SLACK, 1))
            self._fit_equations()
        return super().viewportEvent(event)

    def loadResource(self, kind, url):
        if url.scheme() == "formula":
            try:
                image = QImage()
                image.loadFromData(formulas.png(self.equations[int(url.path())]), "PNG")
                return image
            except (ValueError, IndexError, formulas.FormulaError):
                return None
        return super().loadResource(kind, url)

    def _clicked(self, url):
        if url.scheme() == "help":
            which, _, anchor = url.path().partition("/")
            self.link_activated.emit(which, unquote(anchor))


class HelpPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("helpPanel")
        self.browser = HelpBrowser()
        self.browser.link_activated.connect(self.open_link)
        self.back = QPushButton("Back")
        self.back.setObjectName("helpBack")
        self.back.clicked.connect(self.go_back)
        pyqula = QPushButton("pyqula guide")
        pyqula.setObjectName("helpPyqulaGuide")
        pyqula.setToolTip("the contents of pyqula's user guide")
        pyqula.clicked.connect(lambda: self.show_contents("pyqula"))
        own = QPushButton("guiqula guide")
        own.setObjectName("helpGuiqulaGuide")
        own.setToolTip("the contents of guiqula's user guide")
        own.clicked.connect(lambda: self.show_contents("guiqula"))
        self.search = QLineEdit()
        self.search.setObjectName("helpSearch")
        self.search.setPlaceholderText("Search the help")
        self.search.setClearButtonEnabled(True)
        self.search.setToolTip("the entries and the sections of both guides that answer a "
                               "question, best first (Enter)")
        self.search.returnPressed.connect(lambda: self.show_search(self.search.text()))
        self.title = QLabel("")
        self.title.setObjectName("helpTitle")
        self.title.setWordWrap(True)         # a long section's name would widen the column
        row = QHBoxLayout()
        row.addWidget(self.back)
        row.addWidget(pyqula)
        row.addWidget(own)
        row.addStretch(1)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.addLayout(row)
        layout.addWidget(self.search)
        layout.addWidget(self.title)
        layout.addWidget(self.browser, 1)
        self.session = None     # the window's, for the help of outliner items
        self.history = []       # pages shown before
        self.page = None        # ("item", id) | ("section", which, anchor) | ("contents", which)
                                # | ("plugins",) | ("entry", family, kind) | ("search", text)
        self._update_back()

    def _show(self, page, title, text, remember=True):
        if remember and self.page is not None and self.page != page:
            self.history.append(self.page)
        self.page = page
        self.title.setText(title)
        self.browser.show_markdown(text)
        self._update_back()
        return title

    def _update_back(self):
        self.back.setEnabled(bool(self.history))

    def show_item(self, item_id, remember=True):
        """The help of an outliner item (an entry, a system, a region...)."""
        try:
            title, text = entries.item_help(self.session, item_id)
        except Exception as error:          # an entry of an unknown kind (a missing plugin)
            title, text = item_id, f"No help for {item_id}: {error}\n"
        return self._show(("item", item_id), title, text, remember)

    def open_link(self, which, anchor):
        """A help: link: a registry entry, a guide's contents or a section."""
        if which == "entry":
            return self.show_entry(*anchor.split(":", 1))
        if not anchor:
            return self.show_contents(which)
        return self.show_section(which, anchor)

    def show_entry(self, family, kind, remember=True):
        """The help of a registry entry, with its default values."""
        spec = registry.get(family, kind)
        return self._show(("entry", family, kind), spec.label, entries.entry_help(spec),
                          remember)

    def show_search(self, text, remember=True):
        """The entries and the guide sections that answer a question, as links."""
        if not text.strip():
            return None
        if self.search.text() != text:
            self.search.setText(text)
        title, markdown = search.page(text)
        return self._show(("search", text), title, markdown, remember)

    def show_page(self, page, remember=False):
        """Show a page as self.page names it (Back, a redraw)."""
        kind, args = page[0], page[1:]
        return {"section": self.show_section, "contents": self.show_contents,
                "plugins": self.show_plugins, "entry": self.show_entry,
                "search": self.show_search, "item": self.show_item}[kind](
                    *args, remember=remember)

    def show_section(self, which, anchor, remember=True):
        try:
            text = entries.section_page(which, anchor)
        except guides.GuideError as error:
            text = f"{error}\n"
        return self._show(("section", which, anchor), anchor, text, remember)

    def show_contents(self, which, remember=True):
        title = f"{which} user guide"
        return self._show(("contents", which), title, entries.contents(which), remember)

    def show_plugins(self, remember=True):
        """The plugins loaded, their entries, the ones that failed, and the
        ones the open document uses."""
        document = self.session.document if self.session is not None else None
        return self._show(("plugins",), "Plugins", entries.plugins_page(document), remember)

    def go_back(self):
        if not self.history:
            return None
        page = self.history.pop()
        self.show_page(page)
        self._update_back()
        return page
