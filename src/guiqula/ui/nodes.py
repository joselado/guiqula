"""The node view (PLAN.md phase 9, part C, decisions 226 to 231): the
Document drawn as a graph, Blender's node editor for the geometries, the
k-paths, the systems, the embeddings and the calculations, as the
alternative view of the Outliner dock (OutlinerPanel: Tree or Nodes).

It is a QGraphicsView (Qt's own, which renders offscreen too), and it holds
nothing but view state: the graph is registry/graph.py's, read from the
Document at every refresh, and every edit goes out as a signal for the
window to run as a Command, as the tree's do, which is what keeps the two
views consistent by construction. A node shows its id, its kind (a system
is a Hamiltonian or a Model), its name and, for a calculation, the mark of
ui/marks.py its tab and its row read; its inputs on the left, each named,
its output on the right. A drag from an output to an input asks for that
link (connect_requested); a right click on an input whose link may be cut
offers Cut (cut_requested); a node dragged reports its place (moved), kept
by the window in the ui block; a click selects (selected), a double click
opens (activated: a k-path's zone window, a calculation's result); Shift+A
asks for the Add menu at the cursor (add_requested), Del for a removal
(delete_requested), Home frames everything.

Its widgets: nodeView, and in the panel outlinerViewTabs (Tree, Nodes),
outlinerStack and nodeArrange. The items are no widgets: tests and drivers
read NodeView.node_items ({node id: NodeItem}) and NodeView.link_items."""
from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QCursor, QFont, QFontMetricsF, QPainter, QPainterPath, \
    QPen
from PySide6.QtWidgets import (QGraphicsEllipseItem, QGraphicsItem, QGraphicsPathItem,
                               QGraphicsScene, QGraphicsView, QHBoxLayout, QMenu,
                               QStackedWidget, QTabBar, QToolButton, QVBoxLayout, QWidget)

from guiqula.registry import graph as graph_tools
from guiqula.ui import marks, theme

WIDTH = 180          # a node's width, in scene units
HEADER = 22          # its title bar
LINE = 18            # a line of text or a socket's row
RADIUS = 5           # a socket's
STYLES = {"solid": Qt.PenStyle.SolidLine, "dashed": Qt.PenStyle.DashLine,
          "dotted": Qt.PenStyle.DotLine}


def kind_color(kind):
    """The colour of a node's title bar, by kind, in the active theme."""
    return {"geometry": theme.CELL, "kpath": theme.REGION, "system": theme.SUBLATTICE[-1.0],
            "embedding": theme.POINT, "junction": theme.POINT,
            "calculation": theme.SELECTED}.get(kind, theme.MUTED)


class SocketItem(QGraphicsEllipseItem):
    """An input (named, on the left) or the output (on the right) of a node."""

    def __init__(self, node, name, is_input, parent):
        super().__init__(-RADIUS, -RADIUS, 2 * RADIUS, 2 * RADIUS, parent)
        self.node, self.name, self.is_input = node, name, is_input
        self.setBrush(QBrush(QColor(theme.TEXT if is_input else kind_color(parent.node.kind))))
        self.setPen(QPen(QColor(theme.AXES), 1))
        self.setAcceptHoverEvents(True)
        self.setCursor(Qt.CursorShape.CrossCursor)

    def scene_point(self):
        return self.mapToScene(QPointF(0, 0))


class NodeItem(QGraphicsItem):
    """A node: its title bar, its lines, its sockets."""

    def __init__(self, node, status=""):
        super().__init__()
        self.node = node
        self.status = status
        self.lines = [line for line in (node.name if node.name and node.name != node.id
                                        else "", node.detail, status) if line]
        self.setFlags(QGraphicsItem.GraphicsItemFlag.ItemIsMovable
                      | QGraphicsItem.GraphicsItemFlag.ItemIsSelectable
                      | QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges)
        self.height = HEADER + LINE * (len(self.lines) + len(node.inputs)) + 6
        self.inputs = {}
        top = HEADER + LINE * len(self.lines)
        for i, socket in enumerate(node.inputs):
            item = SocketItem(node.id, socket.name, True, self)
            item.setPos(0, top + LINE * i + LINE / 2)
            item.setToolTip(f"{socket.label}: takes a {' or '.join(socket.accepts)}"
                            + ("" if socket.required else "; optional, the right click cuts it"))
            self.inputs[socket.name] = item
        self.output = SocketItem(node.id, node.output, False, self)
        self.output.setPos(WIDTH, HEADER / 2)
        self.output.setToolTip(f"its {node.output}: drag it onto an input that takes one")
        self.setToolTip(f"{node.id} {node.title}" + (f" · {node.name}" if node.name else ""))

    def boundingRect(self):
        return QRectF(-RADIUS - 1, -1, WIDTH + 2 * RADIUS + 2, self.height + 2)

    def paint(self, painter, option, widget=None):
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        body = QRectF(0, 0, WIDTH, self.height)
        selected = self.isSelected()
        painter.setPen(QPen(QColor(theme.SELECTED if selected else theme.MUTED),
                            2 if selected else 1))
        painter.setBrush(QBrush(QColor(theme.FIGURE)))
        painter.drawRoundedRect(body, 6, 6)
        header = QPainterPath()
        header.addRoundedRect(QRectF(0, 0, WIDTH, HEADER), 6, 6)
        painter.fillPath(header, QBrush(QColor(kind_color(self.node.kind))))
        font = QFont(painter.font())
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(QColor("#ffffff"))
        metrics = QFontMetricsF(font)
        title = metrics.elidedText(f"{self.node.id}  {self.node.title}",
                                   Qt.TextElideMode.ElideRight, WIDTH - 16)
        painter.drawText(QRectF(8, 0, WIDTH - 16, HEADER), Qt.AlignmentFlag.AlignVCenter, title)
        font.setBold(False)
        painter.setFont(font)
        metrics = QFontMetricsF(font)
        painter.setPen(QColor(theme.TEXT))
        y = HEADER
        for line in self.lines:
            painter.drawText(QRectF(8, y, WIDTH - 16, LINE), Qt.AlignmentFlag.AlignVCenter,
                             metrics.elidedText(line, Qt.TextElideMode.ElideRight, WIDTH - 16))
            y += LINE
        painter.setPen(QColor(theme.DOC))
        for socket in self.node.inputs:
            painter.drawText(QRectF(12, y, WIDTH - 20, LINE), Qt.AlignmentFlag.AlignVCenter,
                             metrics.elidedText(socket.label, Qt.TextElideMode.ElideRight,
                                                WIDTH - 20))
            y += LINE

    def itemChange(self, change, value):
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged and self.scene():
            for view in self.scene().views():
                if isinstance(view, NodeView):
                    view.update_links()
        return super().itemChange(change, value)


class LinkItem(QGraphicsPathItem):
    """A link: a curve from an output to an input, solid, dashed (a
    from_result Field) or dotted (a sweep)."""

    def __init__(self, link):
        super().__init__()
        self.link = link
        self.setZValue(-1)
        pen = QPen(QColor(theme.MUTED if link.style != "solid" else theme.TEXT), 1.6)
        pen.setStyle(STYLES[link.style])
        self.setPen(pen)
        what = {"solid": f"the {link.socket} of {link.target}",
                "dashed": f"a Field of {link.target} reads the result of {link.source}",
                "dotted": f"the sweep {link.source} moves or runs {link.target}"}[link.style]
        self.setToolTip(what)

    def route(self, start, end):
        path = QPainterPath(start)
        bend = max(40.0, abs(end.x() - start.x()) / 2)
        path.cubicTo(start + QPointF(bend, 0), end - QPointF(bend, 0), end)
        self.setPath(path)


class NodeView(QGraphicsView):
    selected = Signal(str)                       # a node clicked: its id
    activated = Signal(str)                      # a node double clicked
    connect_requested = Signal(str, str, str)    # output node, input node, input name
    cut_requested = Signal(str, str)             # node, input name
    moved = Signal(str, float, float)            # a node dragged to x, y
    add_requested = Signal(object)               # Shift+A: the cursor's global position
    delete_requested = Signal(str)               # Del on a node

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("nodeView")
        self.setScene(QGraphicsScene(self))
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setDragMode(QGraphicsView.DragMode.RubberBandDrag)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.node_items, self.link_items = {}, []
        self._drag = None            # (output socket, temporary link) while a link is drawn
        self._places = {}            # where each node was drawn, to report the moved ones
        self._quiet = False
        self.scene().selectionChanged.connect(self._selection_changed)
        self.setToolTip("the document as a graph: drag an output (right) onto an input "
                        "(left) to link them; Shift+A adds, Del removes, Home shows all")

    # ---- drawing
    def refresh(self, session, places=None, current=""):
        """Draw the Document of a Session: places, {node id: [x, y]} kept by
        hand (the rest in columns by kind); current, the node selected."""
        document = session.document
        nodes = graph_tools.nodes(document)
        where = graph_tools.layout(nodes, places)
        self._quiet = True
        try:
            self.scene().clear()
            self.setBackgroundBrush(QBrush(QColor(theme.AXES)))
            self.node_items, self.link_items = {}, []
            for node in nodes:
                status = ""
                if node.kind == "calculation":
                    try:
                        status = marks.mark(*marks.calculation_state(session, node.id))
                    except Exception:
                        status = ""
                item = NodeItem(node, status)
                item.setPos(*where[node.id])
                self.scene().addItem(item)
                self.node_items[node.id] = item
            for link in graph_tools.links(document, nodes):
                item = LinkItem(link)
                self.scene().addItem(item)
                self.link_items.append(item)
            self.update_links()
            self._places = {n: (i.pos().x(), i.pos().y()) for n, i in self.node_items.items()}
            if current in self.node_items:
                self.node_items[current].setSelected(True)
        finally:
            self._quiet = False
        self.setSceneRect(self.scene().itemsBoundingRect().adjusted(-60, -60, 60, 60))

    def update_links(self):
        for item in self.link_items:
            link = item.link
            source, target = self.node_items.get(link.source), self.node_items.get(link.target)
            if source is None or target is None:
                continue
            start = source.output.scene_point()
            socket = target.inputs.get(link.socket)
            end = socket.scene_point() if socket is not None else \
                target.mapToScene(QPointF(0, HEADER / 2))
            item.route(start, end)

    def frame_all(self):
        self.fitInView(self.scene().itemsBoundingRect().adjusted(-20, -20, 20, 20),
                       Qt.AspectRatioMode.KeepAspectRatio)

    def select_node(self, node_id):
        """Select a node without emitting selected (the window drives this)."""
        self._quiet = True
        try:
            self.scene().clearSelection()
            if node_id in self.node_items:
                self.node_items[node_id].setSelected(True)
        finally:
            self._quiet = False

    def socket_point(self, node_id, socket=None):
        """The view's pixel of a node's input (or of its output, socket None),
        for tests and drivers."""
        item = self.node_items[node_id]
        target = item.output if socket is None else item.inputs[socket]
        return self.mapFromScene(target.scene_point())

    # ---- interaction
    def _selection_changed(self):
        if self._quiet:
            return
        chosen = [n for n, item in self.node_items.items() if item.isSelected()]
        if len(chosen) == 1:
            self.selected.emit(chosen[0])

    def _socket_at(self, point):
        for item in self.items_at(point):
            if isinstance(item, SocketItem):
                return item
        return None

    def items_at(self, point):
        return super().items(point)

    def mousePressEvent(self, event):
        socket = self._socket_at(event.position().toPoint())
        if event.button() == Qt.MouseButton.LeftButton and socket is not None \
                and not socket.is_input:
            link = QGraphicsPathItem()
            link.setPen(QPen(QColor(theme.SELECTED), 2))
            self.scene().addItem(link)
            self._drag = (socket, link)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._drag is not None:
            socket, link = self._drag
            path = QPainterPath(socket.scene_point())
            path.lineTo(self.mapToScene(event.position().toPoint()))
            link.setPath(path)
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self._drag is not None:
            socket, link = self._drag
            self._drag = None
            self.scene().removeItem(link)
            target = self._socket_at(event.position().toPoint())
            if target is not None and target.is_input:
                self.connect_requested.emit(socket.node, target.node, target.name)
            return
        super().mouseReleaseEvent(event)
        for node, item in self.node_items.items():
            place = (item.pos().x(), item.pos().y())
            if place != self._places.get(node):
                self._places[node] = place
                self.moved.emit(node, *place)

    def mouseDoubleClickEvent(self, event):
        for item in self.items_at(event.position().toPoint()):
            if isinstance(item, NodeItem):
                self.activated.emit(item.node.id)
                return
        super().mouseDoubleClickEvent(event)

    def contextMenuEvent(self, event):
        socket = self._socket_at(event.pos())
        if socket is None or not socket.is_input:
            return super().contextMenuEvent(event)
        node = self.node_items[socket.node].node
        entry = next(s for s in node.inputs if s.name == socket.name)
        menu = QMenu(self)
        menu.setObjectName("nodeSocketMenu")
        cut = menu.addAction("Cut the link (the default)",
                             lambda: self.cut_requested.emit(socket.node, socket.name))
        cut.setEnabled(not entry.required and entry.source is not None)
        if entry.required:
            cut.setToolTip("never empty: link another one to it instead")
        menu.popup(event.globalPos())

    def keyPressEvent(self, event):
        key, modifiers = event.key(), event.modifiers()
        if key == Qt.Key.Key_A and modifiers & Qt.KeyboardModifier.ShiftModifier:
            self.add_requested.emit(QCursor.pos())
        elif key in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
            chosen = [n for n, item in self.node_items.items() if item.isSelected()]
            for node in chosen:
                self.delete_requested.emit(node)
        elif key == Qt.Key.Key_Home:
            self.frame_all()
        else:
            super().keyPressEvent(event)

    def wheelEvent(self, event):
        factor = 1.15 if event.angleDelta().y() > 0 else 1 / 1.15
        self.scale(factor, factor)


class OutlinerPanel(QWidget):
    """The Outliner dock's content: Tree or Nodes at its top
    (outlinerViewTabs), the tree and the node view in a stack
    (outlinerStack); with the nodes, Arrange (nodeArrange) puts them back in
    their columns."""

    view_chosen = Signal(str)            # "tree" or "nodes"
    arrange_requested = Signal()

    def __init__(self, tree, nodes, parent=None):
        super().__init__(parent)
        self.setObjectName("outlinerPanel")
        self.tree, self.nodes = tree, nodes
        self.tabs = QTabBar()
        self.tabs.setObjectName("outlinerViewTabs")
        self.tabs.addTab("Tree")
        self.tabs.addTab("Nodes")
        self.tabs.setTabToolTip(0, "the document as a tree: each system with what it owns")
        self.tabs.setTabToolTip(1, "the document as a graph: geometries, k-paths, systems, "
                                   "embeddings and calculations, linked by what they name")
        self.tabs.setDrawBase(False)
        self.tabs.currentChanged.connect(
            lambda i: self.view_chosen.emit("nodes" if i == 1 else "tree"))
        self.arrange = QToolButton()
        self.arrange.setText("Arrange")
        self.arrange.setObjectName("nodeArrange")
        self.arrange.setToolTip("put every node back in the column of its kind, in document "
                                "order (the places moved by hand are forgotten)")
        self.arrange.clicked.connect(self.arrange_requested.emit)
        top = QHBoxLayout()
        top.setContentsMargins(4, 2, 4, 2)
        top.addWidget(self.tabs)
        top.addStretch(1)
        top.addWidget(self.arrange)
        self.stack = QStackedWidget()
        self.stack.setObjectName("outlinerStack")
        self.stack.addWidget(tree)
        self.stack.addWidget(nodes)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addLayout(top)
        layout.addWidget(self.stack, 1)
        self.show_view("tree")

    def show_view(self, name):
        nodes = name == "nodes"
        self.tabs.blockSignals(True)
        self.tabs.setCurrentIndex(1 if nodes else 0)
        self.tabs.blockSignals(False)
        self.stack.setCurrentWidget(self.nodes if nodes else self.tree)
        self.arrange.setVisible(nodes)

    def view(self):
        return "nodes" if self.stack.currentWidget() is self.nodes else "tree"
