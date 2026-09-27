import numpy as np
import pytest

from guiqula.core.expressions import Expression, ExpressionError


@pytest.mark.parametrize("source, point, expected", [
    ("0.3*tanh(x/4)", (1.0, 0.0, 0.0), 0.3 * np.tanh(0.25)),
    ("np.exp(-r**2)", (1.0, 1.0, 0.0), np.exp(-2.0)),
    ("where(x < 0, 1, -1)", (-2.0, 0.0, 0.0), 1.0),
    ("(x > 0) & (y > 0)", (1.0, 1.0, 0.0), True),
    ("cos(pi*z) + 7//2", (0.0, 0.0, 1.0), -1.0 + 3.0),
    ("-x + +y - ~(x > 1)", (0.5, 2.0, 0.0), 0.5),        # ~ is a logical not
])
def test_values(source, point, expected):
    assert Expression(source).at(point) == pytest.approx(expected)


def test_vectorised_matches_pointwise():
    e = Expression("0.3*tanh(x/4) + where(y > 0, r, 0)")
    positions = np.random.default_rng(0).normal(size=(20, 3))
    assert np.allclose(e.evaluate_positions(positions), [e.at(p) for p in positions])
    assert Expression("2.5").evaluate_positions(positions).shape == (20,)


@pytest.mark.parametrize("source", [
    "__import__('os')", "x.__class__", "(1).real", "lambda: 1", "x if y else z", "x and y",
    "np.linalg.norm(x)", "q + 1", "foo(x)", "tanh(x, out=y)", "'a'", "x[0]", "[x]", "{x: 1}",
    "tanh(*x)", "True", "(x := 1)", "np", "exec('1')", "open('f')", "x" * 1001,
    "-" * 60 + "x", "x + sin", "np.tanh", "where(x < 0, cos, 1)",
])
def test_rejected(source):
    with pytest.raises(ExpressionError):
        Expression(source)


def test_huge_power_fails_fast():
    with pytest.raises(ExpressionError):
        Expression("9**9**9").at((0, 0, 0))


@pytest.mark.parametrize("source", ["0.3*tanh(x/4)", "where(x < 0, r, -z)", "exp(-(x**2+y**2)/pi)"])
def test_to_python_is_equivalent(source):
    e = Expression(source)
    f = eval(f"lambda r: {e.to_python('r')}", {"np": np})
    for p in np.random.default_rng(1).normal(size=(10, 3)):
        assert f(p) == pytest.approx(e.at(p), abs=1e-15)


def test_chained_comparisons_act_elementwise():
    """-2 < x < 2 is (-2 < x) & (x < 2): per site as pyqula calls it, on
    arrays as the canvas and the regions evaluate it, and in the script."""
    e = Expression("-2 < x <= 2 < 3")
    positions = np.array([[-3.0, 0, 0], [0.0, 0, 0], [2.0, 0, 0], [2.5, 0, 0]])
    assert list(e.evaluate_positions(positions)) == [0.0, 1.0, 1.0, 0.0]
    assert [bool(e.at(p)) for p in positions] == [False, True, True, False]
    f = eval(f"lambda r: {e.to_python('r')}", {"np": np})
    assert [bool(f(p)) for p in positions] == [False, True, True, False]
