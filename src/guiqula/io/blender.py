"""Export a 3D drawing to Blender: the structure canvas or a result on the
atoms (the local density of states, a magnetization) as a .blend file that
Blender opens, or as the Python script that builds it.

A .blend is written by Blender alone, so the export writes a script
(``script``) that builds the scene with Blender's Python API and runs it in
a Blender found on this computer, in the background, which saves the file
(``write``). The scene is what the window draws, as plain arrays (``scene``
in ui/structure.py makes them from a build and its overlays):

- the atoms, one object per site sharing one sphere mesh, coloured by
  sublattice or by the value on the site (the object's colour, read by the
  material through an Object Info node, so the colours stay editable one
  by one), with the value kept as the object's custom property ``value``;
- the bonds and the edges of the unit cell, one mesh of cylinders each;
- the arrows of a vector per site, one object per site sharing one arrow
  mesh, with the vector kept as the custom property ``vector``;
- a sun, a camera framing the sites, a pale background, and the 3D
  viewports showing the objects' colours and looking at the sites.

The script needs Blender 3.0 or later (its bmesh operators take a radius, which
they called diameter before 3.0; it was run on 5.2.2);
``find`` looks for one: the program given, $GUIQULA_BLENDER, ``blender`` on
the PATH, and the usual places of an installation, and refuses an older
one, saying which it found. No Qt and no pyqula here.
"""
import glob
import json
import os
import re
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

MINIMUM = (3, 0)
TIMEOUT = 600              # seconds write() waits for a Blender run
ENV = "GUIQULA_BLENDER"
PLACES = ("/Applications/Blender.app/Contents/MacOS/Blender", "/snap/bin/blender",
          "/var/lib/flatpak/exports/bin/org.blender.Blender",
          "C:/Program Files/Blender Foundation/Blender*/blender.exe")
SUFFIXES = (".blend", ".py")


class BlenderError(RuntimeError):
    pass


# ---- finding Blender
def version(program):
    """(major, minor) of a Blender program, or None when it does not run
    or does not say."""
    try:
        done = subprocess.run([str(program), "--version"], capture_output=True, text=True,
                              timeout=60, stdin=subprocess.DEVNULL)
    except (OSError, subprocess.SubprocessError):
        return None
    match = re.search(r"Blender\s+(\d+)\.(\d+)", done.stdout + done.stderr)
    return (int(match.group(1)), int(match.group(2))) if match else None


def candidates(program=None):
    """The programs to try, in order: the one given, $GUIQULA_BLENDER,
    blender on the PATH, the usual places; each once."""
    found = [program, os.environ.get(ENV), shutil.which("blender")]
    for place in PLACES:
        found.extend(sorted(glob.glob(place), reverse=True))
    seen, unique = set(), []
    for path in found:
        if path and path not in seen and (Path(path).is_file() or shutil.which(path)):
            seen.add(path)
            unique.append(path)
    return unique


def find(program=None):
    """The first Blender of version MINIMUM or later among candidates();
    raises BlenderError saying what was found when none is."""
    refused = []
    for path in candidates(program):
        found = version(path)
        if found is not None and found >= MINIMUM:
            return path
        refused.append(f"{path} ({'Blender %d.%d' % found if found else 'not Blender'})")
    wanted = f"Blender {MINIMUM[0]}.{MINIMUM[1]} or later"
    if refused:
        raise BlenderError(f"no {wanted} found; refused: {', '.join(refused)}")
    raise BlenderError(f"no {wanted} found (set ${ENV} or choose the program)")


# ---- the script
def script(scene):
    """The Python script that builds a scene in Blender (3.0 or later),
    and saves it as the .blend named after a "--" on Blender's command
    line, if any. The scene is embedded, so the script stands alone: it
    can also be run from Blender's Scripting workspace."""
    data = json.dumps(_plain(scene), separators=(",", ":"))
    title = re.sub(r'["\\\s]+', " ", str(scene.get("title") or "guiqula")).strip()
    return TEMPLATE.replace("@TITLE@", title).replace("@SCENE@", data)


def _plain(value):
    """JSON-ready: arrays as lists, numpy scalars as floats."""
    if hasattr(value, "tolist"):
        return value.tolist()
    if isinstance(value, dict):
        return {key: _plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    return value


def write(path, scene, program=None, timeout=TIMEOUT):
    """Write a scene to path: a .blend (built by a Blender found by find,
    run in the background) or a .py (the script alone), and wait for it.
    Returns the path written; raises BlenderError when no Blender is found
    or its run fails, with what Blender printed."""
    export = start(path, scene, program)
    return export.wait(timeout)


def start(path, scene, program=None):
    """Start writing a scene to path (write without waiting): an Export
    whose poll() says when the file is there. A .py is written at once."""
    path = Path(path)
    if path.suffix not in SUFFIXES:
        raise ValueError(f"{path.name}: a Blender export is a .blend or a .py file")
    path.parent.mkdir(parents=True, exist_ok=True)
    return Export(path, script(scene), None if path.suffix == ".py" else find(program))


class Export:
    """A Blender run saving a .blend, in a scratch directory of its own
    (Blender writes nothing next to the file asked for until it is
    complete), or a script written at once (blender None)."""

    def __init__(self, path, text, blender):
        self.path, self.blender = Path(path), blender
        self.started = time.monotonic()
        self.done = False
        self.error = None
        self.process = None
        if blender is None:
            self.path.write_text(text, encoding="utf-8")
            self.done = True
            return
        self.scratch = tempfile.TemporaryDirectory(prefix="guiqula_blender_")
        folder = Path(self.scratch.name)
        (folder / "scene.py").write_text(text, encoding="utf-8")
        self.target = folder / "scene.blend"
        self.log = open(folder / "blender.log", "w+", encoding="utf-8")
        try:
            self.process = subprocess.Popen(
                [blender, "--background", "--factory-startup", "--python-exit-code", "1",
                 "--python", str(folder / "scene.py"), "--", str(self.target)],
                cwd=folder, stdout=self.log, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL)
        except OSError as error:          # a program that is there but does not run
            self.log.close()
            self.scratch.cleanup()
            raise BlenderError(f"{blender} does not run: {error}") from None

    def poll(self):
        """Whether the run is over: then the file is in place, or error
        says why not (and the run is cleaned up either way)."""
        if self.done:
            return True
        code = self.process.poll()
        if code is None:
            return False
        self._finish(code)
        return True

    def _finish(self, code):
        self.done = True
        self.log.seek(0)
        printed = self.log.read().strip().splitlines()[-12:]
        self.log.close()
        if code != 0 or not self.target.is_file():
            self.error = f"Blender failed (exit {code}): " + "\n".join(printed)
        else:
            shutil.move(str(self.target), str(self.path))
        self.scratch.cleanup()

    def cancel(self):
        if not self.done:
            self.process.kill()
            self.process.wait()
            self._finish(-1)
            self.error = "cancelled"

    def wait(self, timeout=TIMEOUT):
        """Wait for the run; returns the path, or raises BlenderError."""
        if not self.done:
            try:
                self.process.wait(timeout)
            except subprocess.TimeoutExpired:
                self.cancel()
                raise BlenderError(f"Blender took more than {timeout} s") from None
            self.poll()
        if self.error:
            raise BlenderError(self.error)
        return self.path


TEMPLATE = r'''"""@TITLE@: a scene exported by guiqula, built in Blender (3.0 or later).

Open it in Blender's Scripting workspace and press Run Script, or run
    blender --python scene.py
and, to save it as a .blend without opening a window,
    blender --background --python scene.py -- scene.blend
The atoms are objects sharing one sphere mesh, coloured by their object
colour (the material reads it with an Object Info node), the value on a
site is its custom property "value", the vector of an arrow its "vector".
Lengths are pyqula's, in which first neighbours are at a distance 1.
"""
import json
import math
import sys

import bmesh
import bpy
from mathutils import Vector

SCENE = json.loads(r"""@SCENE@""")


def rgba(color):
    """An sRGB colour (as the window draws it) in Blender's linear space."""
    return tuple(c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
                 for c in color[:3]) + (1.0,)


def material(name):
    """One material for every object: its base colour is the object's colour."""
    mat = bpy.data.materials.new(name)
    if hasattr(mat, "use_nodes") and not mat.use_nodes:
        mat.use_nodes = True
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    bsdf = next(node for node in nodes if node.type == "BSDF_PRINCIPLED")
    info = nodes.new("ShaderNodeObjectInfo")
    links.new(info.outputs["Color"], bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value = 0.4
    return mat


def smooth(mesh):
    for polygon in mesh.polygons:
        polygon.use_smooth = True


def mesh_of(name, build):
    """A mesh made by build(bm), a function filling a bmesh."""
    bm = bmesh.new()
    build(bm)
    mesh = bpy.data.meshes.new(name)
    bm.to_mesh(mesh)
    bm.free()
    return mesh


def cone(bm, radius1, radius2, depth, z0, segments):
    """A cone (a cylinder when the radii agree) along z from z0 to z0 + depth."""
    made = bmesh.ops.create_cone(bm, cap_ends=True, cap_tris=False, segments=segments,
                                 radius1=radius1, radius2=radius2, depth=depth)
    bmesh.ops.translate(bm, vec=(0.0, 0.0, z0 + depth / 2), verts=made["verts"])


def tubes(name, segments, radius, sides=10):
    """One mesh of cylinders, one per segment [[x, y, z], [x, y, z]]."""
    verts, faces = [], []
    for a, b in segments:
        a, b = Vector(a), Vector(b)
        axis = b - a
        if axis.length < 1e-9:
            continue
        axis.normalize()
        side = axis.orthogonal().normalized()
        other = axis.cross(side)
        start = len(verts)
        for end in (a, b):
            for k in range(sides):
                angle = 2 * math.pi * k / sides
                verts.append(end + radius * (math.cos(angle) * side + math.sin(angle) * other))
        for k in range(sides):
            n = (k + 1) % sides
            faces.append((start + k, start + n, start + sides + n, start + sides + k))
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata([tuple(v) for v in verts], [], faces)
    mesh.update()
    smooth(mesh)
    return mesh


def place(name, mesh, collection, color, mat, location=(0.0, 0.0, 0.0)):
    obj = bpy.data.objects.new(name, mesh)
    obj.location = location
    obj.color = rgba(color)
    if not mesh.materials:
        mesh.materials.append(mat)
    collection.objects.link(obj)
    return obj


def child(parent, name):
    collection = bpy.data.collections.new(name)
    parent.children.link(collection)
    return collection


def build():
    scene = bpy.context.scene
    if not bpy.data.filepath:            # a new file: Blender's cube and light go
        for name in ("Cube", "Light"):
            obj = bpy.data.objects.get(name)
            if obj is not None:
                bpy.data.objects.remove(obj, do_unlink=True)
    top = bpy.data.collections.new(SCENE["title"] or "guiqula")
    scene.collection.children.link(top)
    mat = material("guiqula")
    atoms = SCENE["atoms"]
    positions = atoms["positions"]
    radius = atoms["radius"]
    sphere = mesh_of("atom", lambda bm: bmesh.ops.create_uvsphere(
        bm, u_segments=24, v_segments=12, radius=radius))
    smooth(sphere)
    group = child(top, "atoms")
    values = atoms.get("values")
    for i, (position, color) in enumerate(zip(positions, atoms["colors"])):
        obj = place(f"atom {i}", sphere, group, color, mat, position)
        if values is not None and values[i] is not None:
            obj["value"] = values[i]
    if atoms.get("label"):
        group["values"] = atoms["label"]
        group["range"] = atoms["range"]
        group["colormap"] = atoms["colormap"]
    for key, name in (("bonds", "bonds"), ("cell", "unit cell")):
        part = SCENE.get(key)
        if part and part["segments"]:
            place(name, tubes(name, part["segments"], part["radius"]), child(top, name),
                  part["color"], mat)
    arrows = SCENE.get("arrows")
    if arrows and arrows["tails"]:
        width = arrows["width"]
        shape = mesh_of("arrow", lambda bm: (cone(bm, 0.045 * width, 0.045 * width, 0.7, 0.0, 12),
                                             cone(bm, 0.12 * width, 0.0, 0.3, 0.7, 16)))
        smooth(shape)
        group = child(top, "arrows")
        if arrows.get("label"):
            group["vectors"] = arrows["label"]
        up = Vector((0.0, 0.0, 1.0))
        for i, (tail, vector, original) in enumerate(zip(arrows["tails"], arrows["vectors"],
                                                         arrows["original"])):
            v = Vector(vector)
            obj = place(f"arrow {arrows['sites'][i]}", shape, group, arrows["color"], mat,
                        tail)
            obj.rotation_mode = "QUATERNION"
            obj.rotation_quaternion = up.rotation_difference(v)
            obj.scale = (v.length,) * 3
            obj["vector"] = original
    # the light, the camera, the background and the viewports
    low, high = Vector(SCENE["bounds"][0]), Vector(SCENE["bounds"][1])
    centre, size = (low + high) / 2, max((high - low).length, 1.0)
    sun = bpy.data.lights.new("sun", type="SUN")
    sun.energy = 3.0
    light = bpy.data.objects.new("sun", sun)
    light.rotation_euler = (math.radians(35), math.radians(15), math.radians(30))
    top.objects.link(light)
    camera = scene.camera
    if camera is None:
        camera = bpy.data.objects.new("Camera", bpy.data.cameras.new("Camera"))
        top.objects.link(camera)
        scene.camera = camera
    direction = Vector((0.0, -0.6, 1.0)).normalized()
    distance = 0.6 * size / math.tan(camera.data.angle / 2)
    camera.location = centre + distance * direction
    camera.rotation_mode = "QUATERNION"
    camera.rotation_quaternion = direction.to_track_quat("Z", "Y")
    camera.data.clip_end = max(camera.data.clip_end, 10 * distance)
    world = scene.world or bpy.data.worlds.new("World")
    scene.world = world
    world.color = (0.9, 0.9, 0.9)
    if world.node_tree is not None:
        for node in world.node_tree.nodes:
            if node.type == "BACKGROUND":
                node.inputs["Color"].default_value = (0.9, 0.9, 0.9, 1.0)
    for screen in bpy.data.screens:
        for area in screen.areas:
            for space in area.spaces:
                if space.type == "VIEW_3D":
                    space.shading.color_type = "OBJECT"
                    space.clip_end = max(space.clip_end, 10 * distance)
                    space.region_3d.view_location = centre
                    space.region_3d.view_distance = 1.2 * distance


build()
if "--" in sys.argv[1:]:
    rest = sys.argv[sys.argv.index("--") + 1:]
    if rest:
        bpy.ops.wm.save_as_mainfile(filepath=rest[0])
'''
