"""Non-modal message bars at the top of the viewport (PLAN.md 3.5): the
error bar (an unexpected error, with its crash report) and the recovery
bar (work a crashed session left behind). Never a modal dialog, so the
window stays drivable from tools/drive.py and the tests.

StatusMessage is the last message of the window in the status bar (PLAN.md
phase 8, package P5), since the Log under the viewport is hidden by
default: its first line, cut to the room there is, the whole text in its
tooltip, in the error colour for an error."""
from PySide6.QtCore import QEvent, Qt
from PySide6.QtWidgets import (QFrame, QHBoxLayout, QLabel, QPushButton, QSizePolicy,
                               QToolButton)


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


class StatusMessage(QLabel):
    """The last message, after the system summary in the status bar: its
    first line, elided to the width it is given (a long message never
    widens the window), the whole text in the tooltip; an error is drawn
    in the theme's error colour, through the property error, which the
    style sheet of ui/theme.py colours, so that a change of theme follows."""

    def __init__(self, name="statusMessage", parent=None):
        super().__init__(parent)
        self.setObjectName(name)
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.setProperty("error", False)
        self.message = ""          # the whole text of the last message
        self.error = False

    def show_message(self, text, error=False):
        self.message, self.error = text, bool(error)
        if self.property("error") != self.error:
            self.setProperty("error", self.error)
            self.style().unpolish(self)
            self.style().polish(self)
        self.setToolTip(text)
        self._elide()

    def _elide(self):
        line = self.message.splitlines()[0] if self.message else ""
        self.setText(self.fontMetrics().elidedText(line, Qt.TextElideMode.ElideRight,
                                                   max(self.contentsRect().width(), 0)))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._elide()

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() == QEvent.Type.FontChange:      # View > Interface text
            self._elide()
