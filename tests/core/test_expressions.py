import numpy as np
import pytest

from guiqula.core.expressions import Expression, ExpressionError


@pytest.mark.parametrize("source, point, expected", [
    ("0.3*tanh(x/4)", (1.0, 0.0, 0.0), 0.3 * np.tanh(0.25)),
    ("np.exp(-r**2)", (1.0, 1.0, 0.0), np.exp(-2.0)),
    ("where(x < 0, 1, -1)", (-2.0, 0.0, 0.0), 1.0),
    ("(x > 0) & (y > 0)", (1.0, 1.0, 0.0), 1.0),
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
    "hypot(x, y, z)", "maximum(x, 1.5, y)", "np.sin(x, y)", "sin()", "where(x)",
    "clip(x, 0, 1, y)", "1e999*x",
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


def test_an_expression_never_writes_into_the_positions_it_is_given():
    """A ufunc takes the array to write into as its next positional
    argument: "hypot(x, y, z)" overwrote the z of the canvas's own site
    positions (Remove selected then removed nothing). A call gives exactly
    the function's arguments, and an evaluation works on copies."""
    from guiqula.core import fields, regions
    with pytest.raises(ExpressionError, match=r"hypot\(\) takes 2 arguments, not 3"):
        Expression("hypot(x, y, z)")
    with pytest.raises(regions.RegionError, match="takes 2 arguments"):
        regions.normalize({"kind": "expression", "expr": "maximum(x, 1.5, y) > 0"})
    positions = np.array([[0.0, 1.0, 2.0], [1.0, 2.0, 3.0], [2.0, 3.0, 4.0]])
    before = positions.copy()
    assert fields.evaluate_positions("hypot(x, y) + clip(z, 0, 3)", positions).tolist() == \
        pytest.approx([3.0, 3 + np.sqrt(5), 3 + np.sqrt(13)])
    regions.evaluate_positions({"kind": "expression", "expr": "where(x > 0, y, z) > 2"},
                               positions)
    values = Expression("x")(positions[:, 0], positions[:, 1], positions[:, 2])
    values[:] = 9.0
    assert np.array_equal(positions, before)


def test_what_cannot_be_read_is_an_expression_error():
    """A literal too large for a float, or a chain of hundreds of
    comparisons, raised OverflowError or RecursionError, which escaped the
    dispatcher and the live preview of a Field being typed."""
    from guiqula.commands import CommandError, Dispatcher
    from guiqula.core import fields
    for text in ("1" + "0" * 400 + "*x", "x<" * 499 + "x"):
        with pytest.raises(fields.FieldError):
            fields.normalize(text)
    d = Dispatcher()
    s = d.do("add_system")
    with pytest.raises(CommandError, match="too large"):
        d.do("add_region", system=s, select={"kind": "expression", "expr": "x < 1" + "0" * 400})
    assert Expression("-2 < x < 2 < 3").at((0.0, 0.0, 0.0)) == 1.0     # a short chain reads


@pytest.mark.parametrize("source, expected", [
    ("(x > 0) + (y > 0)", 2.0), ("-(x > 0)", -1.0), ("(x > 0) - (x < 0)", 1.0),
    ("2*(y > 0.5) - (x > 5)", 2.0), ("~(x > 0) + (x > 0)", 1.0),
    ("(x > 0) & (y > 2) | (x > 0.5)", 1.0), ("(x > 0) ^ (y > 0)", 0.0),
    ("where((x > 0) & (y < 0), 1, -1)", -1.0), ("abs(x > 0) + sqrt(y > 0)", 2.0),
])
def test_a_comparison_is_one_or_zero_wherever_it_appears(source, expected):
    """One arithmetic everywhere: numpy booleans added as a logical or
    ("(x > 0) + (y > 0)" was 1 at a position and 2 between literals) and
    refused - (every build failed on "-(x > 0)"). The engine per site, the
    canvas on arrays, the exported script and the folded constant agree."""
    from guiqula.core import fields
    point = np.array([1.0, 1.0, 0.0])
    e = Expression(source)
    assert e.at(point) == expected
    assert e.evaluate_positions(point[None, :]).tolist() == [expected]
    script = eval(f"lambda r: {e.to_python('r')}", {"np": np})
    assert script(point) == expected
    literal = source.replace("x", "1.0").replace("y", "1.0")
    assert fields.normalize(literal) == expected


def test_a_value_that_is_not_real_is_refused():
    """A negative number to a fractional power is complex in Python: the
    constant "(-8)**(1/3)" raised a raw TypeError, and "0*x + (-8)**(1/3)"
    was complex per site and 1.0 on the canvas."""
    from guiqula.core import fields
    with pytest.raises(fields.FieldError, match="not a real number"):
        fields.normalize("(-8)**(1/3)")
    e = Expression("0*x + (-8)**(1/3)")
    with pytest.raises(ExpressionError, match="not a real number"):
        e.at((1.0, 0.0, 0.0))
    with pytest.raises(ExpressionError, match="not a real number"):
        e.evaluate_positions(np.zeros((3, 3)))
    assert Expression("(8)**(1/3) + 0*x").at((1.0, 0.0, 0.0)) == pytest.approx(2.0)


def test_a_value_that_is_not_finite_is_nan_or_inf():
    """sqrt(x) where x < 0 and 1/x at x = 0 are NaN and inf, on arrays and
    at one position, as numpy gives them: the floating-point warning numpy
    raised from the evaluation, whose builtins are empty, was
    KeyError('__import__') on Python 3.14 with NumPy 2.4."""
    import warnings
    x = np.array([-1.0, 0.0, 4.0])
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        values = Expression("sqrt(x)").evaluate_positions(np.column_stack([x, 0 * x, 0 * x]))
        assert np.isnan(values[0]) and values[1:].tolist() == [0.0, 2.0]
        assert Expression("1/x").at((0.0, 0.0, 0.0)) == np.inf
        assert np.isnan(Expression("log(x)").at((-1.0, 0.0, 0.0)))
