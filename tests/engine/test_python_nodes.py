"""Python nodes (PLAN.md 3.1, 13.7): what they see, how their errors are
flagged, the Hilbert space they declare, the plot a calculation node
sets, and trust: in a document that is not trusted they are skipped and
left out of the keys."""
import numpy as np
import pytest

from guiqula.commands import Dispatcher
from guiqula.engine.build import build_system
from guiqula.engine.calculations import CalculationError, run_calculation
from guiqula.io.script import export_script
from guiqula.registry import pipeline


def document(code, needs="nothing"):
    d = Dispatcher()
    s = d.do("add_system", lattice="honeycomb_lattice")
    d.do("set_construction", system=s, has_spin=False)
    t = d.do("add_term", system=s, kind="python", params={"code": code, "needs": needs})
    return d, s, t


def report(built, entry):
    return next(r for r in built.reports if r["id"] == entry)


def test_error_names_the_line_and_the_stack_goes_on(pyqula):
    d, s, t = document("x = 1\nh.add_nothing_at_all()\n")
    d.do("add_term", system=s, kind="onsite", params={"mu": 0.3})
    built = build_system(d.document, s)
    r = report(built, t)
    assert r["status"] == "invalid" and "AttributeError" in r["message"]
    assert "line 2 of the code" in r["message"]
    assert np.allclose(np.diag(built.h.intra.toarray() if hasattr(built.h.intra, "toarray")
                               else built.h.intra).real, 0.3)     # the onsite still applied


def test_output_and_names(pyqula):
    d, s, t = document("print('sites', len(g.r), np.pi > 3, pyqula.__name__)")
    r = report(build_system(d.document, s), t)
    assert r["status"] == "ok" and r["output"] == "sites 2 True pyqula"


def test_needs_fixes_the_hilbert_space(pyqula):
    d, s, t = document("h.add_zeeman([0, 0, 0.2])", needs="spin")
    plan = pipeline.plan_system(d.document, s)
    assert plan.mode == "spinful" and plan.upgraded_by == [t]
    built = build_system(d.document, s)
    assert [r["mode"] for r in built.reports if r["stage"] == "construction"] == ["spinful"]
    d.do("set_param", entry=t, name="needs", value="nothing")
    assert pipeline.plan_system(d.document, s).mode == "spinless"


def test_a_term_must_leave_a_hamiltonian(pyqula):
    d, s, t = document("h = 3")
    r = report(build_system(d.document, s), t)
    assert r["status"] == "invalid" and "not a Hamiltonian" in r["message"]


def test_untrusted_nodes_are_skipped_and_leave_the_keys(pyqula):
    d, s, t = document("h.add_onsite(0.5)")
    c = d.do("add_calculation", system=s, kind="bands", params={"nk": 10})
    trusted = run_calculation(d.document, c)
    untrusted = run_calculation(d.document, c, trusted=False)
    assert [r["id"] for r in untrusted.skipped] == [t]
    assert pipeline.UNTRUSTED in untrusted.skipped[0]["message"]
    assert trusted.key != untrusted.key                      # trusting makes it stale
    assert untrusted.key == pipeline.calculation_key(d.document, c, trusted=False)
    assert np.allclose(trusted.arrays["energies"], untrusted.arrays["energies"] + 0.5)
    assert pipeline.code_entries(d.document) == [t]
    source = export_script(d.document, c, trusted=False)
    assert f"# {t} python: skipped" in source and "h.add_onsite(0.5)" not in source
    assert "h.add_onsite(0.5)" in export_script(d.document, c)
    d.do("add_calculation", system=s, kind="python")
    with pytest.raises(CalculationError, match="trusted"):
        run_calculation(d.document, "c2", trusted=False)


def test_calculation_plots(pyqula):
    d, s, _ = document("pass")
    c = d.do("add_calculation", system=s, kind="python", params={
        "code": "arrays = {'gap': h.get_gap(), 'sites': len(g.r)}"})
    result = run_calculation(d.document, c)
    assert result.plot == {"kind": "scalar", "rows": [["gap", "gap"], ["sites", "sites"]]}
    d.do("set_param", entry=c, name="code", value=(
        "r = np.array(g.r)\narrays = {'x2': r[:, 0]**2}\n"
        "plot = {'kind': 'structure_scalar', 'values': 'x2'}\n"))
    result = run_calculation(d.document, c)
    assert result.plot["kind"] == "structure_scalar" and result.structure is not None
    d.do("set_param", entry=c, name="code", value="arrays = {'a': [1, 2]}\nplot = {'kind': "
                                                   "'lines', 'x': 'nope', 'y': 'a'}")
    with pytest.raises(CalculationError, match="plot names"):
        run_calculation(d.document, c)
    d.do("set_param", entry=c, name="code", value="arrays = {'a': [1, 2, 4]}")
    assert run_calculation(d.document, c).plot == {"kind": "lines", "y": "a",
                                                   "xlabel": "index", "ylabel": "a"}


def test_syntax_errors_are_refused_by_the_command():
    d = Dispatcher()
    s = d.do("add_system")
    with pytest.raises(Exception, match="syntax error in line 2"):
        d.do("add_term", system=s, kind="python", params={"code": "x = 1\nx = = 2"})


def test_calculation_arrays_are_numbers_and_the_plot_fits_them(pyqula):
    """What a project file keeps (numbers) and what ui/plots.py can draw is
    checked when the node runs, not when the window draws or a file opens."""
    d, s, _ = document("pass")
    c = d.do("add_calculation", system=s, kind="python")

    def run(code):
        d.do("set_param", entry=c, name="code", value=code)
        return run_calculation(d.document, c)

    for code, message in [
            ("arrays = {'gap': 0.5, 'info': {'nk': 10}}", "not a number"),
            ("arrays = {'note': None}", "not a number"),
            ("arrays = {'a': [1, [2, 3]]}", "arrays\\['a'\\]"),
            ("arrays = {'x': np.arange(3.0), 'y': np.arange(4.0)}\n"
             "plot = {'kind': 'lines', 'x': 'x', 'y': 'y'}", "cannot draw"),
            ("arrays = {'x': np.arange(3.0)}\nplot = {'kind': 'heatmap', 'x': 'x', 'y': 'x'}",
             "names c"),
            ("arrays = {'v': np.arange(5.0)}\nplot = {'kind': 'structure_scalar', "
             "'values': 'v'}", "each of the 2 sites"),
            ("arrays = {'g': 1.0}\nplot = {'kind': 'scalar', 'rows': ['g']}", "pairs"),
            ("exit()", "exit\\(\\)")]:
        with pytest.raises(CalculationError, match=message):
            run(code)
    result = run("arrays = {'gap': 0.5, 'k': np.arange(5), 'e': np.arange(10.0)}")
    assert result.plot == {"kind": "lines", "x": "k", "y": "e", "xlabel": "k", "ylabel": "e"}
    from guiqula.registry.python_nodes import CALCULATION_CODE
    result = run(CALCULATION_CODE)          # the template: a row of bands per k
    assert result.arrays["energies"].shape == (100, 2) and result.plot["x"] == "k"


def test_exit_in_a_node_flags_it_and_the_stack_goes_on(pyqula):
    d, s, t = document("h.add_onsite(0.1)\nexit()")
    d.do("add_term", system=s, kind="onsite", params={"mu": 0.3})
    built = build_system(d.document, s)
    r = report(built, t)
    assert r["status"] == "invalid" and "exit()" in r["message"] and "line 2" in r["message"]


def test_a_python_term_of_a_classical_system(pyqula):
    """On a classical system the term sees the model as model (decision
    13.5) and hands it back: it is not "not a Hamiltonian"."""
    d = Dispatcher()
    s = d.do("add_system", lattice="triangular_lattice", kind="classical_spin")
    t = d.do("add_term", system=s, kind="python", params={"code": "x = len(model.geometry.r)"})
    assert report(build_system(d.document, s), t)["status"] == "ok"
    d.do("set_param", entry=t, name="code", value="model = 3")
    r = report(build_system(d.document, s), t)
    assert r["status"] == "invalid" and "not a SpinModel" in r["message"]
