import numpy as np
import pytest

from guiqula import vendoring


@pytest.fixture(scope="session")
def pyqula():
    """Make sure the vendored pyqula is importable (tests run in tmp cwds)."""
    vendoring.ensure_pyqula_on_path()
    import pyqula as module
    return module


def hk_matrices(h, n=4, seed=0):
    """H(k) at a few k-points: compares two Hamiltonians completely."""
    gen = h.get_hk_gen()
    ks = np.random.default_rng(seed).random((n, 3))
    return [np.asarray(gen(k).todense() if hasattr(gen(k), "todense") else gen(k)) for k in ks]


def assert_same_hamiltonian(h1, h2):
    assert (h1.has_spin, getattr(h1, "has_eh", False)) == (h2.has_spin, getattr(h2, "has_eh", False))
    for a, b in zip(hk_matrices(h1), hk_matrices(h2)):
        assert a.shape == b.shape
        assert np.allclose(a, b, rtol=0, atol=1e-12)
