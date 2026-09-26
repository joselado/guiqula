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
                {"kind": "expression", "expr": "import os"}, {"kind": "positions", "tol": -1}):
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
