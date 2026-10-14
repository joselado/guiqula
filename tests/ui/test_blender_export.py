"""The export to Blender from the window (io/blender.py): the Blender
button of a result drawn on the atoms and of the canvas, and the
export_blender action, as a script and as a .blend written by a fake
Blender, waited for or polled from the window's timer."""
import ast
import json
import sys

import pytest

from guiqula.io import blender
from guiqula.ui.app import build_main_window


@pytest.fixture(scope="module")
def window(qapp):
    window = build_main_window()
    window.resize(1200, 800)
    window.show()
    window.start_session("graphene_island", warm=False)
    yield window
    window.close()


def settle(qtbot, window, timeout=120_000):
    session = window.session
    qtbot.waitUntil(lambda: not window.build_timer.isActive() and all(
        session.build_is_current(s.id) or s.id in session.build_errors
        for s in session.document.systems), timeout=timeout)


def scene_of(path):
    text = path.read_text()
    ast.parse(text)
    start = text.index('SCENE = json.loads(r"""') + len('SCENE = json.loads(r"""')
    return json.loads(text[start:text.index('""")', start)])


@pytest.fixture
def fake_blender(tmp_path):
    path = tmp_path / "blender"
    path.write_text(f"""#!{sys.executable}
import sys
if "--version" in sys.argv:
    print("Blender 4.2.0")
else:
    open(sys.argv[sys.argv.index("--") + 1], "w").write("BLENDER")
""")
    path.chmod(0o755)
    return str(path)


def test_the_button_shows_on_a_result_drawn_on_the_atoms(window, qtbot):
    settle(qtbot, window)
    session = window.session
    for calc in ("c1", "c2"):
        assert session.run_calculation(calc, wait=True, timeout=600).status == "done"
    window.result_view("c1")
    window.result_view("c2")
    qtbot.waitUntil(lambda: window.plots["c2"].result is not None)
    ldos, dos = window.plots["c2"], window.plots["c1"]
    assert ldos.bar.shown(ldos.blender) and ldos.blender.objectName() == "blender_c2"
    assert not dos.bar.shown(dos.blender)                  # a curve has no atoms
    assert window.structure.blender.objectName() == "structureBlender"
    assert window.structure.blender.isEnabled()


def test_a_result_exports_its_atoms_coloured_by_the_value(window, qtbot, tmp_path):
    path = window.session.act("export_blender", calculation="c2",
                              path=str(tmp_path / "ldos.py"))
    data = scene_of(tmp_path / "ldos.py")
    sites = len(window.session.result("c2").structure["positions"])
    assert path.endswith("ldos.py") and len(data["atoms"]["positions"]) == sites
    assert data["atoms"]["label"] == "LDOS" and len(set(map(tuple, data["atoms"]["colors"]))) > 1
    assert data["bonds"]["segments"] and "arrows" not in data
    with pytest.raises(Exception, match="not drawn on the atoms"):
        window._blender_scene("c1")


def test_the_canvas_exports_its_structure(window, tmp_path):
    window.session.act("export_blender", path=str(tmp_path / "flake.py"))
    data = scene_of(tmp_path / "flake.py")
    assert len(data["atoms"]["positions"]) == len(window.structure.build["positions"])
    assert data["title"] == window.structure.system_id


def test_a_blend_is_written_while_the_window_goes_on(window, qtbot, tmp_path, fake_blender):
    out = tmp_path / "ldos.blend"
    window.session.act("export_blender", calculation="c2", path=str(out), wait=False,
                       blender=fake_blender)
    qtbot.waitUntil(lambda: not window.blender_runs, timeout=30_000)
    assert out.read_text() == "BLENDER"
    assert "exported to Blender" in window.status_message.text()
    window.session.act("export_blender", calculation="c2", path=str(tmp_path / "b.blend"),
                       blender=fake_blender)
    assert (tmp_path / "b.blend").is_file()


def test_no_blender_is_an_error_saying_so(window, tmp_path, monkeypatch):
    monkeypatch.setenv("PATH", str(tmp_path))
    monkeypatch.delenv(blender.ENV, raising=False)
    monkeypatch.setattr(blender, "PLACES", ())
    with pytest.raises(blender.BlenderError, match="3.0 or later"):
        window.export_blender(str(tmp_path / "x.blend"), calculation="c2")
