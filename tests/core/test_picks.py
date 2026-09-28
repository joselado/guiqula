"""Picks (PLAN.md phase 7): a point of a plot as the values it stands for
(core/picks.py) and what can be done with them (registry/picks.py), on
results written by hand, without pyqula."""
import numpy as np
import pytest

from guiqula.commands import Dispatcher
from guiqula.core import picks
from guiqula.core.results import Result
from guiqula.registry import picks as targets_of


def result(kind, arrays, plot, params=None, **extra):
    return Result(calculation="c1", kind=kind, key="k", params=params or {}, arrays=arrays,
                  plot=plot, **extra)


def bands(kpoints=True):
    k = np.arange(4)
    arrays = {"k": k, "energies": np.array([[-1.0, 1.0], [-0.5, 0.5], [-0.2, 0.2], [0.0, 0.0]])}
    if kpoints:
        arrays["kpoints"] = np.array([[0, 0, 0], [0.1, 0, 0], [0.2, 0.1, 0], [0.3, 0.3, 0]])
    return result("bands", arrays, {"kind": "lines", "x": "k", "y": "energies",
                                    "picks": {"x": "kpath", "y": "energy"}})


def test_a_band_point_is_a_kpoint_and_an_energy():
    picked = picks.pick(bands(), 2.2, 0.2, index=5)
    assert picked["values"] == {"kpoint": [0.2, 0.1, 0.0], "energy": 0.2}
    assert picked["label"] == "E = 0.2 · k = (0.2, 0.1, 0)"
    assert picked["notes"] == []


def test_a_result_without_kpoints_gives_the_energy_alone():
    """A result saved before phase 7: the menu says to run it again."""
    picked = picks.pick(bands(kpoints=False), 1, -0.5)
    assert picked["values"] == {"energy": -0.5}
    assert "run it again" in picked["notes"][0]


def test_a_finite_system_has_no_kpoint():
    finite = bands()
    finite.arrays = {"k": np.array([0.0]), "energies": np.array([[-1.0, 1.0]]),
                     "kpoints": np.zeros((0, 3))}
    picked = picks.pick(finite, 0, 1.0)
    assert picked["values"] == {"energy": 1.0} and picked["notes"] == []


def test_a_spectral_function_column_from_its_fraction():
    """pyqula draws A(k, E) against ik / len(kpath), flat per (k, E)."""
    kpoints = np.array([[0, 0, 0], [0.25, 0, 0], [0.5, 0, 0], [0.5, 0.25, 0]])
    fraction = np.repeat(np.arange(4) / 4, 3)
    r = result("spectral_function", {"k": fraction, "energies": np.tile([-1.0, 0, 1], 4),
                                     "weight": np.ones(12), "kpoints": kpoints},
               {"kind": "heatmap", "x": "k", "y": "energies", "c": "weight",
                "picks": {"x": "kpath", "y": "energy"}})
    assert picks.pick(r, 0.49, 0.3)["values"] == {"kpoint": [0.5, 0.0, 0.0], "energy": 0.3}
    assert picks.pick(r, 0.8, 0.3)["values"]["kpoint"] == [0.5, 0.25, 0.0]


def test_a_cell_of_a_map_to_reduced_k():
    """The nearest node of the mesh, through the k2K matrix the result keeps;
    a Fermi surface adds its own energy."""
    kx, ky = (a.ravel() for a in np.meshgrid(np.linspace(-1, 1, 5), np.linspace(-1, 1, 5),
                                             indexing="ij"))
    k2K = np.array([[0.5, 0.5, 0], [-0.5, 0.5, 0], [0, 0, 1.0]])
    r = result("fermi_surface", {"kx": kx, "ky": ky, "weight": np.ones(25)},
               {"kind": "heatmap", "x": "kx", "y": "ky", "c": "weight",
                "picks": {"x": "kmesh", "y": "kmesh", "fixed": {"energy": "energy"}}},
               params={"energy": 0.4}, kspace={"reciprocal": np.eye(3), "k2K": k2K})
    picked = picks.pick(r, 0.45, -0.05)
    assert picked["values"] == {"kpoint": [0.25, -0.25, 0.0], "energy": 0.4}
    r.kspace = None                                         # saved before phase 7
    picked = picks.pick(r, 0.45, -0.05)
    assert picked["values"] == {"energy": 0.4} and "run it again" in picked["notes"][0]


def test_sites_by_position():
    positions = np.array([[0.0, 0, 0], [1.0, 0, 0], [0.5, 0.8, 0.1]])
    r = result("ldos", {"ldos": np.ones(3)}, {"kind": "structure_scalar", "values": "ldos"},
               structure={"positions": positions})
    assert picks.pick(r, 1.0, 0.0, index=1)["values"] == {"sites": [[1.0, 0.0, 0.0]]}
    assert picks.pick(r, sites=[0, 2])["values"]["sites"] == [[0.0, 0.0, 0.0], [0.5, 0.8, 0.1]]
    assert picks.pick(r, sites=[0, 2])["label"] == "2 sites"
    empty = picks.pick(r, 3.0, 3.0)
    assert empty["values"] == {} and "no atom here" in empty["notes"][0]
    with pytest.raises(picks.PickError):
        picks.pick(r, sites=[5])


def test_a_sweep_yields_its_parameters():
    one = result("sweep", {"value": np.linspace(0, 1, 5), "gap": np.ones(5)},
                 {"kind": "lines", "x": "value", "y": "gap", "picks": {"x": "parameter"},
                  "parameters": {"x": ["t1", "m", 2]}})
    picked = picks.pick(one, 0.5, 1.0, index=2)
    assert picked["values"] == {"parameter": [{"entry": "t1", "param": "m", "component": 2,
                                               "value": 0.5}]}
    assert picked["label"] == "t1 m[z] = 0.5"
    two = result("sweep", {}, {"kind": "heatmap", "x": "value", "y": "value2", "c": "gap",
                               "picks": {"x": "parameter", "y": "parameter"},
                               "parameters": {"x": ["t1", "m", 2], "y": ["t2", "t", None]}})
    values = picks.pick(two, 0.3, 0.1)["values"]["parameter"]
    assert [(v["entry"], v["value"]) for v in values] == [("t1", 0.3), ("t2", 0.1)]


def test_nothing_to_pick():
    scalar = result("chern", {"chern": np.array(1.0)}, {"kind": "scalar", "rows": []})
    assert picks.pick(scalar, 0, 0)["values"] == {}
    old = result("dos", {"energies": np.zeros(3), "dos": np.zeros(3)},
                 {"kind": "lines", "x": "energies", "y": "dos"})    # no picks: before phase 7
    assert picks.pick(old, 0.1, 0)["notes"]


# ---- what a pick can do
def document():
    d = Dispatcher()
    s = d.do("add_system", lattice="honeycomb_lattice")
    bands_ = d.do("add_calculation", system=s, kind="bands")
    ldos = d.do("add_calculation", system=s, kind="ldos", params={"energy": 0.0})
    return d, s, bands_, ldos


def kinds(targets, what):
    return [t for t in targets if t["target"] == what]


def test_the_targets_of_an_energy_and_a_kpoint():
    d, s, bands_, ldos = document()
    values = {"energy": 0.3, "kpoint": [1 / 3, 1 / 3, 0.0]}
    found = targets_of.targets(d.document, s, values, source=bands_, mode="spinful",
                               dimensionality=2)
    order = [t["target"] for t in found]
    assert order == sorted(order, key=["set", "add", "kpath", "fermi_level"].index)
    k = [1 / 3, 1 / 3, 0.0]
    assert kinds(found, "set") == [{                    # over the mesh it stays: energy only
        "target": "set", "calculation": ldos, "params": {"energy": 0.3},
        "label": f"{ldos} Local density of states: energy = 0.3"}]
    added = kinds(found, "add")
    assert {"ldos", "fermi_surface", "eigenstate", "qpi"} <= {t["kind"] for t in added}
    ldos_new = [t for t in added if t["kind"] == "ldos"]      # over the mesh, then at that k
    assert [t["params"] for t in ldos_new] == [{"energy": 0.3}, {"energy": 0.3, "k": k}]
    assert [t["name"] for t in ldos_new] == [
        f"at E = 0.3 from {bands_}", f"at E = 0.3 · k = (0.333, 0.333, 0) from {bands_}"]
    state = next(t for t in added if t["kind"] == "eigenstate")
    assert state["label"] == "new Eigenstate at E = 0.3 · k = (0.333, 0.333, 0)"
    d.do("set_param", entry=ldos, name="k", value=[0.0, 0.0, 0.0])     # at a k: moved in k
    found = targets_of.targets(d.document, s, values, source=bands_)
    assert kinds(found, "set")[0]["params"] == {"energy": 0.3, "k": k}
    path = kinds(found, "kpath")
    assert [t["calculation"] for t in path] == [bands_]
    assert path[0]["kpath"] == ["G", [1 / 3, 1 / 3, 0.0]]         # the default path: from Γ
    level = kinds(found, "fermi_level")[0]
    assert level["term"] is None and level["mu"] == pytest.approx(-0.3)
    # a one-dimensional system has no Fermi surface; a Nambu one no Fermi-level target
    found = targets_of.targets(d.document, s, values, mode="nambu", dimensionality=1)
    assert "fermi_surface" not in {t["kind"] for t in kinds(found, "add")}
    assert kinds(found, "fermi_level") == []


def test_a_calculation_at_the_value_already_is_not_moved():
    d, s, bands_, ldos = document()
    found = targets_of.targets(d.document, s, {"energy": 0.0}, source=bands_)
    assert kinds(found, "set") == []


def test_the_fermi_level_follows_the_shift_the_result_saw():
    """The energy is picked on a spectrum the previous Fermi-level term had
    shifted already: the new shift adds to it."""
    d, s, bands_, ldos = document()
    snapshot = d.document
    term = d.do("add_term", system=s, kind="onsite", params={"mu": -0.3},
                name=targets_of.FERMI_LEVEL)
    found = kinds(targets_of.targets(d.document, s, {"energy": 0.1}, snapshot=snapshot),
                  "fermi_level")
    assert found[0]["term"] == term and found[0]["mu"] == pytest.approx(-0.1)
    found = kinds(targets_of.targets(d.document, s, {"energy": 0.1}, snapshot=d.document),
                  "fermi_level")
    assert found[0]["mu"] == pytest.approx(-0.4)


def test_sites_and_sweeps():
    d, s, bands_, ldos = document()
    t1 = d.do("add_term", system=s, kind="zeeman")
    gap = d.do("add_calculation", system=s, kind="gap")
    sweep = d.do("add_calculation", system=s, kind="sweep", params={
        "calculation": gap, "entry": t1, "param": "m", "component": 2})
    found = targets_of.targets(d.document, s, {"sites": [[0.0, 0.0, 0.0]]})
    assert [t["target"] for t in found] == ["add", "select_sites", "region"]
    assert found[0]["kind"] == "site_dos" and found[0]["name"] == "on the site at (0, 0)"
    assert found[0]["params"] == {"positions": [[0.0, 0.0, 0.0]]}
    point = [{"entry": t1, "param": "m", "component": 2, "value": 0.4}]
    found = targets_of.targets(d.document, s, {"parameter": point}, source=sweep)
    assert found == [{"target": "parameter", "set": point, "run": gap,
                      "label": f"set {t1} m[z] = 0.4 (and run {gap})"}]


def test_names_are_cosmetic():
    """A calculation or a term may have a name (a pick names what it adds),
    left out of the JSON when empty, never in a key."""
    from guiqula.registry import pipeline
    d, s, bands_, ldos = document()
    key = pipeline.calculation_key(d.document, ldos)
    assert '"name"' not in d.document.to_json().split('"calculations"')[1]
    d.do("rename", entry=ldos, name="at E = 0.3 from c1")
    assert d.document.calculation(ldos).name == "at E = 0.3 from c1"
    assert pipeline.calculation_key(d.document, ldos) == key
    t = d.do("add_term", system=s, kind="onsite", name="Fermi level")
    assert d.document.find(t)[4].name == "Fermi level"
    assert type(d.document).from_json(d.document.to_json()).find(t)[4].name == "Fermi level"


def test_where_a_marker_of_a_kpoint_goes():
    """The other way round (part 3): a picked k-point is drawn where it was
    picked, on the path, and at every image of it on a map."""
    b = bands()
    k = picks.pick(b, 2, 0.1)["values"]["kpoint"]
    assert picks.path_position(b, k) == 2.0
    assert picks.path_position(b, [0.9, 0.9, 0.0]) is None           # off the path
    kx, ky = (a.ravel() for a in np.meshgrid(np.linspace(-1, 1, 9), np.linspace(-1, 1, 9),
                                             indexing="ij"))
    k2K = np.array([[0.5, 0.5, 0], [-0.5, 0.5, 0], [0, 0, 1.0]])
    r = result("fermi_surface", {"kx": kx, "ky": ky, "weight": np.ones(81)},
               {"kind": "heatmap", "x": "kx", "y": "ky", "c": "weight",
                "picks": {"x": "kmesh", "y": "kmesh"}}, kspace={"k2K": k2K})
    k = picks.pick(r, 0.5, -0.25)["values"]["kpoint"]
    points = picks.mesh_positions(r, k)
    assert any(np.allclose(p, [0.5, -0.25]) for p in points)
    for p in points:                        # each an image: the same k up to integers
        shift = np.array(picks.reduced_k(r.kspace, *p)) - k
        assert np.allclose(shift, np.round(shift), atol=1e-9)
    r.kspace = None
    assert picks.mesh_positions(r, k) == []
