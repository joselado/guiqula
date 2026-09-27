"""The presets gallery (PLAN.md section 4, decision 13.16): the documents
shipped with guiqula, by title, with the description in their notes; Open
loads one (it stays fully editable). quantum-lattice's modes became these
presets (decision 5: a convenience, not a one-to-one reproduction). Two
groups: teaching presets, which lock what their exercise keeps fixed
(core/locks.py), and examples (PLAN.md phase 5, design items 12 and 13)."""
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QDialog, QHBoxLayout, QLabel, QListWidget, QListWidgetItem,
                               QPushButton, QVBoxLayout)

from guiqula.io import project


GROUPS = (("teaching", "Teaching (some parameters locked)"), ("examples", "Examples"))


def preset_notes(name):
    """(title, description, group) of a shipped preset."""
    document = project.load(name)
    title, _, description = document.notes.strip().partition("\n")
    return title or name, description.strip(), "teaching" if document.locks else "examples"


class Gallery(QDialog):
    opened = Signal(str)            # the name of the preset to open

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("presetGallery")
        self.setWindowTitle("Presets")
        self.resize(720, 420)
        self.list = QListWidget()
        self.list.setObjectName("presetList")
        self.description = QLabel()
        self.description.setObjectName("presetDescription")
        self.description.setWordWrap(True)
        self.description.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self.description.setMinimumWidth(320)
        self.notes = {name: preset_notes(name) for name in project.presets()}
        for group, heading in GROUPS:
            names = sorted((n for n, notes in self.notes.items() if notes[2] == group),
                           key=lambda n: self.notes[n][0].lower())
            if not names:
                continue
            header = QListWidgetItem(heading)
            header.setFlags(Qt.ItemFlag.NoItemFlags)
            font = header.font()
            font.setBold(True)
            header.setFont(font)
            self.list.addItem(header)
            for name in names:
                item = QListWidgetItem("    " + self.notes[name][0])
                item.setData(Qt.ItemDataRole.UserRole, name)
                item.setToolTip(name)
                self.list.addItem(item)
        self.list.currentItemChanged.connect(self._show)
        self.list.itemDoubleClicked.connect(lambda item: self.open(self._name(item)))
        self.open_button = QPushButton("Open")
        self.open_button.setObjectName("openPresetButton")
        self.open_button.clicked.connect(lambda: self.open(self.current()))
        close = QPushButton("Close")
        close.setObjectName("closeGalleryButton")
        close.clicked.connect(self.close)
        row = QHBoxLayout()
        row.addWidget(self.list, 1)
        row.addWidget(self.description, 1)
        buttons = QHBoxLayout()
        buttons.addStretch(1)
        buttons.addWidget(self.open_button)
        buttons.addWidget(close)
        layout = QVBoxLayout(self)
        layout.addLayout(row, 1)
        layout.addLayout(buttons)
        self.list.setCurrentRow(1)

    @staticmethod
    def _name(item):
        return item.data(Qt.ItemDataRole.UserRole) if item is not None else None

    def current(self):
        return self._name(self.list.currentItem())

    def select(self, name):
        for row in range(self.list.count()):
            if self._name(self.list.item(row)) == name:
                self.list.setCurrentRow(row)
                return name
        raise KeyError(name)

    def _show(self, item, previous=None):
        name = self._name(item)
        if name is None:
            self.description.setText("")
            return
        title, description, group = self.notes[name]
        locked = ("<p><i>Some parameters are locked for the exercise (their fields are "
                  "greyed out); Edit &gt; Unlock everything lifts them.</i></p>"
                  if group == "teaching" else "")
        self.description.setText(f"<b>{title}</b><p>{description}</p>{locked}"
                                 f"<p><i>{name}</i></p>")

    def open(self, name):
        if name:
            self.opened.emit(name)
            self.close()
