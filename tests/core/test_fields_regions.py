import numpy as np
import pytest

from guiqula.core import fields, regions


def test_field_forms():
    assert fields.normalize(1) == 1.0
    assert fields.normalize("2*pi") == pytest.approx(2 * np.pi)   # position-free: constant
    assert fields.normalize(" 0.3*tanh(x/4) ") == "0.3*tanh(x/4)"
    assert fields.normalize({"kind": "constant", "value": 3}) == 3.0
    assert fields.normalize({"kind": "expression", "expr": "x"}) == "x"
    for bad in (True, None, [1], "x +", {"kind": "nope"}, float("nan")):
        with pytest.raises(fields.FieldError):
            fields.normalize(bad)


def test_compile_and_code_agree():
    rng = np.random.default_rng(2)
    weight = regions.compile_indicator({"kind": "expression", "expr": "x > 0"})
    weight_code = regions.code_indicator({"kind": "expression", "expr": "x > 0"})
    for value in (0.5, "0.3*tanh(x/4)+y"):
        for w, wc in ((None, None), (weight, weight_code)):
            f = fields.compile_scalar(value, w)
            g = eval(fields.code_scalar(value, wc), {"np": np})
            for p in rng.normal(size=(8, 3)):
                fp = f(p) if callable(f) else f
                gp = g(p) if callable(g) else g
                assert fp == pytest.approx(gp, abs=1e-15)
    assert fields.code_vector([0, 0, 0.1]) == "[0.0, 0.0, 0.1]"   # all constant: a plain list


def test_region_selections():
    positions = np.array([[0.0, 0, 0], [1.0, 0, 0], [-1.0, 0, 0]])
    by_expr = {"kind": "expression", "expr": "x < -0.5"}
    by_pos = {"kind": "positions", "positions": [[1.0, 0.01, 0.0]], "tol": 0.05}
    assert regions.evaluate_positions(by_expr, positions).tolist() == [False, False, True]
    assert regions.evaluate_positions(by_pos, positions).tolist() == [False, True, False]
    indicator = regions.compile_indicator(by_pos)
    assert [indicator(p) for p in positions] == [0.0, 1.0, 0.0]
    code = eval(f"lambda r: {regions.code_indicator(by_pos)}", {"np": np})
    assert [code(p) for p in positions] == [0.0, 1.0, 0.0]
    for bad in ({"kind": "lasso"}, {"kind": "positions", "positions": [[1, 2]]},
                {"kind": "expression", "expr": "import os"}, {"kind": "positions", "tol": -1},
                {**by_pos, "tol": float("inf")}, {**by_pos, "tol": "wide"},
                {**by_pos, "positions": [[float("nan"), 0, 0]]}):
        with pytest.raises(regions.RegionError):
            regions.normalize(bad)


PIECEWISE = {"kind": "piecewise", "default": "0.1*x",
             "pieces": [{"region": "r1", "value": 1.0}, {"region": "r2", "value": "y"}]}
REGIONS = {"r1": {"kind": "expression", "expr": "x > 0"},
           "r2": {"kind": "positions", "positions": [[1.0, 2.0, 0.0]], "tol": 0.05}}


def test_piecewise_forms():
    assert fields.normalize(PIECEWISE) == {
        "kind": "piecewise", "default": "0.1*x",
        "pieces": [{"region": "r1", "value": 1.0}, {"region": "r2", "value": "y"}]}
    assert fields.normalize({"kind": "piecewise"}) == {"kind": "piecewise", "default": 0.0,
                                                       "pieces": []}
    assert fields.kind_of(fields.normalize(PIECEWISE)) == "piecewise"
    assert fields.regions_of([0.0, PIECEWISE, "x"]) == ["r1", "r2"]
    assert fields.regions_of(fields.rename_regions(PIECEWISE, {"r1": "r7"})) == ["r7", "r2"]
    nested = dict(PIECEWISE, pieces=[{"region": "r1", "value": PIECEWISE}])
    for bad in (nested, dict(PIECEWISE, extra=1), dict(PIECEWISE, pieces=[{"region": "r1"}]),
                dict(PIECEWISE, pieces=[{"region": 3, "value": 1}]),
                dict(PIECEWISE, default="x +")):
        with pytest.raises(fields.FieldError):
            fields.normalize(bad)


def test_piecewise_compile_code_and_evaluate_agree():
    """The later piece wins where regions overlap; the default elsewhere."""
    positions = np.array([[-1.0, 0, 0], [0.5, 0, 0], [1.0, 2.0, 0.0], [2.0, -1, 0]])
    expected = [-0.1, 1.0, 2.0, 1.0]           # (1, 2) is in r1 and r2: r2 wins
    f = fields.compile_scalar(PIECEWISE, regions=REGIONS)
    g = eval(fields.code_scalar(PIECEWISE, regions=REGIONS), {"np": np})
    assert [f(p) for p in positions] == pytest.approx(expected)
    assert [g(p) for p in positions] == pytest.approx(expected)
    assert fields.evaluate_positions(PIECEWISE, positions, REGIONS).tolist() == \
        pytest.approx(expected)
    weight = regions.compile_indicator({"kind": "expression", "expr": "y < 1"})
    weighted = fields.compile_scalar(PIECEWISE, weight, REGIONS)
    assert [weighted(p) for p in positions] == pytest.approx([-0.1, 1.0, 0.0, 1.0])
    with pytest.raises(fields.FieldError, match="does not exist"):
        fields.compile_scalar(PIECEWISE, regions={"r1": REGIONS["r1"]})


def test_profile_interpolated_and_painted_fields():
    """The remaining Field kinds of PLAN.md 3.8: a profile is an expression
    once its numbers are filled in; interpolated and painted Fields are
    functions of stored points; each compiles, evaluates and gives code
    that agrees."""
    import numpy as np

    from guiqula.core import fields
    positions = np.array([[0.0, 0.0, 0.0], [1.0, 0.5, 0.0], [-2.0, 1.0, 0.0], [4.0, 0.0, 0.0]])
    values = [
        {"kind": "profile", "name": "gaussian", "params": {"x0": -1.0, "width": 1.5}},
        {"kind": "profile", "name": "step", "params": {"angle": 0.4, "smoothing": 0.3}},
        {"kind": "profile", "name": "aubry_andre", "params": {}},
        {"kind": "interpolated", "points": [[0, 0, 1.0], [3, 0, -1.0]], "length": 1.2},
        {"kind": "painted", "sites": [[1.0, 0.5, 0.0, 2.0]], "default": -0.5},
    ]
    namespace = {"np": np, **{f.__name__: f for f in (fields.interpolated_field,
                                                      fields.painted_field)}}
    for value in values:
        value = fields.normalize(value)
        compiled = fields.compile_scalar(value)
        exported = eval(fields.code_scalar(value), namespace)
        evaluated = fields.evaluate_positions(value, positions)
        for r, v in zip(positions, evaluated):
            assert compiled(r) == pytest.approx(v) == pytest.approx(exported(r))
    painted = fields.normalize(values[-1])
    assert list(fields.evaluate_positions(painted, positions)) == [-0.5, 2.0, -0.5, -0.5]
    for bad, message in [({"kind": "profile", "name": "nope"}, "unknown profile"),
                         ({"kind": "profile", "name": "disk", "params": {"radius": -1}},
                          "must be positive"),
                         ({"kind": "interpolated", "points": []}, "needs control points"),
                         ({"kind": "painted", "sites": [[0, 0, 1]]}, "x, y, z, value")]:
        with pytest.raises(fields.FieldError, match=message):
            fields.normalize(bad)


def test_stored_points_are_found_fast_and_as_before():
    """Painted and from_result Fields and regions by positions look sites up
    through core/nearest.py (phase 5, part 3): the bulk evaluation, the
    compiled function and the exported one agree, for many sites."""
    import time
    from guiqula.core.results import ResultRef
    x, y = np.meshgrid(np.arange(120.0), np.arange(120.0) * 0.9)
    sites = np.column_stack([x.ravel(), y.ravel(), np.zeros(x.size)])        # 14,400
    values = np.sin(sites[:, 0]) + sites[:, 1]
    painted = fields.normalize({"kind": "painted", "tol": 0.2, "default": -1.0,
                                "sites": np.column_stack([sites, values])[::2].tolist()})
    queries = sites + 0.05
    start = time.perf_counter()
    bulk = fields.evaluate_positions(painted, queries)
    assert time.perf_counter() - start < 1.0
    expected = np.where(np.arange(len(sites)) % 2 == 0, values, -1.0)
    assert np.allclose(bulk, expected)
    compiled = fields.compile_scalar(painted)
    assert [compiled(r) for r in queries[:50]] == pytest.approx(expected[:50])
    ref = ResultRef("key", sites, {"m": np.column_stack([values, 2 * values, 3 * values])})
    field = {"kind": "from_result", "calculation": "c1", "array": "m", "component": 1,
             "scale": 0.5, "tol": 0.1}
    assert np.allclose(fields.evaluate_positions(field, queries, results={"c1": ref}), values)
    assert np.allclose(fields.evaluate_positions(field, queries + 1.0, results={"c1": ref}), 0)
    region = {"kind": "positions", "positions": sites[:100].tolist(), "tol": 0.1}
    inside = regions.evaluate_positions(region, queries)
    assert inside.sum() == 100 and inside[:100].all()
    indicator = regions.compile_indicator(region)
    assert indicator(queries[5]) == 1.0 and indicator(queries[500]) == 0.0


def test_a_from_result_field_is_refused_where_it_would_break_a_key():
    """tol = inf was accepted, raised in every key of the system and was
    saved as null; a component of 1.0 (JSON clients send floats) was stored
    as a float and indexed the array with it, a raw IndexError in the
    planner."""
    from guiqula.core.results import ResultRef
    field = {"kind": "from_result", "calculation": "c1", "array": "m", "component": 1.0}
    assert fields.normalize(field)["component"] == 1
    assert type(fields.normalize(field)["component"]) is int
    ref = ResultRef("key", np.eye(3), {"m": np.arange(9.0).reshape(3, 3)})
    assert fields.evaluate_positions(field, np.eye(3), results={"c1": ref}).tolist() == \
        [1.0, 4.0, 7.0]
    for bad, message in [(dict(field, tol=float("inf")), "tol must be a finite number"),
                         (dict(field, tol=0.0), "tol must be positive"),
                         (dict(field, scale=float("nan")), "scale must be a finite number"),
                         (dict(field, component=1.5), "component is 0, 1, 2"),
                         (dict(field, component=True), "component is 0, 1, 2")]:
        with pytest.raises(fields.FieldError, match=message):
            fields.normalize(bad)


def test_the_code_of_a_result_not_computed_says_so():
    """The help writes an entry's pyqula code: a from_result Field whose
    result is not there says so, as the engine does, not KeyError: 'c1'."""
    field = {"kind": "from_result", "calculation": "c1", "array": "m"}
    for results in (None, {}):
        with pytest.raises(fields.FieldError, match="the result of c1 is not available"):
            fields.code_scalar(field, results=results)
        with pytest.raises(fields.FieldError, match="the result of c1 is not available"):
            fields.compile_scalar(field, results=results)


def test_painting_many_sites():
    positions = np.column_stack([np.arange(5000.0), np.zeros(5000), np.zeros(5000)])
    value = fields.paint(0.25, positions, range(0, 5000, 2), 1.0)
    assert value["default"] == 0.25 and len(value["sites"]) == 2500
    value = fields.paint(value, positions, [0, 1, 1, 3], 2.0)      # repaint, and new sites once
    assert len(value["sites"]) == 2502
    evaluated = fields.evaluate_positions(value, positions[:5])
    assert list(evaluated) == [2.0, 2.0, 1.0, 2.0, 1.0]
    for bad in ([[0, 0, "1", 2]], [[0, 0, True, 2]], [[0, 0, float("nan"), 2]]):
        with pytest.raises(fields.FieldError, match="painted site"):
            fields.normalize({"kind": "painted", "sites": bad})
