import numpy as np
import pytest

from guiqula.core import fields, regions


def test_field_forms():
    assert fields.normalize(1) == 1.0
    assert fields.normalize("2*pi") == pytest.approx(2 * np.pi)   # position-free: constant
    assert fields.normalize(" 0.3*tanh(x/4) ") == "0.3*tanh(x/4)"
    assert fields.normalize({"kind": "constant", "value": 3}) == 3.0
    assert fields.normalize({"kind": "expression", "expr": "x"}) == "x"
    for bad in (True, None, [1], "x +", {"kind": "painted"}, float("nan")):
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
