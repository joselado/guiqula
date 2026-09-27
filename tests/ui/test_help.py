"""The Help dock (decision 13.13; PLAN.md phase 5, part 4): F1 and a form's
? show the selected entry's help, drawn with its equations; links open
sections, Back returns; the guides' contents; guiqula's guide lists the
shortcuts of the table."""
import re

import pytest
from PySide6.QtCore import QUrl

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


def test_f1_shows_the_help_of_the_selected_entry(window, qtbot, shot):
    panel, dock = window.help_panel, window.docks["helpDock"]
    window.select("t1")
    action = window.findChild(type(window.undo_action), "helpAction")
    action.trigger()
    assert dock.isVisible() and panel.title.text() == "Zeeman / exchange field"
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
    form.help_button.click()
    assert panel.title.text() == "Band structure" and "h.get_bands" in panel.browser.toPlainText()
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
