"""The remote API over a Session without a window (remote/api.py): what a
client or the MCP bridge gets for each method."""
import base64
import math

import numpy as np
import pytest

from guiqula.remote.api import METHODS, RemoteAPI, jsonable, thinned
from guiqula.remote.server import INVALID_PARAMS, NO_METHOD, RemoteError, resolve
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


def test_console_and_journal(api):
    reply = call(api, "console", code="print(h.intra.shape)\n2 + 3", timeout=300)
    assert reply["status"] == "done" and "(16, 16)" in "\n".join(reply["output"])
    journal = call(api, "journal", limit=5)
    assert journal["commands"] and "log" not in journal


def test_the_window_methods_need_a_window(api):
    for method in ("screenshot", "widgets"):
        with pytest.raises(RemoteError) as error:
            call(api, method)
        assert "window" in error.value.message


def test_jsonable_and_thinned():
    assert jsonable({"a": np.array([1.0, np.nan, np.inf]), 2: (np.int64(3), 1j)}) == \
        {"a": [1.0, None, None], "2": [3, [0.0, 1.0]]}
    assert jsonable(object()).startswith("<object")
    values, step = thinned(np.zeros((1000, 4)), 400)
    assert step == 10 and values.shape == (100, 4)
    values, step = thinned(np.zeros(10), 400)
    assert step == 1 and values.shape == (10,)
    assert math.isfinite(jsonable(np.float32(1.5)))
