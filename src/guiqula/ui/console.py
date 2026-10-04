"""The Python console (PLAN.md section 4, decision 14.1): a thin view of the
console worker, where the code runs (pyqula stays out of the UI process,
13.15, and a crash in the console cannot take the window down). Enter
runs the input, Shift+Enter adds a line, Up and Down walk the history;
Interrupt stops what runs and starts the console afresh (its variables are
lost, as when a kernel restarts). The window sends the code to the
Session and writes what comes back."""
from PySide6.QtCore import QEvent, Qt, QTimer, Signal
from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import (QHBoxLayout, QLabel, QPlainTextEdit, QPushButton, QVBoxLayout,
                               QWidget)

from guiqula.ui import theme

PLACEHOLDER = ("Python, run in the worker: g and h (the geometry and Hamiltonian of the "
               "selected system), doc (the document), do(command, **args) (a command, "
               "undoable), np, pyqula. Enter runs, Shift+Enter adds a line, Up/Down: history.")


class ConsoleWidget(QWidget):
    run_requested = Signal(str)
    interrupt_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("console")
        self.output = QPlainTextEdit()
        self.output.setObjectName("consoleOutput")
        self.output.setReadOnly(True)
        self.output.setMaximumBlockCount(5000)
        self.input = QPlainTextEdit()
        self.input.setObjectName("consoleInput")
        self.input.setPlaceholderText(PLACEHOLDER)
        # the fixed-width font at the console's first show (_follow_font): its first use
        # costs about 6 ms, and the console is hidden at start (tests/ui/test_startup.py)
        self._fonts_set = False
        self.input.installEventFilter(self)
        self.system_label = QLabel("")
        self.system_label.setObjectName("consoleSystem")
        self.run_button = QPushButton("Run")
        self.run_button.setObjectName("consoleRun")
        self.run_button.clicked.connect(self.submit)
        self.interrupt_button = QPushButton("Interrupt")
        self.interrupt_button.setObjectName("consoleInterrupt")
        self.interrupt_button.setToolTip("stop what runs; the console starts afresh and its "
                                         "variables are lost")
        self.interrupt_button.clicked.connect(self.interrupt_requested.emit)
        buttons = QVBoxLayout()
        buttons.addWidget(self.run_button)
        buttons.addWidget(self.interrupt_button)
        buttons.addWidget(self.system_label)
        buttons.addStretch(1)
        row = QHBoxLayout()
        row.addWidget(self.input, 1)
        row.addLayout(buttons)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.addWidget(self.output, 1)
        layout.addLayout(row)
        self.history = []
        self._position = 0

    def showEvent(self, event):
        super().showEvent(event)
        if not self._fonts_set:
            self._follow_font()

    def changeEvent(self, event):
        """View > Interface text: the fixed-width font at the new size, once
        the change is over (the style sheet's repolish, which comes after,
        gives each box back the font it had when it was first polished)."""
        super().changeEvent(event)
        if event.type() == QEvent.Type.FontChange and self._fonts_set:
            QTimer.singleShot(0, self._follow_font)

    def _follow_font(self):
        """The fixed-width font of the desktop at the interface text's points."""
        self._fonts_set = True
        font = theme.fixed_font(self.font().pointSizeF())
        for box in (self.output, self.input):
            box.setFont(font)
        self.input.setMaximumHeight(4 * self.input.fontMetrics().lineSpacing() + 12)

    def eventFilter(self, watched, event):
        if watched is self.input and event.type() == QEvent.Type.KeyPress:
            key, shift = event.key(), event.modifiers() & Qt.KeyboardModifier.ShiftModifier
            cursor = self.input.textCursor()
            if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and not shift:
                self.submit()
                return True
            if key == Qt.Key.Key_Up and cursor.blockNumber() == 0:
                self.recall(-1)
                return True
            if key == Qt.Key.Key_Down and cursor.blockNumber() == self.input.blockCount() - 1:
                self.recall(1)
                return True
        return super().eventFilter(watched, event)

    def recall(self, step):
        """Show an earlier (-1) or later (+1) command of the history."""
        if not self.history:
            return
        self._position = min(max(self._position + step, 0), len(self.history))
        text = self.history[self._position] if self._position < len(self.history) else ""
        self.input.setPlainText(text)
        self.input.moveCursor(QTextCursor.MoveOperation.End)

    def submit(self):
        """Echo the input and ask for it to run."""
        code = self.input.toPlainText()
        if not code.strip():
            return None
        if not self.history or self.history[-1] != code:
            self.history.append(code)
        self._position = len(self.history)
        lines = code.rstrip("\n").split("\n")
        self.write("\n".join([">>> " + lines[0]] + ["... " + line for line in lines[1:]]))
        self.input.clear()
        self.run_requested.emit(code)
        return code

    def write(self, text, error=False):
        if error:
            text = "\n".join("! " + line for line in text.split("\n"))
        self.output.appendPlainText(text)
        self.output.moveCursor(QTextCursor.MoveOperation.End)

    def set_system(self, system):
        self.system_label.setText(f"g, h: {system}" if system else "no system")

    def set_busy(self, busy):
        self.run_button.setEnabled(not busy)
