"""The 3D drawing with pyvista (View > 3D drawing, the optional [3d] extra):
what the structure canvas and the result views draw in 3D, a geometry and
the values or vectors on its sites, drawn by pyvista instead of
matplotlib's mplot3d, and moved in space as Blender's viewport is: the
middle button orbits (a turntable, so z stays up), shift and the middle
button pan, ctrl and the middle button zoom, the wheel zooms, ctrl and
shift with the wheel pan, alt and the left button stand for the middle one,
and the numpad gives the front, right and top views (ctrl for the opposite
side), steps the orbit by 15 degrees (ctrl: pans), toggles the
perspective and orthographic projections and zooms. The arithmetic of the
camera is ui/navigation.py's `Turntable`.

pyvista renders off-screen (its own OpenGL context: X, EGL or OSMesa,
whichever VTK finds) and the widget paints the image; the mouse and the keys
of the widget move the camera directly, and nothing goes through a VTK
interactor: a VTK widget embedded in Qt (pyvistaqt's QtInteractor, VTK's
QVTKRenderWindowInteractor) crashes on the offscreen platform of the tests,
tools/drive.py and the remote screenshots, and in its default form draws
into an X window, which Qt on a Wayland desktop does not have; an image
works on both. SceneCanvas.send() takes the events by name, so tests and
drivers turn the view without a mouse.

pyvista is imported at the first drawing, never when this module is (the
window starts without it, tests/ui/test_startup.py); available() only
looks for it. A drawing that fails (pyvista missing, no OpenGL at all)
raises, and the canvas draws with mplot3d instead and says why.
"""
import importlib.util

import numpy as np
from PySide6.QtCore import QEvent, QRectF, Qt, Signal
from PySide6.QtGui import QAction, QImage, QPainter
from PySide6.QtWidgets import (QFileDialog, QHBoxLayout, QLabel, QMenu, QSizePolicy,
                               QToolButton, QVBoxLayout, QWidget)

from guiqula.ui import navigation
from guiqula.ui import structure as structure_tools
from guiqula.ui import theme

RENDERERS = ("matplotlib", "pyvista")
GLYPH_LIMIT = 4000        # above this many sites they are drawn as points, not spheres
HINT = "middle drag: orbit · shift+middle: pan · ctrl+middle: zoom · wheel: zoom · numpad: views"
VIEW_TIP = ("the views of the numpad, the projection and framing (the view shown is "
            "Blender's name for it)")
HELP = ("as in Blender: the middle button (or alt and the left button) orbits, with shift it "
        "pans and with ctrl it zooms; the wheel zooms, ctrl+wheel and shift+wheel pan; numpad "
        "1, 3 and 7 give the front, right and top views (ctrl: the opposite side), 4, 6, 8 and "
        "2 orbit by 15 degrees (ctrl: pan), 5 toggles perspective and orthographic, 9 turns "
        "half way round, + and - zoom, . frames the selected sites and Home everything")
BUTTONS = {Qt.MouseButton.LeftButton: "LeftButton", Qt.MouseButton.RightButton: "RightButton",
           Qt.MouseButton.MiddleButton: "MiddleButton"}
# the numpad: its keys as Qt reports them with the keypad modifier, and (NumLock off) the
# navigation keys they are then
KEYPAD_DIGITS = {getattr(Qt.Key, f"Key_{d}"): d for d in range(10)}
KEYPAD_DIGITS.update({Qt.Key.Key_End: 1, Qt.Key.Key_Down: 2, Qt.Key.Key_PageDown: 3,
                      Qt.Key.Key_Left: 4, Qt.Key.Key_Clear: 5, Qt.Key.Key_Right: 6,
                      Qt.Key.Key_Home: 7, Qt.Key.Key_Up: 8, Qt.Key.Key_PageUp: 9,
                      Qt.Key.Key_Insert: 0})
NUMPAD_AXIS = {1: "front", 3: "right", 7: "top"}
NUMPAD_STEP = {4: "left", 6: "right", 8: "up", 2: "down"}
VIEW_NAMES = (*navigation.AXIS_VIEWS, "perspective", "orthographic", "flip", "all", "selected",
              "reset")          # what SceneView.set_view takes
_failure = None           # why pyvista could not draw, once it could not


def available():
    """Whether pyvista can draw: installed, and no drawing failed so far."""
    return _failure is None and importlib.util.find_spec("pyvista") is not None


def unavailable_reason():
    """Why pyvista cannot draw, or "" when it can."""
    if _failure is not None:
        return _failure
    if importlib.util.find_spec("pyvista") is None:
        return "pyvista is not installed (pip install pyvista, the [3d] extra)"
    return ""


# ---- the scene (pyvista, imported by the caller)
def _rgb(colors):
    from matplotlib import colors as mcolors
    return (np.array([mcolors.to_rgb(c) for c in colors]).reshape(-1, 3) * 255).astype(np.uint8)


def _sphere(pv, radius):
    return pv.Sphere(radius=radius, theta_resolution=18, phi_resolution=12)


def _spheres(pv, points, radius):
    return pv.PolyData(points).glyph(geom=_sphere(pv, radius), scale=False, orient=False)


def _lines(pv, segments):
    return pv.line_segments_from_points(np.asarray(segments, dtype=float).reshape(-1, 3))


def _sites(plotter, pv, r, name, radius, arrays=None, **style):
    """Spheres at the positions r (points drawn as spheres above
    GLYPH_LIMIT), with point arrays for scalars; style goes to add_mesh."""
    cloud = pv.PolyData(r)
    for key, values in (arrays or {}).items():
        cloud[key] = values
    if len(r) > GLYPH_LIMIT:
        return plotter.add_mesh(cloud, name=name, render_points_as_spheres=True, point_size=6,
                                **style)
    mesh = cloud.glyph(geom=_sphere(pv, radius), scale=False, orient=False)
    return plotter.add_mesh(mesh, name=name, smooth_shading=True, specular=0.4,
                            specular_power=20, **style)


def draw_scene(plotter, build, highlight=None, selected=None, removed=None, images=True,
               site_values=None, arrows=None, hoppings=None, title="", pixel_ratio=1.0):
    """draw_structure_3d (ui/structure.py) with pyvista, overlay for overlay:
    the sites coloured by sublattice (or by site_values, with a colour bar
    when they vary), the bonds (or the hoppings of the Hamiltonian view,
    coloured by their phase and wider for a larger amplitude), the
    neighbouring cells faded, the unit cell, the arrows of a vector per
    site, the region highlighted, the removed positions and the selected
    sites (set_selection redraws only those). Returns the bounds the camera
    fits (xmin, xmax, ymin, ymax, zmin, zmax): the sites and the unit cell,
    as mplot3d's limits, not the faded cells around them. The title and
    the colour bar's text take the plot text size (ui/theme.py), as
    matplotlib draws it at 100 dpi, times the screen's pixel ratio."""
    import pyvista as pv
    plotter.clear()
    plotter.set_background(theme.AXES)
    r = np.asarray(build["positions"], dtype=float).reshape(-1, 3)
    n = len(r)
    # smaller atoms under arrows, which are centred on them and would be hidden
    radius = structure_tools.RADIUS * (0.6 if arrows is not None else 1.0)
    lattice = np.asarray(build["lattice"], dtype=float).reshape(-1, 3)
    def pixels(relative):
        return theme.font_points(relative) * pixel_ratio * 100 / 72
    bar = {"color": theme.TEXT, "title_font_size": round(pixels("large")),
           "label_font_size": round(pixels("medium")), "vertical": True, "position_x": 0.86,
           "position_y": 0.15, "height": 0.7, "width": 0.06, "fmt": "%.3g"}
    if hoppings is not None:
        rows = np.asarray(hoppings["hoppings"]).reshape(-1, 5)
        shift = rows[:, 2:5] @ lattice if len(rows) else np.zeros((0, 3))
        amplitude = np.asarray(hoppings["amplitude"], dtype=float)
        phase = np.asarray(hoppings["phase"], dtype=float)
        top = float(amplitude.max()) if len(amplitude) else 1.0
        widths = np.round(1 + 5 * amplitude / (top if top > 0 else 1.0))
        for k, width in enumerate(np.unique(widths)):      # VTK draws one width per actor
            chosen = widths == width
            ij = rows[chosen, :2].astype(int)
            lines = _lines(pv, np.stack([r[ij[:, 0]], r[ij[:, 1]] + shift[chosen]], axis=1))
            lines.cell_data["phase"] = phase[chosen]
            plotter.add_mesh(lines, name=f"hoppings{k}", scalars="phase",
                             cmap=structure_tools.PHASE_MAP, clim=(-np.pi, np.pi),
                             line_width=float(width), show_scalar_bar=False)
    else:
        segments = structure_tools.bond_segments_3d(build)
        if len(segments):
            plotter.add_mesh(_lines(pv, segments), name="bonds", color=theme.BOND,
                             line_width=2.0)
    if images and 0 < n <= structure_tools.IMAGE_LIMIT // 4 and int(build["dimensionality"]):
        ghosts = np.concatenate([r + c @ lattice
                                 for c in structure_tools.image_cells(build["dimensionality"])])
        plotter.add_mesh(pv.PolyData(ghosts), name="images", color=theme.MUTED, opacity=0.25,
                         render_points_as_spheres=True, point_size=6)
    if n:
        if site_values is not None:
            values = np.asarray(site_values["values"], dtype=float).ravel()
            symmetric = site_values.get("symmetric", True)
            cmap = structure_tools.VALUE_MAP if symmetric else structure_tools.SEQUENTIAL_MAP
            _, mappable = structure_tools.value_colors(values, symmetric=symmetric, cmap=cmap)
            _sites(plotter, pv, r, "sites", radius, {"values": values}, scalars="values",
                   cmap=cmap, clim=(mappable.norm.vmin, mappable.norm.vmax),
                   nan_color=theme.MUTED, show_scalar_bar=structure_tools.varies(values),
                   scalar_bar_args=dict(bar, title=site_values.get("label", "") or " "))
        else:
            _sites(plotter, pv, r, "sites", radius,
                   {"rgb": _rgb(structure_tools.site_colors(build))}, scalars="rgb", rgb=True,
                   show_scalar_bar=False)
    edges = structure_tools.cell_edges_3d(build)
    if len(edges):
        plotter.add_mesh(_lines(pv, edges), name="cell", color=theme.CELL, line_width=1.0,
                         opacity=0.8)
    if arrows is not None:
        vectors = np.asarray(arrows["vectors"], dtype=float).reshape(-1, 3)
        shown = structure_tools.finite_vectors(vectors)
        lengths = np.linalg.norm(vectors[shown], axis=1)
        longest = float(lengths.max()) if len(lengths) else 0.0
        if longest > 1e-12:
            v = vectors[shown] * (0.9 / longest)
            tails = pv.PolyData(r[shown] - v / 2)
            tails["v"] = v
            glyphs = tails.glyph(orient="v", scale="v", factor=1.0,
                                 geom=pv.Arrow(tip_length=0.3, tip_radius=0.12,
                                               shaft_radius=0.045))
            plotter.add_mesh(glyphs, name="arrows", color=theme.ARROW, smooth_shading=True)
    if highlight is not None and np.any(highlight):
        plotter.add_mesh(_spheres(pv, r[np.asarray(highlight, dtype=bool)], radius * 1.6),
                         name="highlight", color=theme.REGION, opacity=0.35)
    if removed is not None and len(removed):
        plotter.add_mesh(pv.PolyData(np.asarray(removed, dtype=float).reshape(-1, 3)),
                         name="removed", color=theme.REMOVED, render_points_as_spheres=True,
                         point_size=10)
    set_selection(plotter, r[np.asarray(selected if selected is not None else [], dtype=int)])
    if title:               # a fixed size, centred at the top (a corner annotation scales)
        text = plotter.add_text(title, position=(0.5, 0.985), viewport=True,
                                font_size=pixels("medium") / 2, color=theme.TEXT, name="title")
        text.prop.justification_horizontal = "center"
        text.prop.justification_vertical = "top"
    plotter.add_axes(color=theme.TEXT, labels_off=False)
    points = np.concatenate([r, edges.reshape(-1, 3)]) if len(edges) else r
    if not len(points):
        return None
    low, high = points.min(axis=0), points.max(axis=0)
    middle, span = (low + high) / 2, np.maximum(high - low, 1.0)
    return tuple(float(x) for m, w in zip(middle, span) for x in (m - 0.55 * w, m + 0.55 * w))


def set_selection(plotter, points):
    """Draw the selected sites (positions (K, 3)) instead of those drawn."""
    import pyvista as pv
    points = np.asarray(points, dtype=float).reshape(-1, 3)
    if len(points):
        plotter.add_mesh(_spheres(pv, points, structure_tools.RADIUS * 1.5), name="selection",
                         color=theme.SELECTED, opacity=0.55)
    else:
        plotter.remove_actor("selection")


# ---- the widgets
class SceneCanvas(QWidget):
    """Paints what an off-screen pyvista Plotter renders and moves its
    camera with the mouse and the keys as Blender's viewport does (`view`,
    a navigation.Turntable). The plotter (and pyvista) is made at the
    first drawing."""

    view_changed = Signal()             # the camera moved
    frame_requested = Signal(str)       # "all" or "selected": the scene knows the bounds

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(160, 120)
        self.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent)
        self.plotter = self.interactor = None
        self.image = None                 # QImage of the last rendering
        self.view = navigation.Turntable()
        self.gesture = None               # the drag in progress (orbit, pan or zoom)
        self._rendered = False            # a rendering since the image was read
        self._stale = True                # the scene changed: render before painting
        self._filter = None

    def ensure(self):
        """The plotter, made (with its interactor) the first time."""
        global _failure
        if self.plotter is not None:
            return self.plotter
        if _failure is not None:              # not tried again at every drawing
            raise RuntimeError(_failure)
        try:
            import pyvista
            from vtkmodules.vtkRenderingCore import vtkWindowToImageFilter
            from vtkmodules.vtkRenderingUI import vtkGenericRenderWindowInteractor
            plotter = pyvista.Plotter(off_screen=True, window_size=self._pixels())
            interactor = vtkGenericRenderWindowInteractor()
            interactor.SetRenderWindow(plotter.render_window)
            interactor.Initialize()
            plotter.render_window.AddObserver("EndEvent", self._on_render)
            self._filter = vtkWindowToImageFilter()
            self._filter.SetInput(plotter.render_window)
            self._filter.SetInputBufferTypeToRGB()
            self._filter.ReadFrontBufferOff()
            self._filter.ShouldRerenderOff()
        except Exception as error:
            _failure = f"pyvista could not start: {type(error).__name__}: {error}"
            raise
        self.plotter, self.interactor = plotter, interactor
        # the render window's OpenGL context goes with the widget
        self.destroyed.connect(lambda *_, p=plotter: p.close())
        return plotter

    def _pixels(self):
        ratio = self.devicePixelRatioF()
        return (max(int(self.width() * ratio), 16), max(int(self.height() * ratio), 16))

    def _on_render(self, *_):
        self._rendered = True

    def render(self):
        """Render now and keep the image (the scene changed)."""
        if self.plotter is None:
            return
        self.plotter.render_window.Render()     # plotter.render() waits for a show()
        self._read()
        self.update()

    def changed(self):
        """The scene changed: it is rendered at the next paint."""
        self._stale = True
        self.update()

    def _read(self):
        self._rendered, self._stale = False, False
        self._filter.Modified()
        self._filter.Update()
        output = self._filter.GetOutput()
        width, height, _ = output.GetDimensions()
        from vtkmodules.util.numpy_support import vtk_to_numpy
        pixels = vtk_to_numpy(output.GetPointData().GetScalars()).reshape(height, width, -1)
        pixels = np.ascontiguousarray(pixels[::-1, :, :3])
        self.image = QImage(pixels.data, width, height, 3 * width,
                            QImage.Format.Format_RGB888).copy()
        self.image.setDevicePixelRatio(self.devicePixelRatioF())

    def pixels(self):
        """The last rendering as an (height, width, 3) array (tests)."""
        if self.plotter is not None and self._stale:
            self.render()
        if self.image is None:
            return np.zeros((0, 0, 3), dtype=np.uint8)
        image = self.image.convertToFormat(QImage.Format.Format_RGB888)
        width, height = image.width(), image.height()
        data = np.frombuffer(image.constBits(), dtype=np.uint8,
                             count=image.bytesPerLine() * height)
        return data.reshape(height, image.bytesPerLine())[:, :3 * width].reshape(height,
                                                                              width, 3).copy()

    def paintEvent(self, event):
        painter = QPainter(self)
        if self.plotter is not None and self._stale:
            self.plotter.render_window.Render()
            self._read()
        if self.image is None:
            painter.fillRect(self.rect(), self.palette().window())
        else:
            painter.drawImage(QRectF(self.rect()), self.image)
        painter.end()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.interactor is not None:
            self.interactor.UpdateSize(*self._pixels())
            self.changed()

    def aspect(self):
        return self.width() / max(self.height(), 1)

    # ---- the camera
    def apply_view(self):
        """The camera goes where the view says (after any change of it)."""
        if self.plotter is None:
            return
        self.view.apply(self.plotter.camera)
        self.plotter.renderer.reset_camera_clipping_range()
        self.changed()
        self.view_changed.emit()

    def orbit_step(self, direction):
        self.view.orbit_step(direction)
        self.apply_view()

    def pan_step(self, direction):
        self.view.pan_step(direction, self.height())
        self.apply_view()

    def zoom(self, notches):
        self.view.zoom(notches)
        self.apply_view()

    def axis_view(self, name, opposite=False):
        name = self.view.axis_view(name, opposite)
        self.apply_view()
        return name

    def flip(self):
        self.view.flip()
        self.apply_view()

    def toggle_projection(self):
        self.view.toggle_projection()
        self.apply_view()

    # ---- the mouse, as Blender's: the middle button (or alt and the left one) moves the
    # view, shift pans and ctrl zooms; the wheel zooms, with ctrl or shift it pans
    @staticmethod
    def gesture_of(button, ctrl=False, shift=False, alt=False):
        """"orbit", "pan" or "zoom" for a button pressed with modifiers, or
        None when the button does not move the view."""
        if button == "MiddleButton" or (button == "LeftButton" and alt):
            return "pan" if shift else "zoom" if ctrl else "orbit"
        return None

    def send(self, event, x=0.0, y=0.0, ctrl=False, shift=False, alt=False):
        """Give the scene a mouse event by name (LeftButtonPress,
        MiddleButtonPress, MouseMove, MiddleButtonRelease, MouseWheelForward,
        MouseWheelBackward, ...) at a position in widget pixels (origin top
        left); the view follows. Returns whether the view moved."""
        if self.plotter is None:
            return False
        if event == "MouseMove":
            return self._move(x, y)
        if event in ("MouseWheelForward", "MouseWheelBackward"):
            return self._wheel(1.0 if event.endswith("Forward") else -1.0, ctrl, shift)
        for suffix, handler in (("Press", self._press), ("Release", self._release)):
            button = event[:-len(suffix)]
            if event.endswith(suffix) and button in BUTTONS.values():
                return handler(button, x, y, ctrl, shift, alt)
        raise ValueError(f"unknown mouse event {event!r}")

    def drag(self, start, end, steps=10, button="MiddleButton", ctrl=False, shift=False,
             alt=False):
        """A drag from start to end (widget pixels) with a button (tests,
        drivers)."""
        (x0, y0), (x1, y1) = start, end
        self.send(f"{button}Press", x0, y0, ctrl, shift, alt)
        for t in np.linspace(0, 1, max(int(steps), 1) + 1)[1:]:
            self.send("MouseMove", x0 + t * (x1 - x0), y0 + t * (y1 - y0), ctrl, shift, alt)
        self.send(f"{button}Release", x1, y1, ctrl, shift, alt)

    def _press(self, button, x, y, ctrl, shift, alt):
        kind = self.gesture_of(button, ctrl, shift, alt)
        self.gesture = None if kind is None else {
            "kind": kind, "button": button, "x": x, "y": y, "y0": y,
            "distance": self.view.distance}
        return False

    def _move(self, x, y):
        gesture = self.gesture
        if gesture is None:
            return False
        dx, dy = x - gesture["x"], y - gesture["y"]
        gesture["x"], gesture["y"] = x, y
        if gesture["kind"] == "orbit":
            self.view.orbit(dx, dy)
        elif gesture["kind"] == "pan":
            self.view.pan(dx, dy, self.height())
        else:
            self.view.zoom_drag(gesture["distance"], gesture["y0"], y)
        self.apply_view()
        return True

    def _release(self, button, x, y, ctrl, shift, alt):
        if self.gesture is not None and self.gesture["button"] == button:
            self.gesture = None
        return False

    def _wheel(self, notches, ctrl=False, shift=False):
        """The wheel zooms; with ctrl the view moves sideways, with shift up
        and down (a notch forward moves it right and up)."""
        if ctrl:
            self.view.pan(-notches * navigation.PAN_STEP, 0.0, self.height())
        elif shift:
            self.view.pan(0.0, notches * navigation.PAN_STEP, self.height())
        else:
            self.view.zoom(notches)
        self.apply_view()
        return True

    @staticmethod
    def _modifiers(event):
        modifiers = event.modifiers()
        return (bool(modifiers & Qt.KeyboardModifier.ControlModifier),
                bool(modifiers & Qt.KeyboardModifier.ShiftModifier),
                bool(modifiers & Qt.KeyboardModifier.AltModifier))

    def _mouse(self, event, suffix):
        button = BUTTONS.get(event.button())
        if button is None:
            return
        point = event.position()
        self.send(f"{button}{suffix}", point.x(), point.y(), *self._modifiers(event))

    def mousePressEvent(self, event):
        self._mouse(event, "Press")

    def mouseDoubleClickEvent(self, event):
        self._mouse(event, "Press")

    def mouseReleaseEvent(self, event):
        self._mouse(event, "Release")

    def mouseMoveEvent(self, event):
        point = event.position()
        self.send("MouseMove", point.x(), point.y(), *self._modifiers(event))

    def wheelEvent(self, event):
        ctrl, shift, _ = self._modifiers(event)
        delta = event.angleDelta()
        vertical, sideways = delta.y() / 120.0, delta.x() / 120.0
        if not vertical and sideways and shift:    # some platforms turn shift+wheel sideways
            vertical, sideways = sideways, 0.0
        if self.plotter is not None:
            if vertical:
                self._wheel(vertical, ctrl, shift)
            elif sideways:
                self.view.pan(sideways * navigation.PAN_STEP, 0.0, self.height())
                self.apply_view()
        event.accept()

    # ---- the keys, as Blender's numpad (the window's own keys, + - 3 4 and Home, are
    # bound to the canvas by the window)
    def _command(self, event):
        """What a key press does in the scene, as a function, or None."""
        key, modifiers = event.key(), event.modifiers()
        ctrl = bool(modifiers & Qt.KeyboardModifier.ControlModifier)
        if modifiers & Qt.KeyboardModifier.KeypadModifier:
            digit = KEYPAD_DIGITS.get(key)
            if digit in NUMPAD_AXIS:
                return lambda: self.axis_view(NUMPAD_AXIS[digit], opposite=ctrl)
            if digit in NUMPAD_STEP:
                step = NUMPAD_STEP[digit]
                return (lambda: self.pan_step(step)) if ctrl else (
                    lambda: self.orbit_step(step))
            if digit == 5:
                return self.toggle_projection
            if digit == 9:
                return self.flip
            if key in (Qt.Key.Key_Plus, Qt.Key.Key_Minus):
                return lambda: self.zoom(1.0 if key == Qt.Key.Key_Plus else -1.0)
            if key in (Qt.Key.Key_Period, Qt.Key.Key_Delete):
                return lambda: self.frame_requested.emit("selected")
        elif ctrl and key in (Qt.Key.Key_Equal, Qt.Key.Key_Plus, Qt.Key.Key_Minus):
            return lambda: self.zoom(-1.0 if key == Qt.Key.Key_Minus else 1.0)
        return None

    def event(self, event):
        # the numpad must not fire the shortcuts of the digits (3 and 4 on the canvas)
        if event.type() == QEvent.Type.ShortcutOverride and self.plotter is not None \
                and self._command(event) is not None:
            event.accept()
            return True
        return super().event(event)

    def keyPressEvent(self, event):
        command = self._command(event) if self.plotter is not None else None
        if command is not None:
            command()
            event.accept()
        elif event.key() == Qt.Key.Key_Home and self.plotter is not None:
            self.frame_requested.emit("all")
            event.accept()
        else:
            super().keyPressEvent(event)


class _Hint(QLabel):
    """A line of text that ends in an ellipsis when it does not fit."""

    def __init__(self, text):
        super().__init__(text)
        self.full = text
        self.setMinimumWidth(0)
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)

    def set_full(self, text):
        self.full = text
        self._elide()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._elide()

    def _elide(self):
        self.setText(self.fontMetrics().elidedText(self.full, Qt.TextElideMode.ElideRight,
                                                   self.width()))


class SceneView(QWidget):
    """The pyvista canvas with its bar: Reset view (the first viewing
    angle, everything in sight), the View menu (Blender's numpad views, the
    projection, framing), Save image, and what the mouse does. The structure
    canvas and a result view take the first three into their own bar
    (ui/canvasbar.py, CanvasBar.adopt_scene), and the scene's bar keeps the
    line saying what the mouse does."""

    def __init__(self, name, parent=None):
        super().__init__(parent)
        self.setObjectName(name)
        self.canvas = SceneCanvas()
        self.canvas.setObjectName(f"{name}Canvas")
        self.canvas.view_changed.connect(self._show_view)
        self.canvas.frame_requested.connect(lambda which: self.set_view(which))
        self.reset = QToolButton()
        self.reset.setText("Reset view")
        self.reset.setObjectName(f"{name}Reset")
        self.reset.setToolTip("the first viewing angle, with everything in sight")
        self.reset.clicked.connect(self.reset_view)
        self.view_button = QToolButton()
        self.view_button.setObjectName(f"{name}View")
        self.view_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.view_button.setToolTip(VIEW_TIP)
        self.view_menu = QMenu(self.view_button)
        self.view_menu.setObjectName(f"{name}ViewMenu")
        self.view_actions = {}
        for key, text, hint in (
                ("front", "Front", "Num+1"), ("back", "Back", "Ctrl+Num+1"),
                ("right", "Right", "Num+3"), ("left", "Left", "Ctrl+Num+3"),
                ("top", "Top", "Num+7"), ("bottom", "Bottom", "Ctrl+Num+7"),
                (None, None, None),
                ("orthographic", "Orthographic", "Num+5"),
                ("flip", "Opposite side", "Num+9"),
                (None, None, None),
                ("all", "Frame all", "Home"), ("selected", "Frame selected", "Num+.")):
            if key is None:
                self.view_menu.addSeparator()
                continue
            action = QAction(f"{text}\t{hint}", self.view_menu)
            action.setObjectName(f"{name}View_{key}")
            if key == "orthographic":
                action.setCheckable(True)
                action.triggered.connect(lambda checked=False: self.set_view(
                    "orthographic" if checked else "perspective"))
            else:
                action.triggered.connect(lambda checked=False, k=key: self.set_view(k))
            self.view_menu.addAction(action)
            self.view_actions[key] = action
        self.view_button.setMenu(self.view_menu)
        self.save = QToolButton()
        self.save.setText("Save image")
        self.save.setObjectName(f"{name}Save")
        self.save.setToolTip("save the view as it is drawn (PNG)")
        self.save.clicked.connect(self._save_dialog)
        self.hint = _Hint(HINT)
        self.hint.setObjectName(f"{name}Hint")
        self.hint.setEnabled(False)
        self.hint.setToolTip(HELP)
        bar = QHBoxLayout()
        bar.setContentsMargins(0, 0, 0, 0)
        bar.addWidget(self.reset)
        bar.addWidget(self.view_button)
        bar.addWidget(self.save)
        bar.addWidget(self.hint, 1)
        self.bar = QWidget()
        self.bar.setLayout(bar)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.bar)
        layout.addWidget(self.canvas, 1)
        self.drawn = False               # a drawing since forget(), whose camera can stay
        self.bounds = None               # what the camera fits (draw_scene)
        self.selection = np.zeros((0, 3))     # the selected sites, drawn and framed
        self._show_view()

    def _show_view(self):
        """The view's name, Blender's (User Perspective, Top Orthographic...):
        the View button's text, which its icon stands for in the bar, and
        its tooltip, and the start of the line over the scene, where
        Blender writes it in the corner of its viewport."""
        view = self.canvas.view
        text = f"View: {view.description()}"
        self.view_button.setText(text)
        self.view_button.setToolTip(f"{text}; {VIEW_TIP}")
        self.hint.set_full(f"{view.description()} · {HINT}")
        self.view_actions["orthographic"].setChecked(view.ortho)

    def show_scene(self, build, keep=False, fit=True, **overlays):
        """Draw a geometry with overlays (draw_scene). keep: the camera
        stays where the user left it (the same system drawn again), and
        with fit it takes everything in sight again from there (its sites
        changed); otherwise the view starts oblique, everything in sight."""
        plotter = self.canvas.ensure()
        kept = keep and self.drawn
        self.bounds = draw_scene(plotter, build, pixel_ratio=self.canvas.devicePixelRatioF(),
                                 **overlays)
        self.selection = np.asarray(build["positions"], dtype=float).reshape(-1, 3)[
            np.asarray(overlays.get("selected") if overlays.get("selected") is not None
                       else [], dtype=int)]
        self.drawn = True
        if not kept:
            self.reset_view()
        elif fit:
            self.frame_all()
        else:
            self.canvas.apply_view()

    def set_selection(self, points):
        self.selection = np.asarray(points, dtype=float).reshape(-1, 3)
        if self.canvas.plotter is not None:
            set_selection(self.canvas.plotter, points)
            self.canvas.changed()

    # ---- the view
    def set_view(self, name):
        """Move the view by name (the View menu, the keys, drivers): front,
        back, right, left, top or bottom; perspective or orthographic; flip
        (half a turn about the vertical axis); all or selected (frame them);
        reset (the first angle, everything in sight)."""
        if name not in VIEW_NAMES:
            raise ValueError(f"unknown view {name!r}; views: {list(VIEW_NAMES)}")
        if self.canvas.plotter is None:
            return name
        view = self.canvas.view
        if name in navigation.AXIS_VIEWS:
            self.canvas.axis_view(name)
        elif name in ("perspective", "orthographic"):
            if view.ortho != (name == "orthographic"):
                self.canvas.toggle_projection()
        elif name == "flip":
            self.canvas.flip()
        elif name == "all":
            self.frame_all()
        elif name == "selected":
            self.frame_selected()
        else:
            self.reset_view()
        return name

    def key_handlers(self):
        """{shortcut id: function} for the keys of the table's "2D canvas"
        context that move the 3D view too (the zoom keys and Ctrl and the
        arrows, which pan)."""
        canvas = self.canvas
        return {"zoom_in": lambda: canvas.zoom(1.0), "zoom_out": lambda: canvas.zoom(-1.0),
                "zoom_selection": self.frame_selected, "zoom_drawing": self.frame_all,
                "scroll_left": lambda: canvas.pan_step("left"),
                "scroll_right": lambda: canvas.pan_step("right"),
                "scroll_up": lambda: canvas.pan_step("up"),
                "scroll_down": lambda: canvas.pan_step("down")}

    def frame_all(self):
        """Everything in sight, from the same angle."""
        if self.canvas.plotter is not None:
            self.canvas.view.frame(self.bounds, self.canvas.aspect())
            self.canvas.apply_view()

    fit = frame_all

    def frame_selected(self):
        """The selected sites in sight from the same angle (all, when none
        is selected)."""
        if len(self.selection) == 0:
            return self.frame_all()
        if self.canvas.plotter is not None:
            low, high = self.selection.min(axis=0), self.selection.max(axis=0)
            self.canvas.view.frame((low[0], high[0], low[1], high[1], low[2], high[2]),
                                   self.canvas.aspect())
            self.canvas.apply_view()

    def reset_view(self):
        """The first viewing angle (oblique, perspective), everything in sight."""
        if self.canvas.plotter is not None:
            self.canvas.view = navigation.Turntable()
            self.frame_all()

    def forget(self):
        """Nothing is drawn: the next drawing starts a new camera."""
        self.drawn = False

    def save_image(self, path):
        self.canvas.pixels()                     # rendered if it had to be
        if self.canvas.image is None or not self.canvas.image.save(str(path)):
            raise ValueError(f"could not save the view to {path}")
        return str(path)

    def _save_dialog(self):
        path, _ = QFileDialog.getSaveFileName(self, "Save the view", "view.png", "PNG (*.png)")
        if path:
            self.save_image(path)
