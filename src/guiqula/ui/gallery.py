"""The presets gallery (PLAN.md section 4, decision 13.16): the documents
shipped with guiqula, by title, with the description in their notes; Open
loads one (it stays fully editable). quantum-lattice's modes became these
presets (decision 5: a convenience, not a one-to-one reproduction)."""
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QDialog, QHBoxLayout, QLabel, QListWidget, QListWidgetItem,
                               QPushButton, QVBoxLayout)

from guiqula.io import project


def preset_notes(name):
    """(title, description) of a shipped preset."""
    notes = project.load(name).notes.strip()
    title, _, description = notes.partition("\n")
    return title or name, description.strip()


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
        self.notes = {}
        for name in project.presets():
            title, description = preset_notes(name)
            self.notes[name] = (title, description)
            item = QListWidgetItem(title)
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
        self.list.setCurrentRow(0)

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
        title, description = self.notes[name]
        self.description.setText(f"<b>{title}</b><p>{description}</p><p><i>{name}</i></p>")

    def open(self, name):
        if name:
            self.opened.emit(name)
            self.close()
