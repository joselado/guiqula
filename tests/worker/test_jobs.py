"""Worker processes (PLAN.md 3.3; decisions 14.6 and 14.10): jobs run in
a separate, non-daemonic process; cancel, crash and timeout kill only the
worker concerned, which is restarted."""
import os
import sys
import time

import numpy as np
import pytest

from guiqula.io import project
from guiqula.worker.client import JobManager


@pytest.fixture(scope="module")
def manager():
    with JobManager(batch=1, interactive=True, warm=False) as m:
        m.wait_ready(120)
        yield m


def wait_running(manager, job, timeout=60):
    deadline = time.monotonic() + timeout
    while job.status != "running":
        assert time.monotonic() < deadline, f"{job} never started"
        manager.poll(0.02)


def test_workers_are_non_daemonic_processes(manager):
    for worker in manager._all_workers():
        assert worker.process.daemon is False and worker.alive()


def test_run_equals_direct_pyqula(manager, pyqula_direct):
    job = manager.wait(manager.run(project.load("honeycomb_zeeman_rashba").to_json(), "c1"), 300)
    assert job.status == "done", job.error
    result = job.value
    k, e, c = pyqula_direct
    assert np.allclose(result.arrays["energies"], e, rtol=0, atol=1e-12)
    assert np.allclose(result.arrays["weights"], c, rtol=0, atol=1e-12)
    assert result.meta["pyqula"]["origin"] in ("checkout", "override", "vendored")


@pytest.fixture(scope="module")
def pyqula_direct(tmp_path_factory):
    from guiqula import vendoring
    vendoring.ensure_pyqula_on_path()
    cwd = os.getcwd()
    os.chdir(tmp_path_factory.mktemp("direct"))
    try:
        from pyqula import geometry
        h = geometry.honeycomb_lattice().get_supercell([2, 2, 1]).get_hamiltonian(has_spin=True)
        h.add_zeeman([0.0, 0.0, lambda r: 0.3 * np.tanh(r[0] / 4)])
        h.add_rashba(0.1)
        out = h.get_bands(nk=100, operator="sz", write=False)
    finally:
        os.chdir(cwd)
    return out[0], out[1].reshape(100, -1), out[2].reshape(100, -1)


def test_ready_reports_pyqula_names(manager):
    manager.wait_ready(120)
    assert "sz" in manager.names["operators"] and "sublattice" in manager.names["operators"]


def test_build_summary(manager):
    document = project.load("honeycomb_zeeman_rashba").to_json()
    assert manager.wait(manager.build(document, "s1"), 120).value["hamiltonian"] is None
    job = manager.wait(manager.build(document, "s1", view=True), 120)
    assert job.status == "done", job.error
    summary = job.value
    assert summary["mode"] == "spinful" and summary["sites"] == 8 and summary["dimension"] == 16
    assert [r["status"] for r in summary["reports"]] == ["ok"] * 5 + ["disabled"]   # mean field
    assert "sz" in manager.names["operators"] and "random" in manager.names["guesses"]
    view = summary["hamiltonian"]                  # PLAN 13.8: what the terms put on the sites
    assert view["onsite"].shape == (8,) and view["exchange"].shape == (8, 3)
    assert view["hoppings"].shape[1] == 5 and len(view["amplitude"]) == len(view["hoppings"])
    assert view["spin"].max() > 0                  # Rashba mixes the spins


def test_cancel_running_job_restarts_only_that_worker(manager):
    document = project.load("honeycomb_zeeman_rashba").to_json()
    first = manager.wait(manager.build(document, "s1"), 120).value["cache"]
    interactive_pid = manager.workers["interactive"][0].process.pid
    batch = manager.workers["batch"][0]
    old_pid = batch.process.pid
    job = manager.submit("sleep", {"seconds": 30})
    wait_running(manager, job)
    manager.cancel(job)
    assert job.status == "cancelled"
    assert batch.process.pid != old_pid
    # the interactive worker and its build cache survive (review item 8)
    assert manager.workers["interactive"][0].process.pid == interactive_pid
    again = manager.wait(manager.build(document, "s1"), 120).value["cache"]
    assert again["hits"] > first["hits"] and again["misses"] == first["misses"]
    after = manager.wait(manager.submit("sleep", {"seconds": 0.1}), 120)
    assert after.status == "done" and after.value["pid"] == batch.process.pid


def test_cancel_queued_job(manager):
    running = manager.submit("sleep", {"seconds": 1})
    queued = manager.submit("sleep", {"seconds": 1})
    manager.cancel(queued)
    assert queued.status == "cancelled"
    assert manager.wait(running, 60).status == "done"


def test_crash_is_reported_and_the_worker_respawns(manager):
    job = manager.wait(manager.submit("crash", {"code": 7}), 60)
    assert job.status == "failed" and "exit code 7" in job.error
    assert manager.wait(manager.submit("sleep", {"seconds": 0.1}), 120).status == "done"


def test_timeout(manager):
    job = manager.wait(manager.submit("sleep", {"seconds": 20}, timeout=0.5), 60)
    assert job.status == "failed" and "timed out" in job.error


def test_errors_come_back_with_the_message(manager):
    document = project.load("honeycomb_zeeman_rashba")
    document.calculations[0].params["operator"] = "no_such_operator"
    job = manager.wait(manager.run(document.to_json(), "c1"), 120)
    assert job.status == "failed" and "no_such_operator" in job.error and job.traceback


def _group_members(pgid):
    members = []
    for entry in os.listdir("/proc"):
        if entry.isdigit():
            try:
                with open(f"/proc/{entry}/stat") as f:
                    fields = f.read().rsplit(")", 1)[1].split()
            except OSError:
                continue
            if int(fields[2]) == pgid and fields[0] != "Z":
                members.append(int(entry))
    return members


@pytest.mark.skipif(not sys.platform.startswith("linux"), reason="reads /proc")
def test_parallel_pool_runs_and_dies_with_a_cancel():
    """pyqula's own pool starts inside the worker (decision 14.10), gives
    the serial result, and a cancel kills the pool with the worker."""
    from guiqula.commands import Dispatcher
    d = Dispatcher()
    s = d.do("add_system", lattice="honeycomb_lattice")
    d.do("add_term", system=s, kind="rashba")
    small = d.do("add_calculation", system=s, kind="bands", params={"nk": 40, "operator": "sz"})
    d.do("set_lattice", system=s, lattice="honeycomb_lattice")
    big_system = d.do("add_system", lattice="honeycomb_lattice")
    d.do("add_geometry_op", system=big_system, kind="supercell", params={"n": [10, 10, 1]})
    big = d.do("add_calculation", system=big_system, kind="bands",
               params={"nk": 400, "operator": "sz"})
    document = d.document.to_json()
    with JobManager(batch=1, interactive=False, warm=False) as m:
        serial = m.wait(m.run(document, small, cores=1), 300)
        parallel = m.wait(m.run(document, small, cores=2), 300)
        assert parallel.status == "done", parallel.error
        assert parallel.value.meta["cores"] == 2
        assert np.allclose(serial.value.arrays["weights"], parallel.value.arrays["weights"],
                           rtol=0, atol=1e-12)
        job = m.run(document, big, cores=2)
        wait_running(m, job)
        pgid = m.workers["batch"][0].process.pid
        deadline = time.monotonic() + 30
        while len(_group_members(pgid)) < 3:          # worker + two pool processes
            assert time.monotonic() < deadline, _group_members(pgid)
            time.sleep(0.1)
        m.cancel(job)
        deadline = time.monotonic() + 10
        while _group_members(pgid):
            assert time.monotonic() < deadline, f"left behind: {_group_members(pgid)}"
            time.sleep(0.1)


def test_a_job_asks_the_ui_process(manager):
    """REQUEST/REPLY (protocol.py): a job waits for the answer of the UI
    process; a refusal reaches the job as an error; without a handler the
    job fails with that message and the worker stays usable."""
    asked = []

    def handler(job, name, args):
        asked.append((job.id, name, args))
        if name == "refuse":
            raise ValueError("not today")
        return {"echo": args["x"] * 2}
    manager.request_handler = handler
    try:
        job = manager.wait(manager.submit("request", {"name": "double", "args": {"x": 21}}), 60)
        assert job.status == "done" and job.value == {"echo": 42}
        assert asked == [(job.id, "double", {"x": 21})]
        job = manager.wait(manager.submit("request", {"name": "refuse"}), 60)
        assert job.status == "failed" and "not today" in job.error
        manager.request_handler = None
        job = manager.wait(manager.submit("request", {"name": "anything"}), 60)
        assert job.status == "failed" and "nobody answers" in job.error
        job = manager.wait(manager.submit("sleep", {"seconds": 0.05}), 60)
        assert job.status == "done"
    finally:
        manager.request_handler = None


def test_unknown_role_is_refused(manager):
    with pytest.raises(ValueError, match="no 'nope' worker"):
        manager.submit("sleep", {}, role="nope")


def test_finished_jobs_are_forgotten_beyond_a_few(manager, monkeypatch):
    from guiqula.worker import client
    monkeypatch.setattr(client, "FINISHED_KEPT", 3)
    jobs = [manager.submit("sleep", {"seconds": 0.01}) for _ in range(5)]
    for job in jobs:
        manager.wait(job, 60)
    assert [job.id in manager.jobs for job in jobs] == [False, False, True, True, True]


def test_a_job_that_prints_without_end_does_not_hold_poll(manager):
    """The window writes each line to the console (slower than the worker
    prints them): one poll must still return quickly."""
    document = project.load("honeycomb_zeeman_rashba").to_json()

    def slow_listener(kind, job):
        if kind == "job" and job.kind == "console":
            time.sleep(0.002)

    unsubscribe = manager.subscribe(slow_listener)
    try:
        job = manager.console("for i in range(3000):\n    print(i)", document, None)
        longest, deadline = 0.0, time.monotonic() + 300
        while not job.done:
            assert time.monotonic() < deadline
            start = time.monotonic()
            manager.poll(0.05)
            longest = max(longest, time.monotonic() - start)
        assert job.status == "done" and len(job.log) == 3000 and longest < 1.0
    finally:
        unsubscribe()


def test_a_worker_that_cannot_start_is_not_restarted_without_end(monkeypatch, tmp_path):
    """No pyqula: the worker says why and dies; it is started again a few
    times, after a pause, then its jobs fail with the reason."""
    from guiqula.worker import client
    monkeypatch.setenv("GUIQULA_PYQULA_PATH", str(tmp_path / "no_pyqula_here"))
    monkeypatch.setattr(client, "START_PAUSE", 0.05)
    with JobManager(batch=1, interactive=False, warm=False) as m:
        first = m.wait(m.submit("sleep", {"seconds": 0.1}), 120)
        assert first.status == "failed" and "could not start" in first.error
        worker = m.workers["batch"][0]
        deadline = time.monotonic() + 120
        while worker.failures < client.START_ATTEMPTS:
            assert time.monotonic() < deadline
            m.poll(0.05)
        later = m.wait(m.submit("sleep", {"seconds": 0.1}), 60)
        assert later.status == "failed" and "cannot start" in later.error
        assert "VendoringError" in later.error
        for _ in range(20):
            m.poll(0.05)
        assert worker.starts == client.START_ATTEMPTS and worker.process is None
