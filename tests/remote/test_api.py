"""The remote API over a Session without a window (remote/api.py): what a
client or the MCP bridge gets for each method."""
import base64
import math
import time

import numpy as np
import pytest

from guiqula.core.results import Result
from guiqula.remote.api import METHODS, RemoteAPI, jsonable, plot_title, thinned
from guiqula.remote.server import INVALID_PARAMS, NO_METHOD, Pending, RemoteError, resolve
from guiqula.commands import CommandError
from guiqula.session import Session


@pytest.fixture(scope="module")
def api():
    with Session("honeycomb_zeeman_rashba", warm=False) as session:
        api = RemoteAPI(session)
        session.build_all()
        yield api
        api.close()


def call(api, method, **params):
    return resolve(api(method, params), api.session.poll)


def test_hello_status_document(api):
    hello = call(api, "hello")
    assert hello["window"] is False and hello["methods"] == list(METHODS)
    status = call(api, "status")
    system = status["systems"][0]
    assert system["id"] == "s1" and system["lattice"] == "honeycomb_lattice"
    assert [t["kind"] for t in system["terms"]] == ["zeeman", "rashba"]
    assert system["mode"] == "spinful"
    assert [c["id"] for c in status["calculations"]] == ["c1", "c2"]
    assert status["window"] is None and status["document"]["trusted"] is True
    document = call(api, "document")
    assert document["systems"][0]["id"] == "s1" and "ui" not in document
    commands = call(api, "commands")
    assert "add_term" in commands["mutations"] and "run_calculation" in commands["actions"]


def test_catalogue(api):
    brief = call(api, "catalogue")
    assert {"family", "kind", "label", "doc"} <= set(brief[0]) and "params" not in brief[0]
    terms = call(api, "catalogue", family="term")
    assert all(t["family"] == "term" for t in terms) and "params" in terms[0]
    haldane = call(api, "catalogue", search="haldane")
    assert any(t["kind"] == "haldane" for t in haldane)
    ising = call(api, "catalogue", system_kind="ising", family="calculation")
    assert ising and all("ising" in t["systems"] for t in ising)
    with pytest.raises(RemoteError) as error:
        call(api, "catalogue", family="nonsense")
    assert error.value.code == INVALID_PARAMS


def test_do_waits_for_the_build(api):
    reply = call(api, "do", command="add_geometry_op",
                 args={"system": "s1", "kind": "supercell", "params": {"n": [2, 1, 1]}})
    op = reply["result"]
    build = reply["systems"]["s1"]["build"]
    assert build["current"] and build["sites"] == 16      # the 2x2 preset doubled along x
    reply = call(api, "do", command="add_term", args={"system": "s1", "kind": "onsite",
                                                      "params": {"mu": "0.1*x"}})
    assert reply["systems"]["s1"]["build"]["current"]
    call(api, "do", command="undo")
    call(api, "do", command="remove", args={"entry": op})
    assert call(api, "status")["systems"][0]["build"]["sites"] == 8
    with pytest.raises(CommandError):
        call(api, "do", command="add_term", args={"system": "s9", "kind": "haldane"})
    with pytest.raises(RemoteError) as error:
        call(api, "nonsense")
    assert error.value.code == NO_METHOD


def test_invalid_entries_are_reported(api):
    """A Python term in a document that is not trusted is skipped (13.7)."""
    call(api, "do", command="trust", args={"enabled": False})
    reply = call(api, "do", command="add_term", args={"system": "s1", "kind": "python"})
    invalid = reply["systems"]["s1"]["invalid"]
    assert invalid[0]["id"] == reply["result"] and "trust" in invalid[0]["problem"]
    call(api, "do", command="undo")
    call(api, "do", command="trust", args={"enabled": True})
    assert "invalid" not in call(api, "status")["systems"][0]


def test_trust_rebuilds_without_a_window(api):
    """Trust changes what is built, as an edit does: the reply of the trust
    action waits for the build the Python op now changes."""
    call(api, "do", command="trust", args={"enabled": False})
    reply = call(api, "do", command="add_geometry_op", args={
        "system": "s1", "kind": "python", "params": {"code": "g = g.get_supercell([2, 1, 1])"}})
    op = reply["result"]
    assert reply["systems"]["s1"]["build"]["sites"] == 8                  # skipped
    build = call(api, "do", command="trust", args={"enabled": True})["systems"]["s1"]["build"]
    assert build["current"] and build["sites"] == 16
    call(api, "do", command="remove", args={"entry": op})


def test_run_result_plot_script(api):
    reply = call(api, "run", calculation="c1", timeout=600)
    assert reply["status"] == "done", reply
    assert reply["result"]["arrays"]["energies"]["shape"][1] == 16
    result = call(api, "result", calculation="c1", arrays=["energies"], max_values=400)
    energies = np.array(result["values"]["energies"])
    full = api.session.result("c1").arrays["energies"]
    step = result["arrays"]["energies"]["every"]
    assert np.allclose(energies, full[::step]) and energies.size <= 400 + 16
    assert "weights" not in result["values"]        # only what is asked for, or tiny
    everything = call(api, "result", calculation="c1", arrays="all", max_values=10**6)
    assert np.allclose(everything["values"]["weights"], api.session.result("c1").arrays["weights"])
    png = base64.b64decode(call(api, "plot", calculation="c1")["png"])
    assert png[:8] == b"\x89PNG\r\n\x1a\n" and len(png) > 10_000
    script = call(api, "script", calculation="c1")
    assert "get_bands" in script and "add_rashba" in script
    with pytest.raises(RemoteError):
        call(api, "result", calculation="c2")        # not run
    with pytest.raises(RemoteError):
        call(api, "result", calculation="c1", arrays=["nonsense"])


def test_a_plot_says_whether_its_result_is_current(api):
    """The figure sent to a client has no tab and no status row above it, so
    its title carries the mark the window shows there (ui/marks.py), and the
    reply the state; a current result reads as the window's title alone."""
    session = api.session
    if session.status("c1") != "done":
        assert call(api, "run", calculation="c1", timeout=600)["status"] == "done"
    result = session.result("c1")
    assert plot_title(session, "c1", result) == ("c1 · bands · spinful", "done")
    assert call(api, "plot", calculation="c1")["state"] == "done"
    call(api, "do", command="set_param", args={"entry": "t1", "name": "m",
                                               "value": [0, 0, 0.35]})
    assert session.is_stale("c1")
    assert plot_title(session, "c1", result) == ("c1 · bands · spinful ↻", "stale")
    reply = call(api, "plot", calculation="c1")
    assert reply["state"] == "stale"
    assert base64.b64decode(reply["png"])[:8] == b"\x89PNG\r\n\x1a\n"
    call(api, "do", command="undo")                 # the earlier result is current again
    assert session.status("c1") == "done"
    assert call(api, "plot", calculation="c1")["state"] == "done"


def test_run_without_waiting_then_wait(api):
    reply = call(api, "run", calculation="c2", wait=False)
    assert reply["job"]["status"] in ("queued", "running")
    reply = call(api, "wait", calculation="c2", timeout=600)
    assert reply["status"] == "done" and "result" in reply
    with pytest.raises(RemoteError):
        call(api, "wait", calculation="c9")


def test_help(api):
    item = call(api, "help", item="t2")
    assert item["title"] == "Rashba spin-orbit coupling" and "## pyqula code" in item["markdown"]
    entry = call(api, "help", kind="haldane")
    assert "add_haldane" in entry["markdown"]
    section = call(api, "help", guide="guiqula", anchor="fields")     # a heading's start
    assert section["title"] == "Fields: parameters that depend on the position"
    assert "piecewise" in section["markdown"]
    with pytest.raises(RemoteError) as error:
        call(api, "help", guide="pyqula", anchor="the")
    assert "several" in error.value.message
    contents = call(api, "help", guide="pyqula")
    assert "help:" in contents["markdown"]
    with pytest.raises(RemoteError):
        call(api, "help", kind="nonsense")
    found = call(api, "help", search="how do I add Rashba spin-orbit coupling", limit=3)
    assert len(found["hits"]) == 3 and found["title"].startswith("Search:")
    assert found["hits"][0]["kind"] == "rashba" and found["hits"][0]["family"] == "term"
    reference = next(h for h in found["hits"] if "anchor" in h)
    assert call(api, "help", guide=reference["guide"], anchor=reference["anchor"])["markdown"]


def test_console_and_journal(api):
    reply = call(api, "console", code="print(h.intra.shape)\n2 + 3", timeout=300)
    assert reply["status"] == "done" and "(16, 16)" in "\n".join(reply["output"])
    assert reply["output"][-1] == "5" and reply["error"] is None
    failed = call(api, "console", code="1/0", timeout=300)
    assert failed["error"] == "ZeroDivisionError: division by zero"
    assert "Traceback" in failed["output"][0]
    journal = call(api, "journal", limit=5)
    assert journal["commands"] and "log" not in journal


def running_console(api, timeout=120):
    deadline = time.monotonic() + timeout
    while not any(j.kind == "console" and j.status == "running"
                  for j in api.session.jobs.jobs.values()):
        assert time.monotonic() < deadline, "the console never started"
        api.session.poll(0.05)


def test_waiting_commands_do_not_hold_up_the_host(api):
    """do of an action that waits for its job (the console, run_calculation
    with wait) replies through a Pending: waiting inside the action held up
    guiqula serve and the window, so no other client got an answer, not
    even one sending interrupt_console."""
    started = time.monotonic()
    pending = api("do", {"command": "console", "args": {"code": "import time\ntime.sleep(30)"}})
    assert isinstance(pending, Pending) and time.monotonic() - started < 10
    running_console(api)
    call(api, "do", command="interrupt_console")         # served meanwhile
    assert resolve(pending, api.session.poll)["result"]["status"] == "cancelled"
    reply = call(api, "do", command="console", args={"code": "import time\ntime.sleep(30)"},
                 timeout=0.5)                             # the reply comes when its time is up
    assert reply["result"]["status"] in ("queued", "running") and "still" in reply["note"]
    call(api, "do", command="interrupt_console")
    reply = call(api, "do", command="run_calculation", args={"calculation": "c2", "wait": True},
                 timeout=600)
    assert reply["result"]["status"] == "done" and api.session.status("c2") == "done"


def test_the_window_methods_need_a_window(api):
    for method in ("screenshot", "widgets"):
        with pytest.raises(RemoteError) as error:
            call(api, method)
        assert "window" in error.value.message


def test_a_result_that_a_field_reads_rebuilds_without_a_window(api):
    """texture_exchange: s2's Zeeman field reads c1's magnetization (a
    from_result Field). Once c1's result lands, s2 is built again, as the
    window does: its build stayed out of date until the next edit."""
    call(api, "do", command="load", args={"path": "texture_exchange"})
    try:
        assert call(api, "status")["systems"][1]["build"]["current"]
        assert call(api, "run", calculation="c1", timeout=900)["status"] == "done"
        resolve(Pending(api.settled, lambda timed_out: timed_out, 300), api.session.poll)
        s2 = call(api, "status")["systems"][1]
        assert s2["build"]["current"] and "invalid" not in s2, s2
    finally:
        call(api, "do", command="load", args={"path": "honeycomb_zeeman_rashba"})


def test_bad_numbers_are_refused_before_anything_is_done(no_jobs):
    """A timeout that is not a number of seconds, or max_values below 1, is
    refused as invalid parameters before the command runs: the command was
    applied first (a client retrying after the error added the term twice),
    0 values divided by zero and a negative number reversed the rows."""
    no_jobs.workers, no_jobs.jobs = {}, {}
    session = Session("honeycomb_zeeman_rashba", jobs=no_jobs)
    api = RemoteAPI(session)
    for timeout in ("soon", None, -1.0, math.nan):
        with pytest.raises(RemoteError) as error:
            api("do", {"command": "add_term", "args": {"system": "s1", "kind": "onsite"},
                       "timeout": timeout})
        assert error.value.code == INVALID_PARAMS
    with pytest.raises(RemoteError) as error:
        api("do", {"command": "console", "args": {"code": "1", "timeout": "soon"}})
    assert error.value.code == INVALID_PARAMS
    assert len(session.document.system("s1").hamiltonian.terms) == 2
    assert session.dispatcher.history()["undo"] == []
    energies = np.arange(100.0).reshape(50, 2)
    session.results["c1"] = Result("c1", "bands", session.calculation_key("c1"), {},
                                   {"energies": energies}, {"kind": "lines"})
    for max_values in (0, -10, "many"):
        with pytest.raises(RemoteError) as error:
            api("result", {"calculation": "c1", "arrays": ["energies"], "max_values": max_values})
        assert error.value.code == INVALID_PARAMS
    values = api("result", {"calculation": "c1", "arrays": ["energies"], "max_values": 10})
    assert values["values"]["energies"][:2] == [[0.0, 1.0], [20.0, 21.0]]
    api.close()
    session.close()


def test_jsonable_and_thinned():
    assert jsonable({"a": np.array([1.0, np.nan, np.inf]), 2: (np.int64(3), 1j)}) == \
        {"a": [1.0, None, None], "2": [3, [0.0, 1.0]]}
    assert jsonable(object()).startswith("<object")
    values, step = thinned(np.zeros((1000, 4)), 400)
    assert step == 10 and values.shape == (100, 4)
    values, step = thinned(np.zeros(10), 400)
    assert step == 1 and values.shape == (10,)
    assert math.isfinite(jsonable(np.float32(1.5)))
