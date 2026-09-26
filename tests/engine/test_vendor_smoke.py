"""The vendored pyqula builds a Hamiltonian through the shim. Runs in the
test's scratch cwd (conftest), as every pyqula call must."""
import os

from guiqula import vendoring


def test_honeycomb_hamiltonian(repo, tmp_path):
    vendoring.ensure_pyqula_on_path()
    from pyqula import geometry
    if not os.environ.get(vendoring.ENV_VAR):
        assert geometry.__file__ == str(repo / "vendor" / "pyqula" / "geometry.py")
    g = geometry.honeycomb_lattice()
    h = g.get_hamiltonian()
    assert len(g.r) == 2
    assert h.intra.shape == (4, 4)       # pyqula builds spinful by default
    assert os.getcwd() == str(tmp_path)
