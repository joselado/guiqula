"""Python nodes in the window (PLAN.md 3.1, 13.7): a file with Python code
opens untrusted, with the trust bar, and its nodes are skipped until the
document is trusted; the code editor commits with Apply; a node stuck in
a loop is stopped when the code is changed, and the canvas recovers."""
import time

import pytest
from PySide6.QtWidgets import QPushButton

from guiqula.commands import Dispatcher
from guiqula.io import project
from guiqula.ui.app import build_main_window
from guiqula.ui.forms import CodeEditor


@pytest.fixture(scope="module")
def window(qapp):
    window = build_main_window()
    window.show()
    window.start_session(None, warm=False)
    yield window
    window.close()


def settle(qtbot, window, timeout=120_000):
    session = window.session
    qtbot.waitUntil(lambda: not window.build_timer.isActive() and all(
        session.build_is_current(s.id) or s.id in session.build_errors
        for s in session.document.systems), timeout=timeout)


def status_of(window, entry):
    system = window.session.document.find(entry)[1].id
    build = window.builds[system]
    return next(r for r in build["reports"] if r["id"] == entry)["status"]


def python_file(tmp_path):
    d = Dispatcher()
    s = d.do("add_system", lattice="honeycomb_lattice")
    d.do("add_term", system=s, kind="python", params={"code": "h.add_onsite(0.4)"})
    return project.save(d.document, tmp_path / "with_code.guiqula")


def test_a_file_with_code_opens_untrusted(window, qtbot, tmp_path, shot):
    session = window.session
    session.act("load", path=str(python_file(tmp_path)))
    settle(qtbot, window)
    assert session.trusted is False and window.trust_bar.isVisible()
    assert "(t1)" in window.trust_bar.label.text()
    assert status_of(window, "t1") == "invalid"
    assert not window.trust_action.isChecked()
    shot(window, "untrusted")
    window.trust_bar.findChild(QPushButton, "showCodeButton").click()
    assert window.selected == "t1"
    window.trust_bar.findChild(QPushButton, "trustButton").click()
    assert session.trusted and not window.trust_bar.isVisible() and window.trust_action.isChecked()
    settle(qtbot, window)
    assert status_of(window, "t1") == "ok"
    session.act("load", path="honeycomb_zeeman_rashba")          # a preset: trusted
    assert session.trusted and not window.trust_bar.isVisible()


def test_code_editor_commits_and_refuses(window, qtbot):
    session = window.session
    session.act("new")
    s = session.do("add_system", lattice="honeycomb_lattice")
    t = session.do("add_term", system=s, kind="python")
    window.select(t)
    editor = window.properties.form.editors["code"]
    assert isinstance(editor, CodeEditor)
    editor.text.setPlainText("h.add_onsite(0.1)\n")
    editor.apply.click()
    assert session.document.find(t)[-1].params["code"] == "h.add_onsite(0.1)\n"
    editor = window.properties.form.editors["code"]
    editor.text.setPlainText("h.add_onsite(0.1\n")
    editor.apply.click()
    assert session.document.find(t)[-1].params["code"] == "h.add_onsite(0.1)\n"
    assert "syntax error" in window.log.toPlainText()
    assert "\nh.add_onsite(0.1)" in window.outliner.item(t).toolTip(0)   # after its label
    settle(qtbot, window)
    assert status_of(window, t) == "ok"


def test_a_stuck_node_is_stopped(window, qtbot, shot):
    session = window.session
    session.act("new")
    session.build_patience = 1.0
    s = session.do("add_system", lattice="honeycomb_lattice")
    op = session.do("add_geometry_op", system=s, kind="python", params={
        "code": "import time\nwhile True:\n    time.sleep(0.05)\n"})
    qtbot.waitUntil(lambda: any(j.kind == "build" and j.status == "running"
                                for j in session.jobs.jobs.values()), timeout=60_000)
    time.sleep(1.2)
    session.do("set_param", entry=op, name="code", value="g = g.get_supercell([2, 2, 1])\n")
    settle(qtbot, window)
    assert session.build_is_current(s) and len(window.builds[s]["positions"]) == 8
    assert status_of(window, op) == "ok"
    session.build_patience = 10.0
    shot(window.structure, "recovered")


def test_console_in_the_window(window, qtbot, shot):
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    session = window.session
    session.act("load", path="honeycomb_zeeman_rashba")
    settle(qtbot, window)
    console = window.console
    console.input.setPlainText("len(g.r), h.has_spin")
    QTest.keyClick(console.input, Qt.Key.Key_Return)
    assert console.input.toPlainText() == ""
    qtbot.waitUntil(lambda: "(8, True)" in console.output.toPlainText(), timeout=300_000)
    assert ">>> len(g.r), h.has_spin" in console.output.toPlainText()
    assert console.system_label.text() == "g, h: s1"
    QTest.keyClick(console.input, Qt.Key.Key_Up)                  # the history
    assert console.input.toPlainText() == "len(g.r), h.has_spin"
    console.input.setPlainText("do('rename', entry='s1', name='from the console')")
    console.run_button.click()
    qtbot.waitUntil(lambda: session.document.system("s1").name == "from the console",
                    timeout=60_000)
    assert window.outliner.item("s1").text(0).endswith("from the console")
    # the rename lands while its console job is still ending, and Run stays disabled until
    # it has ended (a click before would do nothing, as it does for a user)
    qtbot.waitUntil(console.run_button.isEnabled, timeout=60_000)
    console.input.setPlainText("1/0")
    console.run_button.click()
    qtbot.waitUntil(lambda: "ZeroDivisionError" in console.output.toPlainText(), timeout=60_000)
    out = session.act("console", code="print('driven')")                # a driver's command
    assert out["output"] == ["driven"]
    qtbot.waitUntil(lambda: "driven" in console.output.toPlainText(), timeout=10_000)
    console.interrupt_button.click()
    assert "starts afresh" in console.output.toPlainText()
    window.docks["consoleDock"].raise_()
    shot(window, "console")
