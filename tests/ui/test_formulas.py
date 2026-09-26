"""Formulas are shown as images (maintainer, phase-2 review item 5)."""
import pytest

from guiqula.registry import base as registry
from guiqula.ui import formulas


@pytest.mark.parametrize("spec", [s for s in registry.entries() if s.formula],
                         ids=lambda s: f"{s.family}:{s.kind}")
def test_every_registry_formula_renders(qapp, spec):
    """A new entry whose LaTeX mathtext cannot draw fails here."""
    image = formulas.pixmap(spec.formula, ratio=2.0)
    assert not image.isNull() and image.devicePixelRatio() == 2.0
    assert image.width() > 20


def test_bad_formula_is_reported(qapp):
    with pytest.raises(formulas.FormulaError, match="frac"):
        formulas.png(r"\frac{1}{")
