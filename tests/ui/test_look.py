"""The look (PLAN.md section 7, phase 8, package P8): what the merged
packages left for it. A calculation's Run stays in sight under its form at
1200x800 however many parameters the form has; the bar of the 3D scene takes
two lines there, not four; the fixed-width fonts and the formula images
follow View > Interface text."""
import pytest
from PySide6.QtWidgets import QApplication, QLabel, QPushButton

from guiqula.ui import formulas, pyvista_view, theme
from guiqula.ui.app import build_main_window


@pytest.fixture(scope="module")
def window(qapp):
    window = build_main_window()
    window.resize(1200, 800)
    window.show()
    window.start_session("honeycomb_zeeman_rashba", warm=False)
    yield window
    window.close()
    theme.set_ui_text("normal")
    theme.apply_text(QApplication.instance())


def settle(qtbot, window, timeout=120_000):
    session = window.session
    qtbot.waitUntil(lambda: not window.build_timer.isActive() and all(
        session.build_is_current(s.id) or s.id in session.build_errors
        for s in session.document.systems), timeout=timeout)
    for _ in range(5):
        QApplication.processEvents()
        qtbot.wait(20)


def in_sight(widget, window):
    """Whether a widget is drawn whole inside the window, not scrolled away."""
    region = widget.visibleRegion()
    corner = widget.mapTo(window, widget.rect().bottomRight())
    return not region.isEmpty() and region.boundingRect() == widget.rect() and \
        window.rect().contains(corner)


@pytest.mark.parametrize("kind", ["dos", "surface_spectral_function"])
def test_run_stays_in_sight_under_a_long_form(window, qtbot, kind):
    """The density of states has eight parameters and the surface spectral
    function a long name: at 1200x800 their Run fell below the fold of
    Properties (P4's open item); it is in the panel's footer now, under the
    scrolled form."""
    session = window.session
    calc = session.do("add_calculation", system="s1", kind=kind)
    try:
        settle(qtbot, window)
        window.select(calc)
        settle(qtbot, window)
        panel = window.properties
        button = panel.findChild(QPushButton, "formRun")
        estimate = panel.findChild(QLabel, "formEstimate")
        assert button.parentWidget().parentWidget() is panel.footer
        assert in_sight(button, window) and in_sight(estimate, window)
        assert estimate.text().startswith("estimate: ")
        scroll = panel.verticalScrollBar()           # the form scrolls, its Run does not
        scroll.setValue(scroll.maximum())
        QApplication.processEvents()
        assert in_sight(button, window)
    finally:
        session.do("remove", entry=calc)


def test_the_fixed_fonts_and_the_formulas_follow_the_interface_text(window, qtbot):
    console = window.console
    window.set_log(True)                       # the console, shown: its font is set then
    window.docks["consoleDock"].raise_()
    QApplication.processEvents()
    assert console.output.font().fixedPitch() or "mono" in console.output.font().family().lower()
    sizes, widths = [], []
    try:
        for size in ("normal", "large"):
            window.set_ui_text(size, remember=False)
            QApplication.processEvents()
            sizes.append(console.output.font().pointSizeF())
            assert console.input.font().pointSizeF() == sizes[-1] == \
                console.font().pointSizeF()
            widths.append(formulas.pixmap(r"\sum_i t_i", theme.TEXT).width())
    finally:
        window.set_ui_text("normal", remember=False)
        window.set_log(False)
    assert sizes[1] == sizes[0] + 2 and widths[1] > widths[0] * 1.1


@pytest.mark.skipif(not pyvista_view.available(), reason=pyvista_view.unavailable_reason())
def test_the_bar_of_the_scene_takes_two_lines_at_1200_px(window, qtbot):
    """The View button had the width of its longest name, and the structure
    bar of the 3D scene took four lines at 1200x800; it shows its icon now,
    the view's name leading its tooltip and the line over the scene."""
    session = window.session
    session.act("load", path="honeycomb_hubbard")
    session.act("renderer_3d", name="pyvista")
    try:
        session.act("projection", name="3d")
        settle(qtbot, window)
        structure = window.structure
        assert structure.in_scene
        bar = structure.bar
        assert bar.overflows() == [] and len(bar.lines()) <= 2, bar.lines()
        scene = structure.scene
        assert scene.view_button.text() == "View: User Perspective"
        assert scene.view_button.toolTip().startswith("View: User Perspective")
        assert scene.hint.full.startswith("User Perspective · ")
        session.act("view_3d", name="top")
        assert scene.hint.full.startswith("Top Orthographic · ")
    finally:
        session.act("projection", name="auto")
        session.act("renderer_3d", name="matplotlib")
        session.act("load", path="honeycomb_zeeman_rashba")
        settle(qtbot, window)
