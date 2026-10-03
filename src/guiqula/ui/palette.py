"""The Add menus (PLAN.md phase 8, package P2): one searchable menu per
family of registry entries (the lattices of New system, the geometry ops,
the terms, the calculations), opened from the place where the entry will
appear: the "+" of an outliner section, the toolbar's Add (the family of
the workspace) and New system, Ctrl+F.

A PaletteMenu has a search line at its top and then the entries of its
family that a kind of system takes, by group, each with the rich tooltip of
ui/formulas.py; a menu may end with items of its own (the classical
systems of New system, the mean field of the terms). Typing filters the
entries with search_entries, the best match is drawn in bold, and Enter
adds it. A letter typed while an entry has the keyboard goes to the search
line, so that QMenu never triggers an entry by its first letter. The
entries are made at the menu's first showing (or by prepare()), in the
colours of the theme of that moment, and made again when the kind of
system or the theme has changed since; the window never builds them at
startup, which keeps the formula images out of the start.

The menu says what was chosen (chosen, with the kind) and the window adds
it to the menu's system; it never touches the Document itself. It is shown
with popup(), never exec(), so that a click on its button returns at once
(tests and tools/drive.py click them).
"""
from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (QLineEdit, QMenu, QProxyStyle, QStyle, QStyleOptionToolButton,
                               QToolButton, QWidgetAction)

from guiqula.registry import base as registry
from guiqula.ui import formulas, theme

FAMILIES = ("lattice", "geometry_op", "term", "calculation")
# the prefix of the objectName of an entry's action, per family (kept from the toolbars)
PREFIXES = {"lattice": "newSystem", "geometry_op": "addOp", "term": "addTerm",
            "calculation": "addCalc"}
PLACEHOLDERS = {"lattice": "find a lattice", "geometry_op": "find an op",
                "term": "find a term", "calculation": "find a calculation"}


def grouped(family):
    """Registry entries sorted by group, then label."""
    return sorted(registry.entries(family), key=lambda s: (s.group, s.label))


def _search_rank(spec, text):
    """How well an entry matches a search (lower is better), or None."""
    label = spec.label.lower()
    if text in (label, f"{spec.label} ({spec.group})".lower(), spec.kind):
        return 0
    if label.startswith(text):
        return 1
    if any(word.startswith(text) for word in label.replace("-", " ").replace("/", " ").split()):
        return 2
    for rank, where in enumerate((label, spec.kind, spec.group.lower(), spec.doc.lower()), 3):
        if text in where:
            return rank
    return None


def search_entries(family, text):
    """Registry entries matching the text (case-insensitive), best first:
    the exact label (or "label (group)", or the kind), a label starting
    with it, a word of the label starting with it, then the text anywhere
    in the label, the kind, the group or the doc; ties in palette order."""
    text = text.strip().lower()
    if not text:
        return []
    found = [(_search_rank(spec, text), i, spec) for i, spec in enumerate(grouped(family))]
    return [spec for rank, _, spec in sorted(f for f in found if f[0] is not None)]


class MenuButton(QToolButton):
    """A tool button whose menu a click opens with popup() (the owner
    connects clicked), so that the click returns at once, where Qt's
    instant popup would run the menu's own event loop; a press held opens
    it too. Its arrow sits beside the text, as Qt draws it for an instant
    popup."""

    def __init__(self, text, menu, parent=None):
        super().__init__(parent)
        self.setText(text)
        self.setMenu(menu)
        self.setPopupMode(QToolButton.ToolButtonPopupMode.DelayedPopup)

    def sizeHint(self):
        hint = super().sizeHint()
        option = QStyleOptionToolButton()
        self.initStyleOption(option)
        room = self.style().pixelMetric(QStyle.PixelMetric.PM_MenuButtonIndicator, option, self)
        return QSize(hint.width() + room, hint.height())

    def minimumSizeHint(self):
        return self.sizeHint()


class ScrollingMenuStyle(QProxyStyle):
    """Fusion, with a menu taller than the screen scrolled rather than
    broken into columns."""

    def __init__(self):
        super().__init__("Fusion")

    def styleHint(self, hint, option=None, widget=None, data=None):
        if hint == QStyle.StyleHint.SH_Menu_Scrollable:
            return 1
        return super().styleHint(hint, option, widget, data)


class SearchLine(QLineEdit):
    """The search line: Enter stays here (QLineEdit lets it on to the
    menu, which would trigger its active entry a second time)."""

    def keyPressEvent(self, event):
        super().keyPressEvent(event)
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            event.accept()


class PaletteMenu(QMenu):
    """The entries of one family by group, under a search line
    (paletteSearch); objectName paletteMenu_<family>, entries
    <prefix>_<kind> (addOp_, addTerm_, addCalc_, newSystem_)."""
    chosen = Signal(str)             # the kind of the entry chosen (a click or Enter)
    not_found = Signal(str)          # Enter on a search nothing matches: the text

    def __init__(self, family, parent=None):
        super().__init__(parent)
        self.family = family
        self.prefix = PREFIXES.get(family, family)
        self.setObjectName(f"paletteMenu_{family}")
        self.setToolTipsVisible(True)
        # taller than the screen, it scrolls rather than breaking into columns, which would
        # leave a group's title at the foot of one and its entries at the head of the next
        self._style = ScrollingMenuStyle()
        self._style.setParent(self)
        self.setStyle(self._style)
        self.system = None           # the system the window adds the chosen entry to
        self.system_kind = "quantum"  # the kind of system whose entries it offers
        self.search = SearchLine(self)
        self.search.setObjectName("paletteSearch")
        self.search.setPlaceholderText(PLACEHOLDERS.get(family, "find"))
        self.search.setClearButtonEnabled(True)
        self.search.setToolTip("type part of a name, a group or a word of the description; "
                               "Enter adds the best match, drawn in bold")
        self.search.textChanged.connect(self.filter)
        self.search.returnPressed.connect(self.add_best)
        self.search_action = QWidgetAction(self)
        self.search_action.setObjectName("paletteSearch")
        self.search_action.setDefaultWidget(self.search)
        self.addAction(self.search_action)
        self.entries = {}            # kind -> QAction, for the kind of system it was made for
        self._extras = []            # (section, [(QAction, kinds of system or None)])
        self._sections = []          # [(section QAction, [its QActions])]
        self._made = None            # (kind of system, text colour) the entries were made in
        self.best = None             # the QAction Enter triggers, or None
        self.aboutToShow.connect(self.prepare)
        self.aboutToHide.connect(self.search.clear)

    # ---- contents
    def add_extra(self, section, text, name, tooltip, slot, kinds=None):
        """An item after the entries, in a section of its own: kinds are the
        kinds of system it is offered for (None: every kind). It takes part
        in the search by its text."""
        action = QAction(text, self)
        action.setObjectName(name)
        action.setToolTip(tooltip)
        action.triggered.connect(slot)
        for title, items in self._extras:
            if title == section:
                items.append((action, kinds))
                break
        else:
            self._extras.append((section, [(action, kinds)]))
        self._made = None            # shown at the next prepare()
        return action

    def offered(self):
        """The registry entries it offers for its kind of system."""
        return [spec for spec in grouped(self.family) if self.system_kind in spec.systems]

    def prepare(self, system_kind=None):
        """Make the entries for a kind of system (the one of the last call
        when left out), unless they were made for it in the colours of the
        theme of the moment. Returns the menu."""
        if system_kind is not None:
            self.system_kind = system_kind
        made = (self.system_kind, theme.TEXT)
        if self._made == made:
            return self
        self._made = made
        extras = {action for _, items in self._extras for action, _ in items}
        for section, actions in self._sections:
            for action in [section] + actions:
                self.removeAction(action)
                if action not in extras:
                    action.deleteLater()
        self._sections, self.entries = [], {}
        group, current = None, None
        for spec in self.offered():
            if spec.group != group or current is None:
                group = spec.group
                current = (self.addSection(group or "other"), [])
                current[0].setObjectName(f"paletteSection_{group}")
                self._sections.append(current)
            action = QAction(spec.label, self)
            action.setObjectName(f"{self.prefix}_{spec.kind}")
            action.setToolTip(formulas.entry_tooltip(spec))
            action.triggered.connect(lambda checked=False, k=spec.kind: self.chosen.emit(k))
            self.addAction(action)
            self.entries[spec.kind] = action
            current[1].append(action)
        for title, items in self._extras:
            section = self.addSection(title)
            section.setObjectName(f"paletteSection_{title}")
            for action, _ in items:
                self.addAction(action)
            self._sections.append((section, [action for action, _ in items]))
        self.filter()
        return self

    # ---- the search
    def _extra_offered(self, action):
        for _, items in self._extras:
            for extra, kinds in items:
                if extra is action:
                    return kinds is None or self.system_kind in kinds
        return False

    def filter(self, text=None):
        """Show the entries matching the text (all of them for none), the
        best match in bold; returns the objectNames shown, best first."""
        text = (self.search.text() if text is None else text).strip()
        matches = [self.entries[spec.kind] for spec in search_entries(self.family, text)
                   if spec.kind in self.entries] if text else list(self.entries.values())
        shown = set(matches)
        extras = [action for _, items in self._extras for action, _ in items
                  if self._extra_offered(action)
                  and (not text or text.lower() in action.text().lower())]
        shown.update(extras)
        for section, actions in self._sections:
            for action in actions:
                action.setVisible(action in shown)
            section.setVisible(any(action in shown for action in actions))
        self.best = (matches or extras or [None])[0] if text else None
        for action in list(self.entries.values()) + [a for _, items in self._extras
                                                      for a, _ in items]:
            font = action.font()
            if font.bold() != (action is self.best):
                font.setBold(action is self.best)
                action.setFont(font)
        listed = matches + extras
        return [action.objectName() for action in listed]

    def add_best(self):
        """Enter: add the best match of the search (an entry, or an item of
        the menu's own); returns its objectName, or None when nothing
        matches (not_found says so)."""
        text = self.search.text().strip()
        if not text:
            return None
        self.prepare()
        self.filter()
        best = self.best
        if best is None:
            self.not_found.emit(text)
            return None
        name = best.objectName()
        self.hide()
        self.search.clear()          # hiding clears it too, when the menu was shown
        best.trigger()
        return name

    def show_at(self, position, text=""):
        """Show the menu at a global position with the search line focused
        and the text typed in it (popup: it returns at once)."""
        self.prepare()
        self.search.setText(text)
        self.popup(position)
        self.search.setFocus(Qt.FocusReason.PopupFocusReason)
        return self

    def keyPressEvent(self, event):
        """A letter or a deletion that reaches the menu (an entry has the
        keyboard; the search line keeps the ones typed into it) goes to the
        search line: QMenu would trigger an entry by its first letter."""
        if not event.modifiers() & (
                Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.AltModifier) and (
                event.key() == Qt.Key.Key_Backspace or event.text().isprintable()
                and event.text().strip()):
            self.setActiveAction(self.search_action)
            self.search.setFocus(Qt.FocusReason.OtherFocusReason)
            if event.key() == Qt.Key.Key_Backspace:
                self.search.backspace()
            else:
                self.search.insert(event.text())
            event.accept()
            return
        super().keyPressEvent(event)
