"""How the view is moved in space (PLAN.md phase 8): the arithmetic behind
the two ways of moving that guiqula borrows, without Qt, VTK or matplotlib,
so that it is tested without a window.

The 3D scene moves as Blender's viewport does. `Turntable` is the camera:
a target point, a distance to it, and two angles, the azimuth about the
vertical (z) axis and the elevation above the xy plane, so that z stays up
however the view is turned (Blender's turntable orbit). A drag orbits, pans
or zooms it, the numpad steps it by 15 degrees, the axis views (front,
right, top and their opposite sides) put it on an axis and, as Blender's
auto perspective does, switch to the orthographic projection until the
view is turned again.

The flat drawings move as Inkscape's canvas does. A view there is the pair
of limits ((x0, x1), (y0, y1)); the functions below scroll it, zoom it about
a point, and `ZoomHistory` keeps the earlier ones for the previous and next
zoom keys.
"""
import numpy as np

FIELD_OF_VIEW = 30.0        # degrees, vertical: VTK's default, and the camera's
ORBIT_PER_PIXEL = 0.007     # radians turned per pixel dragged (Blender's turntable)
ORBIT_STEP = 15.0           # degrees per numpad step
PAN_STEP = 32.0             # pixels per numpad step or wheel notch of a pan
ZOOM_STEP = 1.2             # distance ratio per wheel notch or key in 3D
MIN_RADIUS = 1.0            # a frame never closes in on less than this (site units)

# the direction the camera looks from: (azimuth, elevation) in degrees; front looks
# along +y with x to the right, right looks along -x, top down with y up (Blender's)
AXIS_VIEWS = {"front": (-90.0, 0.0), "back": (90.0, 0.0),
              "right": (0.0, 0.0), "left": (180.0, 0.0),
              "top": (-90.0, 90.0), "bottom": (-90.0, -90.0)}
OPPOSITE = {"front": "back", "back": "front", "right": "left", "left": "right",
            "top": "bottom", "bottom": "top"}
STEPS = ("left", "right", "up", "down")


def _wrap(angle):
    """An angle in degrees, in (-180, 180]."""
    angle = (angle + 180.0) % 360.0 - 180.0
    return 180.0 if angle == -180.0 else angle


class Turntable:
    """A camera that orbits a target about the vertical axis (Blender's
    turntable orbit). Angles in degrees; the camera looks from
    (cos(el) cos(az), cos(el) sin(az), sin(el)) times the distance, away
    from the target, and its up direction is the derivative with respect to
    the elevation, so that it stays continuous over the poles (past them the
    view is upside down and a horizontal drag turns the other way, as in
    Blender)."""

    def __init__(self, target=(0.0, 0.0, 0.0), distance=10.0, azimuth=45.0,
                 elevation=35.264, ortho=False):
        self.target = np.array(target, dtype=float)
        self.distance = float(distance)
        self.azimuth = _wrap(azimuth)
        self.elevation = _wrap(elevation)
        self.ortho = bool(ortho)
        self.auto_ortho = False     # the orthographic projection is an axis view's
        self.perspective_fov = FIELD_OF_VIEW

    def copy(self):
        other = Turntable(self.target, self.distance, self.azimuth, self.elevation, self.ortho)
        other.auto_ortho = self.auto_ortho
        return other

    # ---- geometry
    def directions(self):
        """(forward, right, up) unit vectors of the view."""
        az, el = np.radians(self.azimuth), np.radians(self.elevation)
        towards_camera = np.array([np.cos(el) * np.cos(az), np.cos(el) * np.sin(az),
                                   np.sin(el)])
        up = np.array([-np.sin(el) * np.cos(az), -np.sin(el) * np.sin(az), np.cos(el)])
        forward = -towards_camera
        return forward, np.cross(forward, up), up

    def position(self):
        forward, _, _ = self.directions()
        return self.target - forward * self.distance

    def parallel_scale(self):
        """Half the height seen in the orthographic projection: what the
        perspective sees at the target, so that toggling does not zoom."""
        return self.distance * np.tan(np.radians(self.perspective_fov) / 2)

    def per_pixel(self, height):
        """Length seen at the target per pixel of a view `height` pixels high."""
        return 2 * self.parallel_scale() / max(float(height), 1.0)

    def apply(self, camera):
        """Set a pyvista camera to this view."""
        _, _, up = self.directions()
        camera.position = tuple(float(x) for x in self.position())
        camera.focal_point = tuple(float(x) for x in self.target)
        camera.up = tuple(float(x) for x in up)
        camera.view_angle = self.perspective_fov
        camera.parallel_projection = self.ortho
        camera.parallel_scale = float(self.parallel_scale())

    # ---- what a name says about the view
    def axis(self):
        """The name of the axis view the camera is on ("front", ...), or None."""
        for name, (azimuth, elevation) in AXIS_VIEWS.items():
            if abs(_wrap(self.elevation - elevation)) < 1e-6 and \
                    abs(_wrap(self.azimuth - azimuth)) < 1e-6:
                return name
        return None

    def description(self):
        """"Front Orthographic", "User Perspective": what Blender writes in
        the corner of its viewport."""
        return f"{(self.axis() or 'user').capitalize()} " \
               f"{'Orthographic' if self.ortho else 'Perspective'}"

    # ---- the gestures
    def _turned(self):
        """The view is no longer on an axis: auto perspective returns to the
        perspective projection an axis view had switched away from."""
        if self.auto_ortho:
            self.ortho = False
            self.auto_ortho = False

    def _sign(self):
        """Upside down (past a pole) a horizontal drag turns the other way."""
        return 1.0 if np.cos(np.radians(self.elevation)) >= 0 else -1.0

    def orbit(self, dx, dy):
        """A drag of (dx, dy) pixels (y down) turns the scene under the
        pointer: to the right shows more of the left side."""
        self.azimuth = _wrap(self.azimuth - self._sign() * np.degrees(dx * ORBIT_PER_PIXEL))
        self.elevation = _wrap(self.elevation + np.degrees(dy * ORBIT_PER_PIXEL))
        self._turned()

    def orbit_step(self, direction):
        """A numpad step: the camera moves left, right, up or down by 15 degrees."""
        if direction not in STEPS:
            raise ValueError(f"unknown orbit step {direction!r}; steps: {list(STEPS)}")
        if direction in ("left", "right"):
            sign = -1.0 if direction == "left" else 1.0
            self.azimuth = _wrap(self.azimuth + sign * self._sign() * ORBIT_STEP)
        else:
            self.elevation = _wrap(self.elevation + (ORBIT_STEP if direction == "up"
                                                     else -ORBIT_STEP))
        self._turned()

    def pan(self, dx, dy, height):
        """A drag of (dx, dy) pixels moves the scene with the pointer."""
        _, right, up = self.directions()
        scale = self.per_pixel(height)
        self.target = self.target - right * dx * scale + up * dy * scale

    def pan_step(self, direction, height):
        """A numpad or wheel step: the view moves left, right, up or down."""
        if direction not in STEPS:
            raise ValueError(f"unknown pan step {direction!r}; steps: {list(STEPS)}")
        _, right, up = self.directions()
        move = {"left": -right, "right": right, "up": up, "down": -up}[direction]
        self.target = self.target + move * PAN_STEP * self.per_pixel(height)

    def zoom(self, notches):
        """Wheel notches (positive: in), by ZOOM_STEP a notch."""
        self.distance = max(self.distance / ZOOM_STEP ** notches, 1e-6)

    def zoom_drag(self, start_distance, start_y, y):
        """Ctrl and a drag: the distance follows the pointer's distance from
        the top edge of the view (so dragging up zooms in), as Blender's."""
        self.distance = max(start_distance * (y + 5.0) / (start_y + 5.0), 1e-6)

    def axis_view(self, name, opposite=False):
        """Numpad 1, 3, 7 (Ctrl: the opposite side): look along an axis, in
        the orthographic projection unless the view was already orthographic
        by choice."""
        if name not in AXIS_VIEWS:
            raise ValueError(f"unknown view {name!r}; views: {list(AXIS_VIEWS)}")
        if opposite:
            name = OPPOSITE[name]
        self.azimuth, self.elevation = AXIS_VIEWS[name]
        if not self.ortho:
            self.ortho = True
            self.auto_ortho = True
        return name

    def flip(self):
        """Numpad 9: the opposite side, half a turn about the vertical axis."""
        self.azimuth = _wrap(self.azimuth + 180.0)
        self._turned()

    def toggle_projection(self):
        """Numpad 5: perspective or orthographic, by choice from now on."""
        self.ortho = not self.ortho
        self.auto_ortho = False
        return self.ortho

    def frame(self, bounds, aspect=1.0):
        """Everything in `bounds` (xmin, xmax, ymin, ymax, zmin, zmax) in
        sight from the same angle; aspect is the width over the height of
        the view."""
        if bounds is None:
            self.target = np.zeros(3)
            self.distance = 10.0
            return
        low, high = np.asarray(bounds, dtype=float)[0::2], np.asarray(bounds, dtype=float)[1::2]
        self.target = (low + high) / 2
        radius = max(0.5 * float(np.linalg.norm(high - low)), MIN_RADIUS)
        half = np.arctan(np.tan(np.radians(self.perspective_fov) / 2) * min(1.0, aspect))
        self.distance = radius / np.sin(half)


# ---- flat drawings (Inkscape)
SCROLL_STEP = 40.0      # pixels per wheel notch or Ctrl+arrow key
ZOOM_FACTOR = 2 ** 0.5  # the view shrinks or grows by this per notch or key
HISTORY_LIMIT = 100


def zoom_limits(limits, centre, factor):
    """(low, high) scaled by `factor` about `centre` (below 1 zooms in)."""
    low, high = limits
    return centre - (centre - low) * factor, centre + (high - centre) * factor


def shift_limits(limits, delta):
    return limits[0] + delta, limits[1] + delta


def limits_around(points, margin=0.1, minimum=1.0):
    """Limits that hold `points` (values along one axis) with a margin
    (a fraction of the span), at least `minimum` wide."""
    points = np.asarray(points, dtype=float)
    low, high = float(points.min()), float(points.max())
    span = max(high - low, minimum)
    middle = (low + high) / 2
    return middle - span / 2 * (1 + 2 * margin), middle + span / 2 * (1 + 2 * margin)


class ZoomHistory:
    """The views before and after the current one (Inkscape's previous and
    next zoom): a zoom pushes the view it leaves, and going back or forward
    exchanges the current view with a stored one."""

    def __init__(self, limit=HISTORY_LIMIT):
        self.limit = limit
        self.past = []
        self.future = []

    def push(self, view):
        if self.past and _same_view(self.past[-1], view):
            return
        self.past.append(view)
        del self.past[:-self.limit]
        self.future.clear()

    def previous(self, current):
        """The view before, or None; `current` becomes the next one."""
        if not self.past:
            return None
        self.future.append(current)
        return self.past.pop()

    def next(self, current):
        if not self.future:
            return None
        self.past.append(current)
        return self.future.pop()

    def clear(self):
        self.past.clear()
        self.future.clear()


def _same_view(a, b):
    return np.allclose(np.asarray(a, dtype=float), np.asarray(b, dtype=float))
