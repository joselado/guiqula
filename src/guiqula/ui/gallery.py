"""The presets gallery (PLAN.md section 4, decision 13.16): the documents
shipped with guiqula as the start page's preset cards (ui/start.py, PLAN.md
phase 8, package P1), a picture, the title and the first sentence of the
notes, with the whole description beside them; a click selects a card,
Open or a double click loads it (it stays fully editable). quantum-lattice's
modes became these presets (decision 5: a convenience, not a one-to-one
reproduction). Two groups: teaching presets, which lock what their exercise
keeps fixed (core/locks.py), and examples (PLAN.md phase 5, design items 12
and 13)."""
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QButtonGroup, QDialog, QFrame, QHBoxLayout, QLabel, QPushButton,
                               QScrollArea, QVBoxLayout, QWidget)

from guiqula.ui.start import FlowLayout, preset_card, preset_info, presets

GROUPS = (("teaching", "Teaching (some parameters locked)"), ("examples", "Examples"))


def preset_notes(name):
    """(title, description, group) of a shipped preset."""
    info = preset_info(name)
    return info["title"], info["description"], "teaching" if info["teaching"] else "examples"


class Gallery(QDialog):
    opened = Signal(str)            # the name of the preset to open

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("presetGallery")
        self.setWindowTitle("Presets")
        self.resize(940, 600)
        infos = presets()
        self.notes = {info["name"]: (info["title"], info["description"],
                                     "teaching" if info["teaching"] else "examples")
                      for info in infos}
        self.cards = {}                 # preset name -> its card (galleryPreset_<name>)
        self.buttons = QButtonGroup(self)
        self.buttons.setExclusive(True)
        content = QWidget()
        column = QVBoxLayout(content)
        column.setContentsMargins(8, 8, 8, 8)
        column.setSpacing(8)
        for group, heading in GROUPS:
            members = sorted((i for i in infos if (i["teaching"]) == (group == "teaching")),
                             key=lambda i: i["title"].lower())
            if not members:
                continue
            label = QLabel(heading)
            label.setObjectName(f"galleryGroup_{group}")
            font = label.font()
            font.setBold(True)
            label.setFont(font)
            column.addWidget(label)
            flow = FlowLayout()
            for info in members:
                card = preset_card(info, prefix="galleryPreset")
                card.setCheckable(True)
                card.toggled.connect(lambda on, n=info["name"]: on and self._show(n))
                card.double_clicked.connect(lambda n=info["name"]: self.open(n))
                card.load_picture()
                self.buttons.addButton(card)
                self.cards[info["name"]] = card
                flow.addWidget(card)
            column.addLayout(flow)
        column.addStretch(1)
        self.list = QScrollArea()
        self.list.setObjectName("presetList")
        self.list.setWidgetResizable(True)
        self.list.setFrameShape(QFrame.Shape.NoFrame)
        self.list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.list.setWidget(content)
        self.description = QLabel()
        self.description.setObjectName("presetDescription")
        self.description.setWordWrap(True)
        self.description.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self.description.setMinimumWidth(280)
        self.description.setMaximumWidth(340)
        self.open_button = QPushButton("Open")
        self.open_button.setObjectName("openPresetButton")
        self.open_button.setToolTip("open the preset selected (a double click on a card does "
                                    "it too)")
        self.open_button.clicked.connect(lambda: self.open(self.current()))
        close = QPushButton("Close")
        close.setObjectName("closeGalleryButton")
        close.clicked.connect(self.close)
        row = QHBoxLayout()
        row.addWidget(self.list, 1)
        row.addWidget(self.description)
        buttons = QHBoxLayout()
        buttons.addStretch(1)
        buttons.addWidget(self.open_button)
        buttons.addWidget(close)
        layout = QVBoxLayout(self)
        layout.addLayout(row, 1)
        layout.addLayout(buttons)
        first = next(iter(self.cards), None)
        if first is not None:
            self.select(first)

    def names(self):
        """The presets in the order the gallery shows them."""
        return list(self.cards)

    def current(self):
        card = self.buttons.checkedButton()
        return card.name if card is not None else None

    def select(self, name):
        if name not in self.cards:
            raise KeyError(name)
        self.cards[name].setChecked(True)
        self.list.ensureWidgetVisible(self.cards[name])
        self._show(name)
        return name

    def _show(self, name):
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
