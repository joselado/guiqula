"""The start page (PLAN.md phase 8, package P1): what the window shows in
place of the viewport while the document has no system, so that the
program opens on something to do. Three bands of a scrolled page: "Start
from a lattice" (the registry's lattices by group, then the classical
systems), "Open an example" (the presets, the teaching ones marked) and
"Recent files" (the settings' recent files and Open a project...), a filter
box at the top that narrows every band, and a footer line under the
scrolled bands, always in sight, saying what comes next, with a link to
guiqula's guide.

A band shows one row of cards (the first ones, in the band's order) until
its "Show all" is pressed or the filter has text, so that every band is in
sight at 1200x800; shown whole, the lattices are grouped under their
dimension. The cards are buttons that paint themselves from the palette at
paint time, so the theme restyles them. The pictures are PNG files made by
tools/make_thumbnails.py (resources/thumbnails/), loaded after the first
paint, never computed here (the UI process stays light, PLAN.md 13.15). The
gallery dialog (ui/gallery.py) is made of the same preset cards.
"""
import json
import re
from pathlib import Path

from PySide6.QtCore import QEvent, QPoint, QRect, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QFontMetrics, QIcon, QPainter, QPalette, QPen, QPixmap
from PySide6.QtWidgets import (QAbstractButton, QFrame, QHBoxLayout, QLabel, QLayout,
                               QLineEdit, QScrollArea, QSizePolicy, QToolButton, QVBoxLayout,
                               QWidget)

from guiqula.io import project
from guiqula.ui import icons, shortcuts
from guiqula.ui.palette import grouped

THUMBNAILS = Path(__file__).resolve().parents[1] / "resources" / "thumbnails"
FOLDERS = {"lattice": "lattices", "classical": "classical", "preset": "presets"}
PREFIXES = {"lattice": "startLattice", "classical": "startClassical",
            "preset": "startPreset", "recent": "startRecent"}
PICTURE = QSize(160, 120)       # the picture of a card, as tools/make_thumbnails.py draws it
PAD = 6                         # inside a card, around its picture and text
CARD = QSize(PICTURE.width() + 2 * PAD, 0)      # the width of a card (Card.sizeHint)
SPACING = 10                    # between cards
# lines of a card's text: the title, and the smaller lines below it, which hold the teaching
# mark and the first sentence (and whatever line a one-line title leaves)
LINES = {"lattice": (2, 0), "classical": (2, 0), "preset": (2, 4)}
RECENT_SHOWN = 3                # recent files in sight until Show all
TEACHING = "teaching, some parameters locked"
CLASSICAL_GROUP = "Classical"
FOOTER = ("Then add terms with the + of the Hamiltonian row in the outliner, and a "
          "calculation with the + of Calculations; Run ({run}) computes it, {help} explains "
          "any entry. <a href=\"guide\">guiqula's guide</a>")


def thumbnail(kind, name):
    """The path of a card's picture, or None when there is none (a
    lattice of a plugin, a preset added without running the tool)."""
    path = THUMBNAILS / FOLDERS[kind] / f"{name}.png"
    return path if path.is_file() else None


def first_sentence(text):
    """The first sentence of a text: up to the first full stop followed by
    a space and a capital or a parenthesis (decimals such as 2.2 do not end
    one)."""
    text = " ".join(text.split())
    return re.split(r"(?<=[.!?])\s+(?=[A-Z(])", text, maxsplit=1)[0]


def preset_info(name):
    """{name, title, description, sentence, teaching} of a shipped preset,
    from its notes (title on the first line) and its locks; read from the
    JSON file, without building the Document."""
    data = json.loads(project.preset_path(name).read_text(encoding="utf-8"))
    title, _, description = str(data.get("notes") or "").strip().partition("\n")
    description = " ".join(description.split())
    return {"name": name, "title": title.strip() or name, "description": description,
            "sentence": first_sentence(description), "teaching": bool(data.get("locks"))}


def presets():
    """preset_info of every shipped preset, as the gallery orders them: the
    teaching ones first, then the examples, each by title."""
    return sorted((preset_info(name) for name in project.presets()),
                  key=lambda info: (not info["teaching"], info["title"].lower()))


def card_search(name, title, sentence="", tag="", search=""):
    """The text the filter reads of a card."""
    return " ".join([name, title, sentence, tag, search]).lower()


def matches(words, text):
    """Whether every word of a filter appears in a card's text."""
    return all(word in text for word in words)


def mix(a, b, share):
    """A colour between a and b (share of a)."""
    return QColor(round(a.red() * share + b.red() * (1 - share)),
                  round(a.green() * share + b.green() * (1 - share)),
                  round(a.blue() * share + b.blue() * (1 - share)))


def wrap(text, metrics, width, lines):
    """The text broken into at most `lines` lines of a width, the last one
    elided when the text does not fit."""
    words, out = text.split(), []
    while words and len(out) < lines:
        line = words.pop(0)
        while words and metrics.horizontalAdvance(f"{line} {words[0]}") <= width:
            line += " " + words.pop(0)
        if len(out) == lines - 1 and words:
            line = metrics.elidedText(f"{line} {' '.join(words)}",
                                      Qt.TextElideMode.ElideRight, width)
            words = []
        elif metrics.horizontalAdvance(line) > width:
            line = metrics.elidedText(line, Qt.TextElideMode.ElideRight, width)
        out.append(line)
    return out


class Card(QAbstractButton):
    """A card: a picture of 160x120, a title and, for a preset, the first
    sentence of its notes; a click is the card's action. Painted from the
    palette at paint time, so a change of theme restyles it; checkable in
    the gallery, where a click selects and a double click opens."""
    double_clicked = Signal()

    def __init__(self, kind, name, title, sentence="", tag="", search="", tooltip="",
                 parent=None):
        super().__init__(parent)
        self.kind, self.name, self.title, self.sentence, self.tag = kind, name, title, \
            sentence, tag
        self.search = card_search(name, title, sentence, tag, search)
        self.picture = None
        self.picture_path = thumbnail(kind, name) if kind in FOLDERS else None
        self.deferred = False          # the start page reads the pictures after its first paint
        self.setObjectName(f"{PREFIXES[kind]}_{name}")
        self.setText(title)
        self.setToolTip(tooltip)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.double_clicked.emit()
        super().mouseDoubleClickEvent(event)

    def keyPressEvent(self, event):
        """Enter is a click too (Space already is), so Tab and Enter walk the page."""
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.click()
        else:
            super().keyPressEvent(event)

    def load_picture(self):
        """Read the picture (once); a card without one keeps its frame."""
        if self.picture is None and self.picture_path is not None:
            self.picture = QPixmap(str(self.picture_path))
            self.update()
        return self.picture is not None and not self.picture.isNull()

    def showEvent(self, event):
        """A card comes into sight (Show all, the filter): its picture, once
        the page has drawn itself (deferred until then)."""
        super().showEvent(event)
        if not self.deferred:
            self.load_picture()

    def _fonts(self):
        bold = QFont(self.font())
        bold.setBold(True)
        small = QFont(self.font())
        small.setPointSizeF(max(self.font().pointSizeF() - 1, 7.0))
        return bold, small

    def sizeHint(self):
        bold, small = self._fonts()
        title_lines, small_lines = LINES[self.kind]
        height = PAD + PICTURE.height() + PAD + title_lines * QFontMetrics(bold).lineSpacing() \
            + small_lines * QFontMetrics(small).lineSpacing()
        return QSize(PICTURE.width() + 2 * PAD, height + PAD)

    def minimumSizeHint(self):
        return self.sizeHint()

    def paintEvent(self, event):
        palette = self.palette()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        text = palette.color(QPalette.ColorRole.Text)
        base = palette.color(QPalette.ColorRole.Base)
        highlight = palette.color(QPalette.ColorRole.Highlight)
        enabled = self.isEnabled()
        lit = enabled and (self.underMouse() or self.hasFocus() or self.isDown())
        frame = QRect(0, 0, self.width() - 1, self.height() - 1)
        painter.setBrush(mix(highlight, base, 0.12) if self.isChecked() else base)
        painter.setPen(QPen(highlight if lit or self.isChecked() else mix(text, base, 0.22),
                            2 if self.isChecked() else 1))
        painter.drawRoundedRect(frame.adjusted(1, 1, -1, -1), 5, 5)
        picture = QRect(QPoint(PAD, PAD), PICTURE)
        if self.picture is not None and not self.picture.isNull():
            painter.drawPixmap(picture, self.picture)
        else:
            painter.fillRect(picture, mix(text, base, 0.06))
            if self.picture_path is None and self.tag:
                painter.setPen(mix(text, base, 0.5))
                painter.drawText(picture, Qt.AlignmentFlag.AlignCenter, self.tag)
        bold, small = self._fonts()
        title_lines = LINES[self.kind][0]
        width, bottom = PICTURE.width(), self.height() - PAD
        y = PAD + PICTURE.height() + PAD
        painter.setPen(text if enabled else mix(text, base, 0.5))
        painter.setFont(bold)
        metrics = QFontMetrics(bold)
        for line in wrap(self.title, metrics, width, title_lines):
            painter.drawText(PAD, y + metrics.ascent(), line)
            y += metrics.lineSpacing()
        painter.setFont(small)
        metrics = QFontMetrics(small)
        if self.kind == "preset":
            painter.setPen(palette.color(QPalette.ColorRole.Link))
            for line in wrap(self.tag, metrics, width, 2):
                painter.drawText(PAD, y + metrics.ascent(), line)
                y += metrics.lineSpacing()
        painter.setPen(mix(text, base, 0.7))
        room = max(0, (bottom - y) // metrics.lineSpacing())
        for line in wrap(self.sentence, metrics, width, room):
            painter.drawText(PAD, y + metrics.ascent(), line)
            y += metrics.lineSpacing()
        if self.kind in ("lattice", "classical") and self.picture is not None and self.tag:
            painter.setFont(small)            # the group in the picture's corner
            tag = QRect(PAD + 3, PAD + 3, metrics.horizontalAdvance(self.tag) + 8,
                        metrics.height() + 2)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(mix(base, text, 0.85))
            painter.drawRoundedRect(tag, 3, 3)
            painter.setPen(mix(text, base, 0.75))
            painter.drawText(tag, Qt.AlignmentFlag.AlignCenter, self.tag)


class RecentRow(QAbstractButton):
    """A recent file: its name, then its folder; a click opens it. A file
    that is gone is disabled and says so."""

    def __init__(self, index, path, parent=None):
        super().__init__(parent)
        self.kind, self.name, self.path = "recent", str(index), Path(path)
        self.search = str(path).lower()
        self.setObjectName(f"{PREFIXES['recent']}_{index}")
        self.setText(self.path.name)
        gone = not self.path.is_file()
        self.setEnabled(not gone)
        self.setToolTip(f"the file is gone: {path}" if gone else f"open {path}")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def sizeHint(self):
        return QSize(200, self.fontMetrics().lineSpacing() + 2 * PAD)

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.click()
        else:
            super().keyPressEvent(event)

    def paintEvent(self, event):
        palette = self.palette()
        painter = QPainter(self)
        text = palette.color(QPalette.ColorRole.Text)
        base = palette.color(QPalette.ColorRole.Base)
        if self.isEnabled() and (self.underMouse() or self.hasFocus()):
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            painter.setPen(QPen(palette.color(QPalette.ColorRole.Highlight), 1))
            painter.setBrush(base)
            painter.drawRoundedRect(QRect(0, 0, self.width() - 1, self.height() - 1), 4, 4)
        bold = QFont(self.font())
        bold.setBold(True)
        metrics = QFontMetrics(bold)
        y = (self.height() - metrics.height()) // 2 + metrics.ascent()
        painter.setFont(bold)
        painter.setPen(text if self.isEnabled() else mix(text, base, 0.5))
        name = self.path.name + ("  (gone)" if not self.isEnabled() else "")
        painter.drawText(PAD, y, name)
        x = PAD + metrics.horizontalAdvance(name) + 2 * PAD
        painter.setFont(self.font())
        painter.setPen(mix(text, base, 0.6))
        folder = self.fontMetrics().elidedText(str(self.path.parent), Qt.TextElideMode.ElideLeft,
                                               max(self.width() - x - PAD, 0))
        painter.drawText(x, y, folder)


class FlowLayout(QLayout):
    """Widgets left to right, wrapping at the width; a widget whose
    `breaks` attribute is true (a group heading) takes a line of its own.
    Hidden widgets take no room."""

    def __init__(self, parent=None, spacing=SPACING):
        super().__init__(parent)
        self.items = []
        self._height = None            # (width, height) of the last heightForWidth
        self.setSpacing(spacing)
        self.setContentsMargins(0, 0, 0, 0)

    def invalidate(self):
        self._height = None
        super().invalidate()

    def addItem(self, item):
        self.items.append(item)

    def count(self):
        return len(self.items)

    def itemAt(self, index):
        return self.items[index] if 0 <= index < len(self.items) else None

    def takeAt(self, index):
        return self.items.pop(index) if 0 <= index < len(self.items) else None

    def expandingDirections(self):
        return Qt.Orientation(0)

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        if self._height is None or self._height[0] != width:
            self._height = (width, self._arrange(QRect(0, 0, width, 0), move=False))
        return self._height[1]

    def setGeometry(self, rect):
        super().setGeometry(rect)
        self._arrange(rect, move=True)

    def sizeHint(self):
        return self.minimumSize()

    def minimumSize(self):
        size = QSize(0, 0)
        for item in self.items:
            if not item.isEmpty() and not getattr(item.widget(), "breaks", False):
                size = size.expandedTo(item.minimumSize())
        return size

    def per_row(self, width, item_width):
        return max(1, (width + self.spacing()) // (item_width + self.spacing()))

    def _arrange(self, rect, move):
        x, y, line = rect.x(), rect.y(), 0
        space = self.spacing()
        for item in self.items:
            if item.isEmpty():
                continue
            hint = item.sizeHint()
            if getattr(item.widget(), "breaks", False):
                if x > rect.x():
                    y += line + space
                height = item.heightForWidth(rect.width()) if item.hasHeightForWidth() \
                    else hint.height()
                if move:
                    item.setGeometry(QRect(rect.x(), y, rect.width(), height))
                y += height + space // 2
                x, line = rect.x(), 0
                continue
            if x > rect.x() and x + hint.width() > rect.right() + 1:
                x, y = rect.x(), y + line + space
                line = 0
            if move:
                item.setGeometry(QRect(QPoint(x, y), hint))
            x += hint.width() + space
            line = max(line, hint.height())
        return y + line - rect.y()


class Title(QWidget):
    """A bold line of text a few points above the widgets' font, painted in
    a font derived at paint time, so that it follows the interface text
    (a font set on a label stays at the size it had, under the style sheet)."""
    breaks = False

    def __init__(self, text, grow=0, muted=False, parent=None):
        super().__init__(parent)
        self._text, self.grow, self.muted = text, grow, muted
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)

    def text(self):
        return self._text

    def title_font(self):
        font = QFont(self.font())
        font.setBold(True)
        font.setPointSizeF(font.pointSizeF() + self.grow)
        return font

    def sizeHint(self):
        metrics = QFontMetrics(self.title_font())
        return QSize(metrics.horizontalAdvance(self._text) + 2, metrics.height() + 2)

    def minimumSizeHint(self):
        return self.sizeHint()

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() in (QEvent.Type.FontChange, QEvent.Type.ApplicationFontChange):
            self.updateGeometry()

    def paintEvent(self, event):
        palette = self.palette()
        text = palette.color(QPalette.ColorRole.WindowText)
        painter = QPainter(self)
        painter.setFont(self.title_font())
        painter.setPen(mix(text, palette.color(QPalette.ColorRole.Window), 0.6)
                       if self.muted else text)
        painter.drawText(self.rect(), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                         self._text)


class Heading(Title):
    """A group heading inside a band: a line of its own in the flow."""
    breaks = True


class Slot:
    """A card of a band, made when it comes into sight (Band.add_later):
    what the filter reads (kind, name, search, group) and make(), which
    returns the card; card is None until it is made."""
    __slots__ = ("kind", "name", "search", "group", "make", "card")

    def __init__(self, kind, name, search, group, make):
        self.kind, self.name, self.search, self.group, self.make = kind, str(name), search, \
            group, make
        self.card = None


class Band(QWidget):
    """A band of the page: a heading with its Show all toggle, the cards,
    and a line for when the filter leaves none. Until Show all (or while
    the filter has text) it shows one row of cards, the first ones."""

    def __init__(self, key, title, tooltip, noun, rows=False, parent=None):
        super().__init__(parent)
        self.setObjectName(f"startBand_{key}")
        self.key, self.rows, self.noun = key, rows, noun
        self.slots, self.headings = [], {}       # [Slot] in the band's order; group -> Heading
        self.order = []                          # the slots and the headings, in order
        self.expanded = False
        self.words = []
        self.heading = heading = Title(title, grow=2)
        heading.setObjectName(f"startHeading_{key}")
        heading.setToolTip(tooltip)
        self.more = QToolButton()
        self.more.setObjectName(f"startMore_{key}")
        self.more.setAutoRaise(True)
        self.more.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.icons_set = False          # the page sets them at its first show (set_more_icon)
        self.more.clicked.connect(lambda: self.set_expanded(not self.expanded))
        self.top = QHBoxLayout()
        self.top.setContentsMargins(0, 0, 0, 0)
        self.top.addWidget(heading)
        self.top.addStretch(1)
        self.top.addWidget(self.more)
        self.empty = QLabel()
        self.empty.setObjectName(f"startEmpty_{key}")
        self.empty_texts = ("", "")    # (the band has no card, the filter leaves none)
        self.empty.setEnabled(False)
        self.empty.setWordWrap(True)
        self.flow = QVBoxLayout() if rows else FlowLayout()
        if rows:
            self.flow.setSpacing(0)
            self.flow.setContentsMargins(0, 0, 0, 0)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        layout.addLayout(self.top)
        layout.addLayout(self.flow)
        layout.addWidget(self.empty)

    @property
    def cards(self):
        """Every card of the band, in its order, each made if it was not
        yet (tests, drivers); the page itself reads made() and the slots."""
        return [self.make(slot) for slot in self.slots]

    def made(self):
        """The cards made so far, in the band's order."""
        return [slot.card for slot in self.slots if slot.card is not None]

    def set_empty(self, none, unmatched):
        """What the band says when it has no card at all, and when the
        filter leaves none of its cards."""
        self.empty_texts = (none, unmatched)
        self.empty.setText(unmatched if self.slots else none)

    def add_heading(self, group):
        heading = Heading(group, muted=True)
        heading.setObjectName(f"startGroup_{group}")
        heading.hide()                 # shown with the band whole (update_cards)
        self.headings[group] = heading
        self.order.append(heading)
        self.flow.addWidget(heading)
        return heading

    def add(self, card, group=None):
        """A card made already (a recent file's row)."""
        slot = Slot(card.kind, card.name, card.search, group, None)
        slot.card = card
        card.group = group
        self.slots.append(slot)
        self.order.append(slot)
        self.flow.addWidget(card)
        self._chain(slot)
        return card

    def add_later(self, kind, name, search, group, make):
        """A card made when it first comes into sight (or is asked for by
        name): make() returns it. At start a band shows one row, so the
        other cards cost nothing until Show all or the filter."""
        slot = Slot(kind, name, search, group, make)
        self.slots.append(slot)
        self.order.append(slot)
        return slot

    def make(self, slot):
        """The card of a slot, made and put in its place in the flow."""
        if slot.card is None:
            card = slot.make()
            card.group = slot.group
            card.hide()                # update_cards shows it
            place = 0
            for entry in self.order:
                if entry is slot:
                    break
                if not isinstance(entry, Slot) or entry.card is not None:
                    place += 1
            self.flow.addWidget(card)
            self.flow.items.insert(place, self.flow.items.pop())
            self.flow.invalidate()
            slot.card = card
            self._chain(slot)
        return slot.card

    def _chain(self, slot):
        """Put a slot's card in the focus chain right after the nearest card
        made before it in the band, or after the band's heading row (Show
        all, Open a project) when none is: a widget that joins the page after
        its neighbours is otherwise the last of the window's chain, and Tab
        would leave the page before it reached the cards made in sight."""
        before = None
        for index in reversed(range(self.top.count())):
            before = self.top.itemAt(index).widget()
            if before is not None:
                break
        for entry in self.order:
            if entry is slot:
                break
            if isinstance(entry, Slot) and entry.card is not None:
                before = entry.card
        if before is not None and before.window() is slot.card.window():
            QWidget.setTabOrder(before, slot.card)

    def find(self, kind, name):
        """The card of a kind and a name, made if need be, or None."""
        for slot in self.slots:
            if slot.kind == kind and slot.name == str(name):
                return self.make(slot)
        return None

    def clear_cards(self):
        for card in self.made():
            self.flow.removeWidget(card)
            card.hide()
            card.setParent(None)       # gone from findChild now, its name free for another
            card.deleteLater()
        self.order = [entry for entry in self.order if not isinstance(entry, Slot)]
        self.slots = []

    def set_expanded(self, expanded):
        self.expanded = bool(expanded)
        self.update_cards()

    def shown(self):
        """How many cards are in sight while the band is folded."""
        if self.rows:
            return RECENT_SHOWN
        if not self.slots:
            return 0
        width = self.width() if self.width() > 0 else 600
        return self.flow.per_row(width, CARD.width())

    def filter(self, text):
        self.words = text.lower().split()
        self.update_cards()

    def update_cards(self):
        """Show the cards in sight (made now if they were not) and hide the
        others; returns the object names of the cards in sight."""
        matching = [slot for slot in self.slots if matches(self.words, slot.search)]
        whole = self.expanded or bool(self.words)
        limit = len(matching) if whole else self.shown()
        visible = set(map(id, matching[:limit]))
        for slot in matching[:limit]:
            self.make(slot)
        for slot in self.slots:
            if slot.card is not None:
                slot.card.setVisible(id(slot) in visible)
        for group, heading in self.headings.items():
            heading.setVisible(whole and any(id(s) in visible and s.group == group
                                             for s in self.slots))
        folded = len(matching) > self.shown()
        self.more.setVisible(not self.words and (folded or self.expanded))
        self.more.setText("Show fewer" if self.expanded else f"Show all {len(matching)}")
        self.more.setToolTip("show only the first row" if self.expanded else
                             f"show the {len(matching)} {self.noun}")
        self.set_more_icon()
        self.empty.setText(self.empty_texts[1] if self.slots else self.empty_texts[0])
        self.empty.setVisible(not matching)
        return [slot.card.objectName() for slot in self.slots if id(slot) in visible]

    def set_more_icon(self):
        """Show all's chevron, down while folded and up for Show fewer, once
        the page has set its icons (StartPage._set_icons)."""
        if self.icons_set:
            self.more.setIcon(icons.icon("collapse" if self.expanded else "expand"))
            self.more.setIconSize(icons.size())

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if not self.expanded and not self.words and event.size().width() != \
                event.oldSize().width():
            self.update_cards()


class StartPage(QWidget):
    """The start page, shown by the window in place of the viewport while
    the document has no system. Its signals carry what a card stands for;
    the window turns them into new_system, new_classical_system,
    open_document and its file dialog."""
    lattice_chosen = Signal(str)       # a lattice kind
    classical_chosen = Signal(str)     # a classical system kind
    preset_chosen = Signal(str)        # a preset name
    recent_chosen = Signal(str)        # a project file
    open_requested = Signal()
    guide_requested = Signal()

    def __init__(self, classical=None, parent=None):
        """classical: {kind: label} of the classical systems (the window's
        CLASSICAL_STARTS)."""
        super().__init__(parent)
        self.setObjectName("startPage")
        self._pictures_loaded = False
        # made from the top down, each part in its place at once: with the application's
        # style sheet, every new parent of a part styles its whole subtree again
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        top = QHBoxLayout()
        top.setContentsMargins(16, 10, 16, 0)
        layout.addLayout(top)
        self.search = QLineEdit(self)
        self.search.setObjectName("startSearch")
        self.search.setPlaceholderText("Filter the lattices, examples and recent files")
        self.search.setToolTip("type to narrow every band: a lattice by its name or "
                               "dimension, an example by its title or description, a file "
                               "by its name")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self.filter)
        self.search_icon = self.search.addAction(QIcon(),
                                                 QLineEdit.ActionPosition.LeadingPosition)
        top.addWidget(self.search)
        # made after the filter, which so comes first in the focus chain and has the focus
        self.scroll = QScrollArea(self)
        self.scroll.setObjectName("startScroll")
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        layout.addWidget(self.scroll, 1)
        content = QWidget()
        content.setObjectName("startContent")
        self.scroll.setWidget(content)
        column = QVBoxLayout(content)
        column.setContentsMargins(16, 8, 16, 12)
        column.setSpacing(14)
        self.lattices = Band("lattices", "Start from a lattice",
                             "a new system on a lattice: then shape it with geometry ops "
                             "(supercell, ribbon, island...) in the Geometry workspace",
                             "lattices and classical systems, by dimension", parent=content)
        # the cards are made as they come into sight (Band.add_later): at start one row of
        # each band, so the window shows sooner (tests/ui/test_startup.py)
        for spec in grouped("lattice"):
            if spec.group not in self.lattices.headings:
                self.lattices.add_heading(spec.group)
            self.lattices.add_later("lattice", spec.kind, card_search(
                spec.kind, spec.label, tag=spec.group, search=f"{spec.group} {spec.doc}"),
                spec.group, lambda spec=spec: self._lattice_card(spec))
        if classical:
            self.lattices.add_heading(CLASSICAL_GROUP)
            for kind, label in classical.items():
                self.lattices.add_later("classical", kind, card_search(
                    kind, label, tag="classical", search="classical"), CLASSICAL_GROUP,
                    lambda kind=kind, label=label: self._classical_card(kind, label))
        self.lattices.set_empty("No lattice is declared.", "No lattice matches the filter.")
        self.presets = Band("presets", "Open an example",
                            "documents shipped with guiqula, fully editable; the teaching "
                            "ones lock what their exercise keeps fixed", "examples",
                            parent=content)
        for info in presets():
            self.presets.add_later("preset", info["name"], card_search(
                info["name"], info["title"], info["sentence"],
                TEACHING if info["teaching"] else "", info["description"]), None,
                lambda info=info: self._preset_card(info))
        self.presets.set_empty("No example is shipped.", "No example matches the filter.")
        self.recent = Band("recent", "Recent files",
                           "the project files opened or saved last", "recent files",
                           rows=True, parent=content)
        self.open_button = QToolButton(self.recent)
        self.open_button.setObjectName("startOpenButton")
        self.open_button.setText("Open a project...")
        self.open_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.open_button.setToolTip(f"open a .guiqula project or a JSON document "
                                    f"({shortcuts.text('open')})")
        self.open_button.clicked.connect(self.open_requested)
        self.recent.top.addWidget(self.open_button)
        self.recent.set_empty("Projects you save or open will be listed here.",
                              "No recent file matches the filter.")
        self.footer = QLabel(FOOTER.format(run=shortcuts.text("run"),
                                           help=shortcuts.text("help")), self)
        self.footer.setObjectName("startFooter")
        self.footer.setWordWrap(True)
        self.footer.setToolTip("the guide opens in the Help panel")
        self.footer.setTextInteractionFlags(Qt.TextInteractionFlag.LinksAccessibleByMouse
                                            | Qt.TextInteractionFlag.LinksAccessibleByKeyboard)
        self.footer.linkActivated.connect(lambda link: self.guide_requested.emit())
        for band in (self.lattices, self.presets, self.recent):
            band.update_cards()            # folded before the first layout: fewer to place
            column.addWidget(band)
        column.addStretch(1)
        # under the scrolled bands rather than at their end, so that it is in sight at
        # 1200x800 whatever the interface text
        bottom = QHBoxLayout()
        bottom.setContentsMargins(16, 6, 16, 8)
        bottom.addWidget(self.footer)
        layout.addLayout(bottom)
        self.set_recent([])
        icons.follow(self, self._set_icons)

    def _set_icons(self):
        """The filter's search icon, Open a project's and the chevrons of
        Show all (icons.follow: at the page's first show and after every
        change of theme)."""
        self.search_icon.setIcon(icons.icon("search"))
        self.open_button.setIcon(icons.icon("open"))
        self.open_button.setIconSize(icons.size())
        for band in self.bands():
            band.icons_set = True
            band.set_more_icon()

    # ---- the cards, made as they come into sight
    def _lattice_card(self, spec):
        card = Card("lattice", spec.kind, spec.label, tag=spec.group,
                    search=f"{spec.group} {spec.doc}",
                    tooltip=f"<b>{spec.label}</b> ({spec.group})<br>{spec.doc}<br>A click "
                            f"adds a system on it (New system).")
        card.clicked.connect(lambda checked=False, k=spec.kind: self.lattice_chosen.emit(k))
        return self._deferred(card)

    def _classical_card(self, kind, label):
        card = Card("classical", kind, label, tag="classical", search="classical",
                    tooltip=f"<b>{label}</b><br>A classical system on its usual lattice, in "
                            f"a supercell (New system > Classical systems).")
        card.clicked.connect(lambda checked=False, k=kind: self.classical_chosen.emit(k))
        return self._deferred(card)

    def _preset_card(self, info):
        card = preset_card(info)
        card.clicked.connect(lambda checked=False, n=info["name"]: self.preset_chosen.emit(n))
        return self._deferred(card)

    def _deferred(self, card):
        """Before the page's first paint a card waits for load_pictures; after
        it, a card reads its picture as it comes into sight."""
        card.deferred = not self._pictures_loaded
        return card

    # ---- the bands
    def bands(self):
        return (self.lattices, self.presets, self.recent)

    def card(self, kind, name):
        """The card of a lattice, a classical system or a preset by its
        name, or the row of a recent file by its place (0: the newest)."""
        found = self.findChild(QAbstractButton, f"{PREFIXES[kind]}_{name}")
        for band in self.bands():
            if found is not None:
                break
            found = band.find(kind, name)
        if found is None:
            raise KeyError(f"no {kind} card {name!r}")
        return found

    def set_recent(self, paths):
        """The recent files (newest first), as the settings list them."""
        self.recent.clear_cards()
        for index, path in enumerate(paths):
            row = self.recent.add(RecentRow(index, path))
            row.clicked.connect(lambda checked=False, p=str(path): self.recent_chosen.emit(p))
        self.recent.update_cards()

    def filter(self, text=None):
        """Narrow every band to the cards matching the text (every word of
        it, in a card's name, title, group or description); returns the
        object names of the cards in sight."""
        if text is None:
            text = self.search.text()
        elif text != self.search.text():
            self.search.setText(text)          # filter() again through textChanged
            return self.visible_cards()
        for band in self.bands():
            band.filter(text)
        return self.visible_cards()

    def visible_cards(self):
        return [card.objectName() for band in self.bands() for card in band.made()
                if not card.isHidden()]

    # ---- the pictures, after the first paint
    def showEvent(self, event):
        super().showEvent(event)
        if not self._pictures_loaded:
            self._pictures_loaded = True
            QTimer.singleShot(0, self.load_pictures)

    def load_pictures(self, every=False):
        """Read the pictures of the cards in sight (of every card: every,
        each made if it was not), and let the others read theirs when they
        come into sight; returns the cards read that have none."""
        self._pictures_loaded = True
        missing = []
        cards = self.lattices.cards + self.presets.cards if every else \
            self.lattices.made() + self.presets.made()
        for card in cards:
            card.deferred = False
            if (every or not card.isHidden()) and not card.load_picture():
                missing.append(card.objectName())
        return missing


def preset_card(info, prefix=None):
    """The card of a preset (preset_info): its picture, its title, the
    teaching mark, the first sentence of its notes; the whole notes in the
    tooltip."""
    card = Card("preset", info["name"], info["title"], info["sentence"],
                TEACHING if info["teaching"] else "", search=info["description"],
                tooltip=f"<b>{info['title']}</b><p>{info['description']}</p>"
                        + (f"<p><i>Some parameters are locked for the exercise.</i></p>"
                           if info["teaching"] else "") + f"<p><i>{info['name']}</i></p>")
    if prefix:
        card.setObjectName(f"{prefix}_{info['name']}")
    return card
