"""The start page (PLAN.md phase 8, package P1): the empty program shows the
lattices, the presets and the recent files as cards in place of the
viewport; a card adds a system or opens a preset, the filter narrows every
band, and the pictures are PNG files that tools/make_thumbnails.py made."""
import struct

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QPalette
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QAbstractButton, QLabel, QLineEdit, QToolButton

from guiqula.io import project
from guiqula.registry import base as registry
from guiqula.ui import start, theme
from guiqula.ui.app import build_main_window
from guiqula.ui.mainwindow import CLASSICAL_STARTS


def png_size(path):
    """(width, height) from a PNG file's header."""
    data = path.read_bytes()[:24]
    assert data[:8] == b"\x89PNG\r\n\x1a\n", path
    return struct.unpack(">II", data[16:24])


@pytest.fixture(scope="module")
def window(qapp):
    window = build_main_window()
    window.resize(1200, 800)
    window.show()
    window.start_session(None, warm=False)
    yield window
    window.close()


@pytest.fixture
def empty(window, qtbot):
    """The window on an empty document, the filter cleared."""
    window.session.act("new")
    window.start_page.filter("")
    for band in window.start_page.bands():
        band.set_expanded(False)
    qtbot.waitUntil(lambda: window.start_page.isVisible(), timeout=5000)
    return window


def test_every_lattice_and_preset_has_a_picture():
    """A lattice, a classical system or a preset added without running
    tools/make_thumbnails.py fails here."""
    wanted = [("lattice", spec.kind) for spec in registry.entries("lattice")] \
        + [("classical", kind) for kind in CLASSICAL_STARTS] \
        + [("preset", name) for name in project.presets()]
    missing = [f"{kind} {name}" for kind, name in wanted if start.thumbnail(kind, name) is None]
    assert not missing, f"no picture (run tools/make_thumbnails.py): {missing}"
    for kind, name in wanted:
        path = start.thumbnail(kind, name)
        assert png_size(path) == (160, 120), path
        assert path.stat().st_size < 20_000, path
    shipped = {(folder, p.stem) for folder in start.FOLDERS.values()
               for p in (start.THUMBNAILS / folder).glob("*.png")}
    assert shipped == {(start.FOLDERS[kind], name) for kind, name in wanted}, \
        "a picture of something that is gone"


TOOL = """
import importlib.util, json, os, shutil, sys
os.environ.pop("GUIQULA_NO_PLUGINS", None)
spec = importlib.util.spec_from_file_location("make_thumbnails", sys.argv[1])
tool = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tool)
scratch = tool.environment()
before = "guiqula" in sys.modules
from guiqula.registry import plugins
print(json.dumps({"off": plugins.disabled(), "cwd": os.getcwd() == scratch,
                  "data": os.environ["GUIQULA_DATA_DIR"].startswith(scratch),
                  "config": os.environ["GUIQULA_CONFIG_DIR"].startswith(scratch),
                  "guiqula_before": before}))
os.chdir("/")
shutil.rmtree(scratch)
"""


def test_the_thumbnail_tool_draws_without_plugins(run_python, repo):
    """tools/make_thumbnails.py turns the plugins off before guiqula is
    imported, so that a plugin's lattice never lands among the shipped
    pictures (test_every_lattice_and_preset_has_a_picture would fail)."""
    import json
    tool = repo / "tools" / "make_thumbnails.py"
    result = run_python(TOOL.replace("sys.argv[1]", repr(str(tool))),
                        env_update={"GUIQULA_NO_PLUGINS": ""})
    assert result.returncode == 0, result.stderr
    out = json.loads(result.stdout.strip().splitlines()[-1])
    assert out == {"off": True, "cwd": True, "data": True, "config": True,
                   "guiqula_before": False}


def test_the_first_sentence_of_every_preset():
    for info in start.presets():
        sentence = info["sentence"]
        assert sentence and info["description"].startswith(sentence), info["name"]
        assert sentence.endswith((".", ")")) and len(sentence) < len(info["description"]) \
            or sentence == info["description"], info["name"]
        assert info["title"] and "\n" not in info["title"], info["name"]
    assert start.first_sentence("Above U of about 2.2 the gap opens. Then more.") == \
        "Above U of about 2.2 the gap opens."
    teaching = [i["name"] for i in start.presets() if i["teaching"]]
    assert set(teaching) == {"graphene_basics", "ssh_chain"}
    assert [i["name"] for i in start.presets()][:len(teaching)] == teaching   # first


def test_the_window_without_a_session_shows_the_page(qtbot, shot):
    window = build_main_window()
    qtbot.addWidget(window)
    window.resize(1200, 800)
    window.show()
    qtbot.waitExposed(window)
    page = window.start_page
    assert window.central_stack.objectName() == "centralStack"
    assert window.central_stack.currentWidget() is page and page.objectName() == "startPage"
    assert page.isVisible() and not window.viewport.isVisible()
    # the pictures are read after the first paint, those in sight first
    dimer, kagome = page.card("lattice", "dimer"), page.card("lattice", "kagome_lattice")
    qtbot.waitUntil(lambda: dimer.picture is not None, timeout=5000)
    assert dimer.isVisible() and kagome.isHidden() and kagome.picture is None
    page.lattices.more.click()                         # in sight: read now
    assert kagome.isVisible() and kagome.picture is not None and not kagome.picture.isNull()
    page.lattices.more.click()
    page.card("lattice", "honeycomb_lattice").click()   # no session: nothing happens
    page.card("preset", "haldane_chern").click()
    assert window.session is None and window.central_stack.currentWidget() is page
    window.new_document()                               # File > New: the page, no error
    assert window.central_stack.currentWidget() is page
    assert window.log.toPlainText() == "" and not window.error_bar.isVisible()
    shot(window, "start_without_session")


def test_the_page_comes_and_goes_with_the_systems(empty, qtbot, shot):
    window = empty
    page, stack = window.start_page, window.central_stack
    assert stack.currentWidget() is page
    shot(window, "start")
    page.card("lattice", "kagome_lattice").click()
    assert stack.currentWidget() is window.viewport and not page.isVisible()
    assert [s.geometry.base.kind for s in window.session.document.systems] == \
        ["kagome_lattice"]
    window.undo()                                        # no system again
    assert stack.currentWidget() is page
    window.redo()
    assert stack.currentWidget() is window.viewport
    window.new_document()                                # File > New
    assert stack.currentWidget() is page and not window.session.document.systems
    page.card("classical", "ising").click()
    system = window.session.document.systems[0]
    assert system.kind == "ising" and stack.currentWidget() is window.viewport
    window.new_document()
    page.card("preset", "haldane_chern").click()
    assert window.session.document.notes.startswith("Chern insulator (Haldane model)")
    assert stack.currentWidget() is window.viewport
    window.new_document()
    assert stack.currentWidget() is page
    QTest.keyClick(page.card("lattice", "dimer"), Qt.Key.Key_Return)    # Enter clicks a card
    assert [s.geometry.base.kind for s in window.session.document.systems] == ["dimer"]
    window.new_document()


def test_the_filter_narrows_every_band(empty):
    page = empty.start_page
    folded = page.visible_cards()
    lattices = [n for n in folded if n.startswith("startLattice_")]
    presets = [n for n in folded if n.startswith("startPreset_")]
    assert lattices and presets                          # one row of each, folded
    assert len(lattices) < len(registry.entries("lattice"))
    assert page.lattices.more.isVisible() and page.lattices.more.text().startswith("Show all")
    shown = page.filter("kagome")
    assert "startLattice_kagome_lattice" in shown and "startLattice_kagome_ribbon" in shown
    assert "startPreset_kagome_flat_band" in shown
    assert "startLattice_honeycomb_lattice" not in shown and \
        "startPreset_haldane_chern" not in shown
    assert page.search.text() == "kagome" and not page.lattices.more.isVisible()
    assert page.lattices.headings["2D"].isVisible() and \
        not page.lattices.headings["3D"].isVisible()     # the groups that have a match
    shown = page.filter("2d honeycomb")                  # every word, the group too
    assert shown and all(n.startswith("startLattice_honeycomb") or
                         n.startswith("startLattice_buckled") for n in shown)
    assert page.filter("graphene") and "startPreset_graphene_basics" in page.visible_cards()
    assert page.filter("nothing at all like this") == []
    assert page.lattices.empty.isVisible() and page.presets.empty.isVisible()
    page.search.clear()                                  # the user's typing filters too
    assert page.visible_cards() == folded
    assert empty.session.act("start", search="majorana") == ["startPreset_majorana_wire"]
    page.filter("")


def test_show_all_and_the_groups(empty):
    page = empty.start_page
    band = page.lattices
    band.more.click()
    every = [n for n in page.visible_cards() if n.startswith(("startLattice_", "startClassical"))]
    assert len(every) == len(registry.entries("lattice")) + len(CLASSICAL_STARTS)
    assert all(h.isVisible() for h in band.headings.values())
    assert list(band.headings) == ["0D", "1D", "2D", "3D", "Layered", "Classical"]
    assert band.more.text() == "Show fewer"
    # the cards of a group come after its heading, in the New system menu's order
    order = [spec.kind for spec in start.grouped("lattice")]
    assert [c.name for c in band.cards if c.kind == "lattice"] == order
    band.more.click()
    assert len([n for n in page.visible_cards() if n.startswith("startLattice_")]) < len(order)
    assert not any(h.isVisible() for h in band.headings.values())


def test_recent_files(empty, tmp_path, qtbot):
    page = empty.start_page
    saved = tmp_path / "work.guiqula"
    empty.session.act("save", path=str(saved))
    page.set_recent([str(saved), str(tmp_path / "gone.guiqula")])
    assert [r.objectName() for r in page.recent.cards] == ["startRecent_0", "startRecent_1"]
    assert page.card("recent", 0).isEnabled() and not page.card("recent", 1).isEnabled()
    assert "gone" in page.card("recent", 1).toolTip()
    assert page.filter("work") == ["startRecent_0"]
    assert page.filter("nothing like these") == [] and page.recent.empty.isVisible()
    assert page.recent.empty.text() == "No recent file matches the filter."   # not "will be listed"
    page.filter("")
    assert not page.recent.empty.isVisible()
    opened = []
    page.recent_chosen.connect(opened.append)
    page.card("recent", 0).click()
    assert opened == [str(saved)] and empty.session.path == saved
    page.recent_chosen.disconnect()
    page.set_recent([])
    assert page.recent.empty.isVisible() and page.findChild(QToolButton, "startOpenButton")
    assert page.recent.empty.text() == "Projects you save or open will be listed here."
    assert page.filter("work") == [] and \
        page.recent.empty.text() == "Projects you save or open will be listed here."
    page.filter("")


def test_the_guide_link_opens_the_help(empty):
    empty.start_page.footer.linkActivated.emit("guide")
    assert empty.docks["helpDock"].isVisible()
    assert empty.help_panel.page[:2] == ("contents", "guiqula")
    assert "F5" in empty.start_page.footer.text() and "F1" in empty.start_page.footer.text()


def test_every_control_of_the_page_has_a_tooltip(empty):
    page = empty.start_page
    controls = page.findChildren(QAbstractButton) + page.findChildren(QLineEdit)
    missing = [c.objectName() for c in controls       # but the filter's own clear button
               if not c.objectName().startswith("qt_") and not c.toolTip()
               and not isinstance(c.parent(), QLineEdit)]
    assert not missing
    assert "Ctrl+O" in page.findChild(QToolButton, "startOpenButton").toolTip()
    assert page.findChild(QLabel, "startFooter").toolTip()


def test_the_cards_follow_the_theme(empty, qtbot):
    card = empty.start_page.card("lattice", "dimer")

    def pixel():
        image = card.grab().toImage()
        return image.pixelColor(card.width() // 2, card.height() - 4).name()

    try:
        empty.set_theme("light")
        light = pixel()
        empty.set_theme("dark")
        dark = pixel()
    finally:
        empty.set_theme("light")
    assert light == theme.PALETTES["light"][QPalette.ColorRole.Base]
    assert dark == theme.PALETTES["dark"][QPalette.ColorRole.Base]


def test_the_headings_follow_the_interface_text(empty):
    band = empty.start_page.lattices
    heights = []
    try:
        for size in ("large", "normal"):
            empty.set_ui_text(size, remember=False)
            points = band.font().pointSizeF()
            title = band.heading.title_font()
            assert title.pointSizeF() == points + 2 and title.bold()
            assert band.headings["2D"].title_font().pointSizeF() == points
            heights.append(band.heading.sizeHint().height())
    finally:
        empty.set_ui_text("normal", remember=False)
    assert heights[0] > heights[1]


def test_the_gallery_is_made_of_the_same_cards(empty, qtbot):
    gallery = empty.show_gallery()
    card = gallery.cards["haldane_chern"]
    assert isinstance(card, start.Card) and card.objectName() == "galleryPreset_haldane_chern"
    assert card.picture is not None and not card.picture.isNull()
    assert card.isCheckable() and card.toolTip() == \
        empty.start_page.card("preset", "haldane_chern").toolTip()
    QTest.mouseDClick(card, Qt.MouseButton.LeftButton)        # a double click opens it
    assert empty.session.document.notes.startswith("Chern insulator")
    assert not gallery.isVisible()
    assert empty.central_stack.currentWidget() is empty.viewport


def test_the_cards_are_made_as_they_come_into_sight(qapp):
    """At start a band makes only the cards of its first row (package P8: the
    start budget of tests/ui/test_startup.py), in their places among the
    headings; Show all, the filter or a card asked for by name make the
    others, and a resize to a wider row makes the ones it shows."""
    window = build_main_window()
    window.resize(1200, 800)
    window.show()
    qapp.processEvents()
    try:
        page = window.start_page
        lattices = page.lattices
        shown = lattices.shown()
        assert 0 < len(lattices.made()) <= shown + 1 < len(lattices.slots)
        assert [c.objectName() for c in lattices.made()] == \
            [f"startLattice_{s.name}" for s in lattices.slots[:len(lattices.made())]]
        assert len(page.presets.made()) < len(page.presets.slots)
        window.resize(1600, 1000)                  # a wider row: its cards are made
        qapp.processEvents()
        assert len([c for c in lattices.made() if not c.isHidden()]) == lattices.shown() > shown
        card = page.card("lattice", "kagome_lattice")        # by name: made, in its place
        order = [item.widget() for item in lattices.flow.items]
        assert order.index(lattices.headings["2D"]) < order.index(card) < \
            order.index(lattices.headings["3D"])
        lattices.more.click()                                 # Show all: every card
        assert len(lattices.made()) == len(lattices.slots)
        assert [c.name for c in lattices.made()] == [s.name for s in lattices.slots]
    finally:
        window.close()
