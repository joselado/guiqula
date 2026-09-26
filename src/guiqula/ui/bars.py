"""Non-modal message bars at the top of the viewport (PLAN.md 3.5): the
error bar (an unexpected error, with its crash report) and the recovery
bar (work a crashed session left behind). Never a modal dialog, so the
window stays drivable from tools/drive.py and the tests."""
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QToolButton


class MessageBar(QFrame):
    def __init__(self, name, parent=None):
        super().__init__(parent)
        self.setObjectName(name)
        self.label = QLabel()
        self.label.setObjectName(f"{name}Text")
        self.label.setWordWrap(True)
        self.close_button = QToolButton()
        self.close_button.setText("×")
        self.close_button.setObjectName(f"{name}Close")
        self.close_button.setAutoRaise(True)
        self.close_button.clicked.connect(self.dismiss)
        self.row = QHBoxLayout(self)
        self.row.setContentsMargins(8, 4, 4, 4)
        self.row.addWidget(self.label, 1)
        self.row.addWidget(self.close_button)
        self.buttons = []
        self.hide()

    def show_message(self, text, buttons=()):
        """buttons: (text, callback, objectName) tuples, shown before ×."""
        for button in self.buttons:
            self.row.removeWidget(button)
            button.deleteLater()
        self.buttons = []
        for label, callback, name in buttons:
            button = QPushButton(label)
            button.setObjectName(name)
            button.clicked.connect(callback)
            self.row.insertWidget(self.row.count() - 1, button)
            self.buttons.append(button)
        self.label.setText(text)
        self.show()

    def button(self, name):
        return next((b for b in self.buttons if b.objectName() == name), None)

    def dismiss(self):
        self.hide()
