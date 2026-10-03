"""Remote control of the window (PLAN.md 3.7): the server polled by the
window's timer, a client in another thread (as guiqula mcp would be, in
another process), screenshots, the window's own actions, the switch and its
setting."""
import base64
import threading

import pytest
from PySide6.QtGui import QImage

from guiqula.io import settings
from guiqula.remote import connection
from guiqula.remote.api import WINDOW_ACTIONS
from guiqula.remote.client import connect
from guiqula.remote.server import RemoteError
from guiqula.session import ACTIONS
from guiqula.ui.app import build_main_window


@pytest.fixture(scope="module")
def window(qapp):
    window = build_main_window()
    window.resize(1100, 750)
    window.show()
    window.start_session("honeycomb_zeeman_rashba", warm=False)
    yield window
    window.close()


def remote(qtbot, call, timeout=300_000):
    """Run call(client) in a thread while the window's event loop runs;
    returns its value (or raises what it raised)."""
    out = {}

    def work():
        try:
            with connect() as client:
                out["value"] = call(client)
        except Exception as error:          # re-raised in the test's thread
            out["error"] = error
    thread = threading.Thread(target=work)
    thread.start()
    qtbot.waitUntil(lambda: not thread.is_alive(), timeout=timeout)
    if "error" in out:
        raise out["error"]
    return out["value"]


def test_the_switch(window, qtbot):
    assert window.remote is None and not window.remote_action.isChecked()
    port = window.session.act("remote", enabled=True)
    assert window.remote.port == port and window.remote_action.isChecked()
    assert window.remote_label.text() == f"remote :{port}"
    found = connection.find()
    assert found["port"] == port and found["window"] is True


def test_status_and_screenshots(window, qtbot, shot):
    qtbot.waitUntil(lambda: "s1" in window.builds, timeout=120_000)
    status = remote(qtbot, lambda c: c.call("status"))
    assert status["window"]["workspace"] == "geometry"
    assert status["systems"][0]["build"]["sites"] == 8
    image = remote(qtbot, lambda c: c.call("screenshot"))
    picture = QImage.fromData(base64.b64decode(image["png"]), "PNG")
    assert [picture.width(), picture.height()] == image["size"] == [1100, 750]
    canvas = remote(qtbot, lambda c: c.call("screenshot", widget="structureView"))
    assert canvas["widget"] == "structureView" and canvas["size"][0] < 1100
    names = remote(qtbot, lambda c: c.call("widgets"))
    assert any(line.strip().startswith("structureView") for line in names)
    with pytest.raises(RemoteError):
        remote(qtbot, lambda c: c.call("screenshot", widget="nonsense"))
    shot(window, "driven")


def test_commands_reach_the_window(window, qtbot):
    reply = remote(qtbot, lambda c: c.call("do", command="add_term", args={
        "system": "s1", "kind": "haldane", "params": {"t": 0.05}}))
    term = reply["result"]
    assert reply["systems"]["s1"]["build"]["current"]         # the window rebuilt it
    assert window.outliner.item(term) is not None
    remote(qtbot, lambda c: c.call("do", command="select", args={"entry": term}))
    assert window.selected == term
    remote(qtbot, lambda c: c.call("do", command="workspace", args={"name": "hamiltonian"}))
    assert window.workspace == "hamiltonian"
    with pytest.raises(RemoteError) as error:                 # a window action's ValueError
        remote(qtbot, lambda c: c.call("do", command="canvas_view", args={"name": "nonsense"}))
    assert error.value.code == -32000
    remote(qtbot, lambda c: c.call("do", command="undo"))
    assert window.outliner.item(term) is None


def test_a_run_shows_in_the_window(window, qtbot):
    reply = remote(qtbot, lambda c: c.call("run", calculation="c1", timeout=600))
    assert reply["status"] == "done", reply
    qtbot.waitUntil(lambda: "c1" in window.plots and window.plots["c1"].result is not None,
                    timeout=10_000)
    journal = remote(qtbot, lambda c: c.call("journal", limit=50))
    assert journal["log"]
    remote(qtbot, lambda c: c.call("do", command="tool", args={"name": "box"}))


def test_a_console_command_does_not_freeze_the_window(window, qtbot):
    """do console waited for its job inside the window's timer: the window
    froze until the code ended, and no client could interrupt it. The
    reply waits in a Pending now, while the window goes on."""
    out = {}

    def sleeping():
        with connect() as client:
            out.update(client.call("do", command="console",
                                   args={"code": "import time\ntime.sleep(30)"}, timeout=120))
    thread = threading.Thread(target=sleeping, daemon=True)
    thread.start()
    qtbot.waitUntil(lambda: any(j.kind == "console" and j.status == "running"
                                for j in window.session.jobs.jobs.values()), timeout=60_000)
    remote(qtbot, lambda c: c.call("do", command="interrupt_console"))
    qtbot.waitUntil(lambda: not thread.is_alive(), timeout=60_000)
    assert out["result"]["status"] == "cancelled"


def test_window_actions_are_listed(window):
    from guiqula.ui import mainwindow
    registered = set(window.session.dispatcher.actions())
    assert registered - set(ACTIONS) == set(WINDOW_ACTIONS)
    assert set(mainwindow.WINDOW_ACTIONS) == set(WINDOW_ACTIONS)     # the window's own list
    assert len(mainwindow.WINDOW_ACTIONS) == len(set(mainwindow.WINDOW_ACTIONS))


def test_turning_it_off(window, qtbot):
    path = window.remote.file
    assert window.session.act("remote", enabled=False) is None
    assert window.remote is None and not path.exists() and window.remote_label.text() == ""
    with pytest.raises(ConnectionError):
        connect()


def test_the_setting(qapp, qtbot):
    settings.put("remote", True)
    try:
        other = build_main_window(use_settings=True)
        assert other.remote_wanted and other.remote_action.isChecked() and other.remote is None
        other.show()
        other.start_session(warm=False, interactive=False)
        assert other.remote is not None                   # started with its session
        path = other.remote.file
        other.close()
        assert not path.exists()
        assert settings.load()["remote"] is True          # --remote style: not changed
        other = build_main_window(use_settings=True)
        other.set_remote(False)                            # the menu: remembered
        assert settings.load()["remote"] is False
        other.close()
    finally:
        settings.put("remote", False)
