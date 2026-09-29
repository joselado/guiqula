"""The 3D drawing with pyvista (View > 3D drawing, the optional [3d] extra):
what the structure canvas and the result views draw in 3D, a geometry and
the values or vectors on its sites, drawn by pyvista instead of
matplotlib's mplot3d, turned and zoomed with the mouse as in a pyvista
window: drag to turn, shift+drag or the middle button to pan, the wheel or
the right button to zoom, ctrl+drag to spin about the line of sight.

pyvista renders off-screen (its own OpenGL context: X, EGL or OSMesa,
whichever VTK finds) and the widget paints the image; the mouse goes to a
VTK interactor with the trackball camera style, pyvista's default, so the
gestures are pyvista's own. A VTK widget embedded in Qt (pyvistaqt's
QtInteractor, VTK's QVTKRenderWindowInteractor) crashes on the offscreen
platform of the tests, tools/drive.py and the remote screenshots, and in its
default form draws into an X window, which Qt on a Wayland desktop does not
have; an image works on both. SceneCanvas.send() takes the events by VTK's
names, so tests and drivers turn the view without a mouse.

pyvista is imported at the first drawing, never when this module is (the
window starts without it, tests/ui/test_startup.py); available() only
looks for it. A drawing that fails (pyvista missing, no OpenGL at all)
raises, and the canvas draws with mplot3d instead and says why.
"""
import importlib.util

import numpy as np
from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QImage, QPainter
from PySide6.QtWidgets import (QFileDialog, QHBoxLayout, QLabel, QSizePolicy, QToolButton,
                               QVBoxLayout, QWidget)

from guiqula.ui import structure as structure_tools
from guiqula.ui import theme

RENDERERS = ("matplotlib", "pyvista")
GLYPH_LIMIT = 4000        # above this many sites they are drawn as points, not spheres
HINT = "drag: turn · shift+drag: pan · wheel: zoom"
HELP = ("drag to turn; shift+drag or the middle button to pan; the wheel or a drag with the "
        "right button to zoom; ctrl+drag to spin about the line of sight (pyvista's mouse)")
BUTTONS = {Qt.MouseButton.LeftButton: "LeftButton", Qt.MouseButton.RightButton: "RightButton",
           Qt.MouseButton.MiddleButton: "MiddleButton"}
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
               site_values=None, arrows=None, hoppings=None, title=""):
    """draw_structure_3d (ui/structure.py) with pyvista, overlay for overlay:
    the sites coloured by sublattice (or by site_values, with a colour bar
    when they vary), the bonds (or the hoppings of the Hamiltonian view,
    coloured by their phase and wider for a larger amplitude), the
    neighbouring cells faded, the unit cell, the arrows of a vector per
    site, the region highlighted, the removed positions and the selected
    sites (set_selection redraws only those). Returns the bounds the camera
    fits (xmin, xmax, ymin, ymax, zmin, zmax): the sites and the unit cell,
    as mplot3d's limits, not the faded cells around them."""
    import pyvista as pv
    plotter.clear()
    plotter.set_background(theme.AXES)
    r = np.asarray(build["positions"], dtype=float).reshape(-1, 3)
    n = len(r)
    # smaller atoms under arrows, which are centred on them and would be hidden
    radius = structure_tools.RADIUS * (0.6 if arrows is not None else 1.0)
    lattice = np.asarray(build["lattice"], dtype=float).reshape(-1, 3)
    bar = {"color": theme.TEXT, "title_font_size": 14, "label_font_size": 12,
           "vertical": True, "position_x": 0.86, "position_y": 0.15, "height": 0.7,
           "width": 0.06, "fmt": "%.3g"}
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
    if title:
        plotter.add_text(title, position="upper_edge", font_size=9, color=theme.TEXT,
                         name="title")
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
    """Paints what an off-screen pyvista Plotter renders and hands it the
    mouse. The plotter (and pyvista) is made at the first drawing."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(160, 120)
        self.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent)
        self.plotter = self.interactor = None
        self.image = None                 # QImage of the last rendering
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
            from vtkmodules.vtkInteractionStyle import vtkInteractorStyleTrackballCamera
            from vtkmodules.vtkRenderingCore import vtkWindowToImageFilter
            from vtkmodules.vtkRenderingUI import vtkGenericRenderWindowInteractor
            plotter = pyvista.Plotter(off_screen=True, window_size=self._pixels())
            interactor = vtkGenericRenderWindowInteractor()
            interactor.SetRenderWindow(plotter.render_window)
            interactor.SetInteractorStyle(vtkInteractorStyleTrackballCamera())
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

    # ---- the mouse, forwarded to VTK's trackball camera
    def send(self, event, x=0.0, y=0.0, ctrl=False, shift=False, repeat=0):
        """Give the interactor a mouse event by VTK's name without "Event"
        (LeftButtonPress, MouseMove, LeftButtonRelease, MouseWheelForward,
        RightButtonPress, ...) at a position in widget pixels (origin top
        left); the view follows. Returns whether the scene was rendered."""
        if self.interactor is None:
            return False
        ratio = self.devicePixelRatioF()
        self.interactor.SetEventInformationFlipY(int(x * ratio), int(y * ratio), int(ctrl),
                                                 int(shift), "\0", int(repeat))
        self._rendered = False
        getattr(self.interactor, f"{event}Event")()
        if self._rendered:
            self._read()
            self.update()
            return True
        return False

    def drag(self, start, end, steps=10, button="LeftButton", ctrl=False, shift=False):
        """A drag from start to end (widget pixels) with a button (tests,
        drivers)."""
        (x0, y0), (x1, y1) = start, end
        self.send(f"{button}Press", x0, y0, ctrl, shift)
        for t in np.linspace(0, 1, max(int(steps), 1) + 1)[1:]:
            self.send("MouseMove", x0 + t * (x1 - x0), y0 + t * (y1 - y0), ctrl, shift)
        self.send(f"{button}Release", x1, y1, ctrl, shift)

    @staticmethod
    def _modifiers(event):
        modifiers = event.modifiers()
        return (bool(modifiers & Qt.KeyboardModifier.ControlModifier),
                bool(modifiers & Qt.KeyboardModifier.ShiftModifier))

    def _mouse(self, event, suffix, repeat=0):
        button = BUTTONS.get(event.button())
        if button is None:
            return
        point = event.position()
        self.send(f"{button}{suffix}", point.x(), point.y(), *self._modifiers(event), repeat)

    def mousePressEvent(self, event):
        self._mouse(event, "Press")

    def mouseDoubleClickEvent(self, event):
        self._mouse(event, "Press", repeat=1)

    def mouseReleaseEvent(self, event):
        self._mouse(event, "Release")

    def mouseMoveEvent(self, event):
        point = event.position()
        self.send("MouseMove", point.x(), point.y(), *self._modifiers(event))

    def wheelEvent(self, event):
        delta = event.angleDelta().y()
        if delta:
            point = event.position()
            self.send("MouseWheelForward" if delta > 0 else "MouseWheelBackward",
                      point.x(), point.y(), *self._modifiers(event))
        event.accept()


class _Hint(QLabel):
    """A line of text that ends in an ellipsis when it does not fit."""

    def __init__(self, text):
        super().__init__(text)
        self.full = text
        self.setMinimumWidth(0)
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.setText(self.fontMetrics().elidedText(self.full, Qt.TextElideMode.ElideRight,
                                                   self.width()))


class SceneView(QWidget):
    """The pyvista canvas with its bar: Reset view (the first viewing
    angle, everything in sight), Save image, and what the mouse does."""

    def __init__(self, name, parent=None):
        super().__init__(parent)
        self.setObjectName(name)
        self.canvas = SceneCanvas()
        self.canvas.setObjectName(f"{name}Canvas")
        self.reset = QToolButton()
        self.reset.setText("Reset view")
        self.reset.setObjectName(f"{name}Reset")
        self.reset.setToolTip("the first viewing angle, with everything in sight")
        self.reset.clicked.connect(self.reset_view)
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

    def show_scene(self, build, keep=False, fit=True, **overlays):
        """Draw a geometry with overlays (draw_scene). keep: the camera
        stays where the user left it (the same system drawn again), and
        with fit it takes everything in sight again from there (its sites
        changed); otherwise the view starts oblique, everything in sight."""
        plotter = self.canvas.ensure()
        camera = plotter.camera_position if keep and self.drawn else None
        self.bounds = draw_scene(plotter, build, **overlays)
        self.drawn = True
        if camera is None:
            self.reset_view()
            return
        plotter.camera_position = camera
        if fit:
            self.fit()
        else:
            self.canvas.changed()

    def set_selection(self, points):
        if self.canvas.plotter is not None:
            set_selection(self.canvas.plotter, points)
            self.canvas.changed()

    def fit(self):
        """Everything in sight, from the same angle."""
        if self.canvas.plotter is not None:
            self.canvas.plotter.reset_camera(render=False, bounds=self.bounds)
            self.canvas.changed()

    def reset_view(self):
        """The first viewing angle (oblique), everything in sight."""
        if self.canvas.plotter is not None:
            self.canvas.plotter.view_isometric(render=False)
            self.fit()

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
