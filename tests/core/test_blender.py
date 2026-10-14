"""The export to Blender (io/blender.py): the script that builds the scene,
the search for a Blender of 3.0 or later, the background run saving the
.blend. A fake Blender stands in for the program; the run of a real one is
tested when one is found ($GUIQULA_BLENDER, or blender on the PATH)."""
import ast
import json
import subprocess
import sys

import numpy as np
import pytest

from guiqula.io import blender


def scene(n=3, arrows=True):
    r = np.array([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.5, 0.8, 0.3]])[:n]
    out = {"title": 'a "quoted" title\\', "bounds": [r.min(axis=0), r.max(axis=0)],
           "atoms": {"positions": r, "radius": 0.2, "colors": np.full((n, 3), 0.5),
                     "values": [0.1, None, 0.3][:n], "label": "LDOS", "range": [0.0, 0.3],
                     "colormap": "viridis"},
           "bonds": {"segments": np.stack([r[:-1], r[1:]], axis=1), "radius": 0.05,
                     "color": [0.6, 0.6, 0.6]},
           "cell": {"segments": np.zeros((0, 2, 3)), "radius": 0.02, "color": [0, 0, 1]}}
    if arrows:
        out["arrows"] = {"sites": np.arange(n), "tails": r, "vectors": np.ones((n, 3)) * 0.5,
                         "original": np.ones((n, 3)), "width": 1.0, "color": [0, 0, 0],
                         "label": "magnetization"}
    return out


def embedded(text):
    """The scene a script carries."""
    start = text.index('SCENE = json.loads(r"""') + len('SCENE = json.loads(r"""')
    return json.loads(text[start:text.index('""")', start)])


def test_the_script_parses_and_carries_the_scene(tmp_path):
    path = blender.write(tmp_path / "scene.py", scene())
    text = path.read_text()
    ast.parse(text)
    data = embedded(text)
    assert data["atoms"]["values"] == [0.1, None, 0.3]
    assert len(data["arrows"]["tails"]) == 3 and data["title"] == 'a "quoted" title\\'
    assert text.startswith('"""a quoted title: a scene exported by guiqula')


def test_a_file_that_is_neither_blend_nor_py_is_refused(tmp_path):
    with pytest.raises(ValueError):
        blender.write(tmp_path / "scene.obj", scene())


@pytest.fixture
def fake(tmp_path, monkeypatch):
    """A program answering --version as Blender of a given version and,
    run on a script, writing the file after "--" (or failing)."""
    monkeypatch.delenv(blender.ENV, raising=False)
    monkeypatch.setenv("PATH", str(tmp_path / "nowhere"))
    monkeypatch.setattr(blender, "PLACES", ())

    def make(name, version, fail=False):
        path = tmp_path / name
        path.write_text(f"""#!{sys.executable}
import sys
if "--version" in sys.argv:
    print("Blender {version}")
elif {fail!r}:
    print("Traceback: the scene did not build", file=sys.stderr)
    sys.exit(1)
else:
    open(sys.argv[sys.argv.index("--python") + 1]).read()
    open(sys.argv[sys.argv.index("--") + 1], "w").write("BLENDER")
""")
        path.chmod(0o755)
        return str(path)
    return make


def test_an_old_blender_is_refused_saying_which(fake, monkeypatch):
    old = fake("blender279", "2.79 (sub 0)")
    with pytest.raises(blender.BlenderError, match=r"2\.79"):
        blender.find(old)
    before = fake("blender293", "2.93.1")          # its bmesh operators take a diameter
    with pytest.raises(blender.BlenderError, match=r"2\.93"):
        blender.find(before)
    new = fake("blender52", "5.2.2 LTS")
    monkeypatch.setenv(blender.ENV, new)
    assert blender.find(old) == new                 # the old one given, the variable's next
    assert blender.version(new) == (5, 2)


def test_no_blender_at_all_says_how_to_name_one(fake):
    with pytest.raises(blender.BlenderError, match=blender.ENV):
        blender.find()


def test_a_blend_is_written_by_the_blender_found(fake, tmp_path):
    program = fake("blender", "4.2.0")
    out = blender.write(tmp_path / "out" / "scene.blend", scene(), program)
    assert out.read_text() == "BLENDER"
    export = blender.start(tmp_path / "later.blend", scene(), program)
    export.wait()
    assert export.poll() and export.error is None and (tmp_path / "later.blend").is_file()


def test_a_failing_blender_says_what_it_printed(fake, tmp_path):
    program = fake("blender", "4.2.0", fail=True)
    with pytest.raises(blender.BlenderError, match="did not build"):
        blender.write(tmp_path / "scene.blend", scene(), program)
    assert not (tmp_path / "scene.blend").exists()


def real_blender():
    try:
        return blender.find()
    except blender.BlenderError as error:
        pytest.skip(str(error))


def test_a_real_blender_builds_the_scene(tmp_path):
    program = real_blender()
    out = blender.write(tmp_path / "scene.blend", scene(), program)
    check = """
import bpy, json
atoms = [o for o in bpy.data.objects if o.name.startswith("atom ")]
arrows = [o for o in bpy.data.objects if o.name.startswith("arrow ")]
print("CHECK", json.dumps({"atoms": len(atoms), "arrows": len(arrows),
    "bonds": "bonds" in bpy.data.objects, "value": atoms[0].get("value"),
    "vector": list(arrows[0]["vector"]), "camera": bpy.context.scene.camera is not None,
    "cube": "Cube" in bpy.data.objects, "values": bpy.data.collections["atoms"]["values"]}))
"""
    done = subprocess.run([program, "--background", "--factory-startup", str(out),
                           "--python-expr", check], capture_output=True, text=True, timeout=300)
    line = next(l for l in done.stdout.splitlines() if l.startswith("CHECK "))
    found = json.loads(line[len("CHECK "):])
    assert found == {"atoms": 3, "arrows": 3, "bonds": True, "value": 0.1,
                     "vector": [1.0, 1.0, 1.0], "camera": True, "cube": False,
                     "values": "LDOS"}
