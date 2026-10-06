"""The grids of result views (decisions 170 to 180): a tab of the viewport
split into rows and columns, each cell holding the live view of one result,
the very PlotView its tab held, so that it keeps its bar, its status row,
its picks and its stale mark. A result goes into a cell by dragging its tab
from the viewport's bar onto the cell, or by the `grid_place` action; a
cell's title is dragged onto another cell to move it there (the two swap
when the other is taken), and onto the tab bar to give it back to its tab.

The window owns the placement (ui/mainwindow.py, `place_result`): a view is
in one place at a time, a tab, a window of its own or a cell, and this
module only shows cells and reports the drops. A drop carries the
calculation's id as `MIME`, and a drop is handled by `GridView.accept`,
which the tests call directly, since a real QDrag does not run offscreen.
"""
from PySide6.QtCore import QMimeData, QPoint, Qt, Signal
from PySide6.QtGui import QColor, QDrag, QPainter, QPalette, QPen
from PySide6.QtWidgets import (QApplication, QFrame, QHBoxLayout, QLabel,
                               QMenu, QSizePolicy, QSpinBox, QTabBar, QToolButton, QVBoxLayout,
                               QWidget)

from guiqula.ui import icons, theme

MIME = "application/x-guiqula-result"       # the calculation id, as UTF-8
MAX_SIDE = 4                                # rows or columns of a grid at most
EMPTY_TEXT = "Drag a result's tab here, or"
SAVE_TIP = "save the whole grid as an image (PNG), as it is shown"


def mime_of(calc):
    data = QMimeData()
    data.setData(MIME, calc.encode())
    return data


def calc_of(mime):
    """The calculation id a drop carries, or None for anything else."""
    if mime is None or not mime.hasFormat(MIME):
        return None
    return bytes(mime.data(MIME)).decode() or None


def start_drag(source, calc):
    """Drag a result (from its tab or its cell's title); returns the drop's action."""
    drag = QDrag(source)
    drag.setMimeData(mime_of(calc))
    return drag.exec(Qt.DropAction.MoveAction)


class ResultTabBar(QTabBar):
    """The viewport's tab bar: a result's tab can be dragged out onto a cell
    of a grid (`calc_at(index)` says which tabs are results). Pressing the
    tab shows the result, which hides the grid, so a drag held over a Grid
    tab shows that grid at once (`grid_at(index)` says which tabs are
    grids), and the drag goes on into a cell; a result dropped on a Grid
    tab goes into that grid's first free cell (`dropped_on_grid`), and one
    dropped anywhere else on the bar back to its tab (`dropped`)."""

    dropped = Signal(str)                   # calculation id
    dropped_on_grid = Signal(str, str)      # calculation id, grid id

    def __init__(self, calc_at, grid_at=lambda index: None, parent=None):
        super().__init__(parent)
        self.calc_at = calc_at
        self.grid_at = grid_at
        self._press = None
        self.setAcceptDrops(True)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._press = (event.position().toPoint(), self.tabAt(event.position().toPoint()))
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._press is not None and event.buttons() & Qt.MouseButton.LeftButton:
            point, index = self._press
            moved = (event.position().toPoint() - point).manhattanLength()
            calc = self.calc_at(index) if index >= 0 else None
            if calc and moved >= QApplication.startDragDistance():
                self._press = None
                start_drag(self, calc)
                return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self._press = None
        super().mouseReleaseEvent(event)

    def dragEnterEvent(self, event):
        # accepted for any result, so the bar switches tabs under the drag
        if calc_of(event.mimeData()) is not None:
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dragMoveEvent(self, event):
        if calc_of(event.mimeData()) is None:
            return super().dragMoveEvent(event)
        event.acceptProposedAction()
        index = self.tabAt(event.position().toPoint())
        if index >= 0 and self.grid_at(index) is not None and index != self.currentIndex():
            self.setCurrentIndex(index)         # the grid's cells in sight under the drag

    def dropEvent(self, event):
        calc = calc_of(event.mimeData())
        if calc is None:
            return super().dropEvent(event)
        event.acceptProposedAction()
        grid_id = self.grid_at(self.tabAt(event.position().toPoint()))
        if grid_id is not None:
            self.dropped_on_grid.emit(calc, grid_id)
        else:
            self.dropped.emit(calc)


class CellTitle(QWidget):
    """The title of a taken cell: the result's name and state, which a click
    selects and a drag moves, and the button giving it back to its tab."""

    clicked = Signal()

    def __init__(self, name, parent=None):
        super().__init__(parent)
        self.calc = None
        self._press = None
        self.label = QLabel("")
        self.label.setObjectName(f"gridCellTitle_{name}")
        self.release = QToolButton()
        self.release.setObjectName(f"gridRelease_{name}")
        self.release.setAutoRaise(True)
        self.release.setToolTip("give this result back to its tab in the viewport (or drag "
                                "the title onto the tab bar)")
        icons.follow(self.release, lambda: self.release.setIcon(icons.icon("close")))
        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 2, 2, 0)
        layout.addWidget(self.label, 1)
        layout.addWidget(self.release)
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        self.setToolTip("click to select this calculation; drag onto another cell to move "
                        "it there (the two swap), or onto the tab bar to give it back")

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._press = event.position().toPoint()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._press is not None and self.calc and event.buttons() & Qt.MouseButton.LeftButton:
            if (event.position().toPoint() - self._press).manhattanLength() >= \
                    QApplication.startDragDistance():
                self._press = None
                start_drag(self, self.calc)
                return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self._press is not None and event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        self._press = None
        super().mouseReleaseEvent(event)


class GridCell(QFrame):
    """One cell of a grid: a title and the view, or the empty state, under a
    frame drawn in the highlight colour while a result is dragged over it."""

    dropped = Signal(str)               # calculation id
    chosen = Signal(str)                # calculation id: its title was clicked
    release_requested = Signal(str)     # calculation id

    def __init__(self, grid_id, row, col, offer=lambda: [], parent=None):
        super().__init__(parent)
        name = f"{grid_id}_{row}_{col}"
        self.offer = offer          # () -> [(calculation id, its text)] the Choose menu lists
        self.setObjectName(f"gridCell_{name}")
        self.row, self.col = row, col
        self.view = None
        self.calc = None
        self._hover = False
        self.setAcceptDrops(True)
        # every cell its share of the grid, whatever its view asks for
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored)
        self.title = CellTitle(name)
        self.title.clicked.connect(lambda: self.calc and self.chosen.emit(self.calc))
        self.title.release.clicked.connect(
            lambda: self.calc and self.release_requested.emit(self.calc))
        self.title.hide()
        # the empty state: the drag, and a menu of the results for who does not drag
        self.empty = QWidget()
        self.empty.setObjectName(f"gridEmpty_{name}")
        hint = QLabel(EMPTY_TEXT)
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hint.setWordWrap(True)
        hint.setEnabled(False)                     # drawn in the muted text colour
        self.choose = QToolButton()
        self.choose.setObjectName(f"gridChoose_{name}")
        self.choose.setText("Choose a result")
        self.choose.setToolTip("show a calculation's result in this cell")
        self.choose.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.choose.setMenu(QMenu(self.choose))
        self.choose.menu().setObjectName(f"gridChooseMenu_{name}")
        self.choose.menu().aboutToShow.connect(self._fill_choose)
        column = QVBoxLayout(self.empty)
        column.addStretch(1)
        column.addWidget(hint)
        column.addWidget(self.choose, 0, Qt.AlignmentFlag.AlignHCenter)
        column.addStretch(1)
        self.body = QVBoxLayout(self)
        # the view's minimum size is not the cell's: CellArea gives it its share, and
        # setGeometry would otherwise grow it back to what the view asks
        self.body.setSizeConstraint(QVBoxLayout.SizeConstraint.SetNoConstraint)
        self.body.setContentsMargins(2, 2, 2, 2)
        self.body.setSpacing(0)
        self.body.addWidget(self.title)
        self.body.addWidget(self.empty, 1)

    def put(self, view, calc):
        """Hold a view (taken out of wherever it was by the window)."""
        self.view, self.calc = view, calc
        self.title.calc = calc
        self.empty.hide()
        self.title.show()
        self.body.addWidget(view, 1)
        view.show()

    def take(self):
        """Give the view back (unparented), or None for an empty cell."""
        view = self.view
        if view is not None:
            self.body.removeWidget(view)
            view.setParent(None)
        self.view = self.calc = self.title.calc = None
        self.title.hide()
        self.empty.show()
        return view

    def _fill_choose(self):
        menu = self.choose.menu()
        menu.clear()
        offered = self.offer()
        for calc, text in offered:
            menu.addAction(text, lambda c=calc: self.dropped.emit(c))
        if not offered:
            menu.addAction("no calculation yet").setEnabled(False)

    def set_title(self, text, error=False, tip=""):
        self.title.label.setText(text)
        palette = self.title.label.palette()
        palette.setColor(QPalette.ColorRole.WindowText,
                         QColor(theme.COLORS[theme.name]["ERROR"]) if error
                         else self.palette().color(QPalette.ColorRole.WindowText))
        self.title.label.setPalette(palette)
        self.title.label.setToolTip(tip)

    def dragEnterEvent(self, event):
        if calc_of(event.mimeData()) is not None:
            self._hover = True
            self.update()
            event.acceptProposedAction()

    def dragLeaveEvent(self, event):
        self._hover = False
        self.update()

    def dropEvent(self, event):
        self._hover = False
        self.update()
        calc = calc_of(event.mimeData())
        if calc is not None:
            event.acceptProposedAction()
            self.dropped.emit(calc)

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        if self._hover:
            pen = QPen(self.palette().color(QPalette.ColorRole.Highlight), 2)
        else:
            pen = QPen(QColor(theme.COLORS[theme.name]["GRID"]), 1)
        painter.setPen(pen)
        painter.drawRect(self.rect().adjusted(0, 0, -1, -1))
        painter.end()


class CellArea(QWidget):
    """Where the cells sit, each placed by hand at an equal share of the
    area: a layout would give a row holding a view the view's minimum
    height, and leave an empty row a sliver."""

    MARGIN = 4
    SPACING = 4

    def __init__(self, grid):
        super().__init__()
        self.grid = grid
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    def place(self):
        rows, cols = max(self.grid.rows, 1), max(self.grid.cols, 1)
        width = self.width() - 2 * self.MARGIN - (cols - 1) * self.SPACING
        height = self.height() - 2 * self.MARGIN - (rows - 1) * self.SPACING
        for (row, col), cell in self.grid.cells.items():
            x0 = self.MARGIN + col * self.SPACING + col * width // cols
            x1 = self.MARGIN + col * self.SPACING + (col + 1) * width // cols
            y0 = self.MARGIN + row * self.SPACING + row * height // rows
            y1 = self.MARGIN + row * self.SPACING + (row + 1) * height // rows
            cell.setGeometry(x0, y0, max(x1 - x0, 0), max(y1 - y0, 0))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.place()


class GridView(QWidget):
    """A tab of rows by columns of cells (`grid_<id>`), with its bar: the
    number of rows and of columns, and Save image. The window moves the
    views in and out (`put`, `take`); what is shown where is `placed()`."""

    shape_requested = Signal(str, int, int)        # grid id, rows, columns
    drop_requested = Signal(str, str, int, int)    # calculation, grid id, row, column
    chosen = Signal(str)                           # calculation id
    release_requested = Signal(str)                # calculation id
    save_requested = Signal(str)                   # grid id

    def __init__(self, grid_id, rows=2, cols=2, parent=None):
        super().__init__(parent)
        self.grid_id = grid_id
        self.setObjectName(f"grid_{grid_id}")
        self.bar = QWidget()
        self.bar.setObjectName(f"gridBar_{grid_id}")
        line = QHBoxLayout(self.bar)
        line.setContentsMargins(4, 4, 4, 0)
        self.spins = {}
        for key, text, tip in (("rows", "Rows", "rows of the grid; a result in a row taken "
                                                "away goes back to its tab"),
                               ("cols", "Columns", "columns of the grid; a result in a column "
                                                   "taken away goes back to its tab")):
            label = QLabel(text)
            spin = QSpinBox()
            spin.setObjectName(f"grid{key.capitalize()}_{grid_id}")
            spin.setRange(1, MAX_SIDE)
            spin.setToolTip(tip)
            label.setToolTip(tip)
            label.setBuddy(spin)
            line.addWidget(label)
            line.addWidget(spin)
            self.spins[key] = spin
        line.addStretch(1)
        self.save = QToolButton()
        self.save.setObjectName(f"gridSave_{grid_id}")
        self.save.setToolTip(SAVE_TIP)
        self.save.setText("Save image")
        self.save.clicked.connect(lambda: self.save_requested.emit(self.grid_id))
        icons.follow(self.save, lambda: self.save.setIcon(icons.icon("image")))
        line.addWidget(self.save)
        self.area = CellArea(self)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.bar)
        layout.addWidget(self.area, 1)
        self.offer = lambda: []           # what an empty cell's Choose menu lists (the window)
        self.cells = {}                   # (row, column) -> GridCell
        self.rows = self.cols = 0
        self.set_shape(rows, cols)
        for spin in self.spins.values():
            spin.valueChanged.connect(lambda _: self.shape_requested.emit(
                self.grid_id, self.spins["rows"].value(), self.spins["cols"].value()))

    def set_shape(self, rows, cols):
        """Make the cells of rows x cols; the cells that go away must be
        empty (the window gives their views back first)."""
        for key in [k for k in self.cells if k[0] >= rows or k[1] >= cols]:
            cell = self.cells.pop(key)
            assert cell.view is None, "a cell that goes away holds a view"
            cell.deleteLater()
        for row in range(rows):
            for col in range(cols):
                if (row, col) not in self.cells:
                    cell = GridCell(self.grid_id, row, col, lambda: self.offer())
                    cell.dropped.connect(lambda calc, r=row, c=col: self.accept(calc, r, c))
                    cell.chosen.connect(self.chosen)
                    cell.release_requested.connect(self.release_requested)
                    self.cells[row, col] = cell
                    cell.setParent(self.area)
                    cell.show()
        self.rows, self.cols = rows, cols
        self.area.place()
        for key, value in (("rows", rows), ("cols", cols)):
            spin = self.spins[key]
            spin.blockSignals(True)
            spin.setValue(value)
            spin.blockSignals(False)

    def accept(self, calc, row, col):
        """A result dropped on a cell: the window places it."""
        self.drop_requested.emit(calc, self.grid_id, row, col)

    def cell(self, row, col):
        return self.cells[row, col]

    def placed(self):
        """{(row, column): calculation id} of the taken cells."""
        return {key: cell.calc for key, cell in self.cells.items() if cell.calc is not None}

    def where(self, calc):
        """(row, column) of the cell holding calc, or None."""
        return next((key for key, cell in self.cells.items() if cell.calc == calc), None)

    def outside(self, rows, cols):
        """The results in the cells that a shape of rows x cols leaves out."""
        return [cell.calc for (r, c), cell in self.cells.items()
                if cell.calc is not None and (r >= rows or c >= cols)]
