"""The Help dock (decision 13.13; PLAN.md section 11, open point 7): the help
of the selected entry, and pyqula's and guiqula's user guides, as the
docs package puts them together (pyqula's own text, never written again).

The Markdown is drawn by Qt's QTextBrowser; its equations become images
drawn with mathtext (ui/formulas.py), served under formula:N by
loadResource, and one mathtext cannot draw is shown as its LaTeX source.
Links help:<guide>/<anchor> open a section; Back returns to the page
before.
"""
from urllib.parse import unquote

from PySide6.QtCore import Signal
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QTextBrowser, QVBoxLayout, QWidget

from guiqula.docs import entries, guide as guides
from guiqula.ui import formulas


class HelpBrowser(QTextBrowser):
    link_activated = Signal(str, str)      # guide ("pyqula" or "guiqula"), anchor

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("helpBrowser")
        self.setOpenLinks(False)
        self.anchorClicked.connect(self._clicked)
        self.equations = []
        self.markdown = ""

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
        self.browser.link_activated.connect(self.show_section)
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
        self.title = QLabel("")
        self.title.setObjectName("helpTitle")
        row = QHBoxLayout()
        row.addWidget(self.back)
        row.addWidget(pyqula)
        row.addWidget(own)
        row.addStretch(1)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.addLayout(row)
        layout.addWidget(self.title)
        layout.addWidget(self.browser, 1)
        self.session = None     # the window's, for the help of outliner items
        self.history = []       # pages shown before
        self.page = None        # ("item", id) | ("section", which, anchor) | ("contents", which)
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

    def show_section(self, which, anchor, remember=True):
        try:
            text = entries.section_page(which, anchor)
        except guides.GuideError as error:
            text = f"{error}\n"
        return self._show(("section", which, anchor), anchor, text, remember)

    def show_contents(self, which, remember=True):
        title = f"{which} user guide"
        return self._show(("contents", which), title, entries.contents(which), remember)

    def go_back(self):
        if not self.history:
            return None
        page = self.history.pop()
        if page[0] == "section":
            self.show_section(page[1], page[2], remember=False)
        elif page[0] == "contents":
            self.show_contents(page[1], remember=False)
        else:
            self.show_item(page[1], remember=False)
        self._update_back()
        return page
