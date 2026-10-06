"""The Help dock (decision 13.13; PLAN.md phase 5, part 4): F1 and a form's
? show the selected entry's help, drawn with its equations; links open
sections, Back returns; the guides' contents; guiqula's guide lists the
shortcuts of the table."""
import re

import pytest
from PySide6.QtCore import Qt, QUrl

from guiqula.docs import entries
from guiqula.docs.guide import math_images
from guiqula.ui import formulas, shortcuts
from guiqula.ui.app import build_main_window


@pytest.fixture(scope="module")
def window(qapp):
    window = build_main_window()
    window.resize(1400, 900)
    window.show()
    window.start_session("honeycomb_zeeman_rashba", warm=False)
    yield window
    window.close()


def images(browser):
    return re.findall(r'<img src="formula:\d+"', browser.document().toHtml())


def in_front(window, name):
    """Shown, and in front of the tabs it shares."""
    dock = window.docks[name]
    return not dock.isHidden() and not dock.visibleRegion().isEmpty()


def test_f1_shows_the_help_of_the_selected_entry(window, qtbot, shot):
    panel, dock = window.help_panel, window.docks["helpDock"]
    window.select("t1")
    action = window.findChild(type(window.undo_action), "helpAction")
    action.trigger()
    assert dock.isVisible() and panel.title.text() == "Zeeman / exchange field"
    assert in_front(window, "helpDock") and in_front(window, "propertiesDock")
    assert window.properties.form.isVisible()                       # the form it explains
    text = panel.browser.toPlainText()
    assert "Adds zeeman to the matrix" in text                     # pyqula's docstring
    assert "Including an external Zeeman field" in text           # pyqula's guide
    assert "h.add_zeeman([0.0, 0.0, lambda r: 0.3 * np.tanh(r[0] / 4)])" in text   # its values
    assert len(images(panel.browser)) >= 5                         # the equations, drawn
    image = panel.browser.loadResource(2, QUrl("formula:0"))
    assert image is not None and image.width() > 10
    shot(dock, "zeeman_help")
    window.select("t2")                                            # the dock follows
    assert panel.title.text() == "Rashba spin-orbit coupling"
    panel.browser.anchorClicked.emit(QUrl("help:pyqula/Density%20of%20states"))
    assert panel.page == ("section", "pyqula", "Density of states")
    assert panel.browser.toPlainText().startswith("Density of states")
    window.select("t1")                                            # a section stays
    assert panel.page[0] == "section"
    panel.go_back()
    assert panel.page == ("item", "t2") and not panel.back.isEnabled()


def test_the_guides_and_the_question_mark(window, qtbot):
    panel = window.help_panel
    assert window.help(guide="guiqula") == "guiqula user guide"
    assert "Fields: parameters that depend on the position" in panel.browser.toPlainText()
    assert window.help(guide="pyqula", anchor="Chern number") == "Chern number"
    with pytest.raises(ValueError):
        window.help(guide="nope")
    window.select("c1")
    form = window.properties.form
    window.docks["jobsDock"].raise_()
    form.help_button.click()
    assert panel.title.text() == "Band structure" and "h.get_bands" in panel.browser.toPlainText()
    assert in_front(window, "helpDock") and in_front(window, "propertiesDock")
    assert window.properties.form is form and form.isVisible()
    window.select("s1/regions")
    assert window.help() == "Selections and regions"
    window.select("s1")
    assert window.help() == "Systems and geometry"
    window.select("")
    assert window.help() == "guiqula"


def test_the_guide_lists_the_shortcuts_of_the_table():
    text = entries.GUIQULA_GUIDE.read_text()
    assert shortcuts.markdown_table() in text


def test_mathtext_draws_most_of_the_guides_equations():
    """What mathtext cannot draw is shown as its source (matrices, aligned
    environments): measured over the whole of pyqula's guide."""
    guide = entries.pyqula_guide()
    _, equations = math_images("\n".join(guide.lines))
    failed = []
    for tex in equations:
        try:
            formulas.png(tex)
        except formulas.FormulaError:
            failed.append(tex)
    assert len(equations) > 900
    assert len(failed) / len(equations) < 0.03, failed[:10]


def test_the_help_follows_a_change_of_theme(window, qtbot):
    """The equations are drawn in the text colour of the theme."""
    from guiqula.ui import theme
    panel = window.help_panel

    def ink(image):          # the mean lightness of the drawn (opaque) pixels
        values = [image.pixelColor(x, y).lightness() for x in range(image.width())
                  for y in range(image.height()) if image.pixelColor(x, y).alpha() > 200]
        return sum(values) / len(values)
    window.select("t1")
    window.show_help()
    before = ink(panel.browser.loadResource(2, QUrl("formula:0")))
    window.set_theme("dark")
    try:
        assert panel.page == ("item", "t1")
        assert ink(panel.browser.loadResource(2, QUrl("formula:0"))) > before + 100
    finally:
        window.set_theme("light")
    assert theme.name == "light"


def test_the_plugins_page(window, qtbot):
    panel = window.help_panel
    window.help("t1")
    action = window.findChild(type(window.undo_action), "pluginsAction")
    action.trigger()
    assert panel.title.text() == "Plugins" and panel.page == ("plugins",)
    assert "Plugins are off in this run" in panel.browser.toPlainText()    # the test suite's
    window.set_theme("dark")                                    # drawn again in the new colours
    assert panel.page == ("plugins",)
    window.set_theme("light")
    panel.go_back()
    assert panel.page == ("item", "t1")


def test_code_wraps_at_the_width_of_the_panel(window, qtbot):
    """A line of code longer than the panel wraps, as the prose does, so the
    page has no horizontal scroll bar (t1's help shows pyqula's example of
    add_zeeman, whose comment made it about 560 px wide)."""
    browser = window.help_panel.browser
    window.help("t1")
    window.docks["helpDock"].raise_()
    qtbot.wait(50)
    block, wide = browser.document().begin(), []
    while block.isValid():
        wide.append(block.blockFormat().nonBreakableLines())
        block = block.next()
    assert "# add the Zeeman field (modifies h in place)" in browser.toPlainText()
    assert not any(wide)
    assert browser.horizontalScrollBar().maximum() == 0


def test_a_wide_equation_is_scaled_to_the_panel(window, qtbot):
    """A displayed equation wider than the panel is drawn at the panel's
    width, its height in proportion, so the section does not scroll
    sideways; the long section name wraps instead of widening the column."""
    panel = window.help_panel
    browser = panel.browser
    window.docks["helpDock"].raise_()
    width = window.docks["helpDock"].width()
    panel.show_section("pyqula", "The screened interaction")
    qtbot.wait(50)
    scaled = []
    block = browser.document().begin()
    while block.isValid():
        fragments = block.begin()
        while not fragments.atEnd():
            look = fragments.fragment().charFormat()
            if look.isImageFormat() and look.toImageFormat().width() > 0:
                image = look.toImageFormat()
                natural = browser._natural_size(image.name())
                scaled.append((image.width(), natural.width(), image.height(),
                               natural.height()))
            fragments += 1
        block = block.next()
    assert scaled, "no equation of that section is wider than the panel"
    for shown, natural, high, natural_high in scaled:
        assert shown < natural and shown <= browser.viewport().width()
        assert abs(high / natural_high - shown / natural) < 0.01
    assert browser.horizontalScrollBar().maximum() == 0
    panel.show_section("pyqula", "Abrikosov-pseudofermion (Read-Newns) mean field for the "
                       "Kondo lattice")                   # a long name: it wraps
    qtbot.wait(50)
    assert window.docks["helpDock"].width() == width


def test_the_search_line_lists_what_answers_a_question(window, qtbot, shot):
    """The Help panel's search line (decision 159): Enter lists the entries
    and sections, a link opens one, Back returns to the list; Shift+F1 puts
    the focus in the line, and the help action searches too."""
    panel = window.help_panel
    action = window.findChild(type(window.undo_action), "helpSearchAction")
    assert action.shortcut().toString() == "Shift+F1"
    action.trigger()
    assert in_front(window, "helpDock") and panel.search.hasFocus()
    qtbot.keyClicks(panel.search, "rashba spin orbit")
    qtbot.keyClick(panel.search, Qt.Key.Key_Return)
    assert panel.page == ("search", "rashba spin orbit")
    assert panel.title.text() == "Search: rashba spin orbit"
    text = panel.browser.toPlainText()
    assert text.index("Rashba spin-orbit coupling") < text.index("h.add_rashba()")
    shot(window.docks["helpDock"], "search")
    panel.browser.anchorClicked.emit(QUrl("help:entry/term%3Arashba"))
    assert panel.page == ("entry", "term", "rashba")
    assert panel.title.text() == "Rashba spin-orbit coupling" and "add_rashba" in \
        panel.browser.toPlainText()
    window.set_theme("dark")                                    # drawn again, the same page
    assert panel.page == ("entry", "term", "rashba")
    window.set_theme("light")
    panel.go_back()
    assert panel.page == ("search", "rashba spin orbit")
    panel.browser.anchorClicked.emit(QUrl("help:pyqula/"))         # a guide's contents
    assert panel.page == ("contents", "pyqula")
    assert window._act("help", search="kane mele") == "Search: kane mele"
    assert panel.search.text() == "kane mele" and "Kane-Mele" in panel.browser.toPlainText()
