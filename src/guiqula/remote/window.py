"""The window's part of remote control (PLAN.md 3.7): the hooks the API
asks of it (screenshots, the widget names, its state, whether a build is
about to be asked for, its log) and the server it polls from its timer.
"""
from PySide6.QtCore import QBuffer, QByteArray, QIODevice, Qt
from PySide6.QtWidgets import QWidget

from guiqula.remote.api import RemoteAPI
from guiqula.remote.server import INVALID_PARAMS, RemoteError, Server


def widget_tree(widget, depth=0):
    """Lines "name (Class)", indented by nesting, of the widgets that have
    an objectName (what a screenshot, and tools/drive.py's --widget, take)."""
    lines = []
    name = widget.objectName()
    if name and not name.startswith("qt_"):
        lines.append("  " * depth + f"{name} ({type(widget).__name__})")
        depth += 1
    for child in widget.findChildren(QWidget, options=Qt.FindChildOption.FindDirectChildrenOnly):
        lines.extend(widget_tree(child, depth))
    return lines


def png_of(widget):
    """(PNG bytes, [width, height]) of what a widget shows."""
    pixmap = widget.grab()
    data = QByteArray()
    buffer = QBuffer(data)
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    pixmap.save(buffer, "PNG")
    buffer.close()
    return bytes(data.data()), [pixmap.width(), pixmap.height()]


class WindowHooks:
    def __init__(self, window):
        self.window = window

    def screenshot(self, widget=None):
        target = self.window
        if widget:
            target = self.window.findChild(QWidget, widget)
            if target is None:
                raise RemoteError(INVALID_PARAMS, f"no widget named {widget!r}; the widgets "
                                                  f"method lists them")
        png, size = png_of(target)
        return png, target.objectName(), size

    def widget_names(self):
        return widget_tree(self.window)

    def state(self):
        window = self.window
        return {"selected": window.selected, "workspace": window.workspace,
                "canvas_view": window.canvas_view, "tab": window.current_tab(),
                "result_views": list(window.plots), "theme": window.theme_choice,
                "selected_sites": int(len(window.structure.selected())),
                "projection": window.structure.projection,
                "renderer_3d": window.structure.renderer_3d}

    def projection(self):
        return self.window.structure.projection

    def busy(self):
        return self.window.build_timer.isActive()

    def log(self, lines):
        return self.window.log.toPlainText().splitlines()[-lines:]


def start(window):
    """A server over the window's session, published in a connection file."""
    session = window.session
    server = Server(RemoteAPI(session, WindowHooks(window)))
    server.publish(window=True, document=str(session.path) if session.path else None)
    return server
