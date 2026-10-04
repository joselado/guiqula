"""The window's state as remote control reports it (remote/window.py,
WindowHooks.state, the status method's "window"): whether the start page
stands in the viewport's place, and the calculation Run acts on (PLAN.md
phase 8, packages P1 and P4)."""
import pytest

from guiqula.remote.window import WindowHooks
from guiqula.ui.app import build_main_window


@pytest.fixture(scope="module")
def window(qapp):
    window = build_main_window()
    window.resize(1100, 750)
    window.show()
    yield window
    window.close()


def test_the_state_names_the_start_page_and_what_run_acts_on(window, qtbot):
    hooks = WindowHooks(window)
    state = hooks.state()
    assert state["start_page"] is True and state["selected_calculation"] is None
    window.start_session("honeycomb_zeeman_rashba", warm=False)
    qtbot.waitUntil(lambda: "s1" in window.builds, timeout=120_000)
    state = hooks.state()
    assert state["start_page"] is False and state["tab"] == window.current_tab()
    assert state["selected_calculation"] == window.selected_calculation() == "c1"
    window.select("c2")
    assert hooks.state()["selected_calculation"] == "c2"
    window.select("t1")                     # a term keeps its form, and Run follows the tab
    assert hooks.state()["selected_calculation"] == window.selected_calculation()
    window.new_document()                   # no system: the page comes back
    assert hooks.state()["start_page"] is True
