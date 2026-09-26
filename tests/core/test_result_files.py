"""Result files (io/results.py): the arrays, the metadata, and the
geometry of a result drawn on the atoms survive a save and a load."""
import numpy as np

from guiqula.core.results import Result
from guiqula.io import results as result_files


def structure(sublattice=True):
    return {"positions": np.array([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0]]),
            "lattice": np.eye(3), "dimensionality": 2,
            "sublattice": np.array([1.0, -1.0]) if sublattice else None,
            "bonds": np.array([[0, 1]]), "image_bonds": np.zeros((0, 5), dtype=np.int64)}


def result(**extra):
    return Result(calculation="c1", kind="ldos", key="k", params={"energy": 0.0},
                  arrays={"ldos": np.array([0.2, 0.3])},
                  plot={"kind": "structure_scalar", "values": "ldos"}, **extra)


def test_round_trip_with_geometry(tmp_path):
    for sublattice in (True, False):
        saved = result(structure=structure(sublattice))
        arrays, info = result_files.save(saved, tmp_path / f"r{sublattice}")
        loaded = result_files.load(arrays)
        assert set(loaded.arrays) == {"ldos"}               # the geometry stays apart
        assert loaded.structure["dimensionality"] == 2
        assert isinstance(loaded.structure["dimensionality"], int)
        for name in ("positions", "lattice", "bonds", "image_bonds"):
            assert np.array_equal(loaded.structure[name], saved.structure[name]), name
        if sublattice:
            assert np.array_equal(loaded.structure["sublattice"], [1.0, -1.0])
        else:
            assert loaded.structure["sublattice"] is None
        assert loaded.plot == saved.plot and loaded.summary()["sites"] == 2


def test_round_trip_without_geometry(tmp_path):
    arrays, _ = result_files.save(result(), tmp_path / "plain")
    loaded = result_files.load(arrays)
    assert loaded.structure is None and loaded.summary()["sites"] is None
