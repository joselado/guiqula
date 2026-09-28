"""Result files (io/results.py): the arrays, the metadata, and the
geometry of a result drawn on the atoms survive a save and a load."""
import numpy as np
import pytest

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


def test_round_trip_of_a_map_over_the_zone(tmp_path):
    """The reciprocal frame a pick maps its cells with (phase 7) is kept
    apart from the arrays; a one-dimensional frame has no k2K."""
    for k2K in (np.array([[0.5, 0.5, 0], [-0.5, 0.5, 0], [0, 0, 1.0]]), None):
        saved = result(kspace={"reciprocal": np.eye(3), "k2K": k2K})
        arrays, _ = result_files.save(saved, tmp_path / f"map{k2K is None}")
        loaded = result_files.load(arrays)
        assert set(loaded.arrays) == {"ldos"}
        assert np.array_equal(loaded.kspace["reciprocal"], np.eye(3))
        assert (loaded.kspace["k2K"] is None) if k2K is None else \
            np.array_equal(loaded.kspace["k2K"], k2K)
    arrays, _ = result_files.save(result(), tmp_path / "flat")
    assert result_files.load(arrays).kspace is None


def test_any_array_name_survives(tmp_path):
    """A Python calculation names its arrays freely: structure_factor was
    read back as geometry (and the result dropped on reopening), file and
    allow_pickle collided with numpy.savez's arguments (Save failed). The
    results a from_result Field read are kept apart too."""
    from guiqula.core.results import ResultRef
    names = ("ldos", "structure_factor", "structure_positions", "file", "allow_pickle",
             "reads_c2_m")
    reads = {"c2": ResultRef("key2", np.array([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0]]),
                             {"m": np.array([[0.0, 0.0, 1.0], [0.0, 0.0, -1.0]])})}
    saved = result(structure=structure(), reads=reads)
    saved.arrays = {name: np.arange(3.0) + i for i, name in enumerate(names)}
    arrays, _ = result_files.save(saved, tmp_path / "names")
    assert set(np.load(arrays).files) >= set(names)     # readable without guiqula
    loaded = result_files.load(arrays)
    assert set(loaded.arrays) == set(names)
    for name in names:
        assert np.array_equal(loaded.arrays[name], saved.arrays[name]), name
    assert np.array_equal(loaded.structure["positions"], structure()["positions"])
    assert loaded.reads["c2"].key == "key2"
    assert np.array_equal(loaded.reads["c2"].positions, reads["c2"].positions)
    assert np.array_equal(loaded.reads["c2"].arrays["m"], reads["c2"].arrays["m"])


def test_a_file_without_a_layout_still_reads(tmp_path):
    """Files written before the layout existed: the geometry by its prefix."""
    import io
    import json
    buffer = io.BytesIO()
    np.savez(buffer, ldos=np.array([0.2, 0.3]), **{"structure_" + k: v for k, v in
                                                   structure().items()})
    npz, text = result_files.to_bytes(result())
    meta = json.loads(text)
    del meta["layout"]
    loaded = result_files.from_bytes(buffer.getvalue(), json.dumps(meta))
    assert set(loaded.arrays) == {"ldos"} and loaded.structure["dimensionality"] == 2
    assert loaded.reads == {}


def test_a_failed_save_leaves_no_temporary(tmp_path, monkeypatch):
    """Save raises what went wrong and removes its half-written file."""
    from guiqula.io import project
    document = project.load("honeycomb_zeeman_rashba")

    def broken(result):
        raise TypeError("not today")
    monkeypatch.setattr(result_files, "to_bytes", broken)
    with pytest.raises(TypeError, match="not today"):
        project.save(document, tmp_path / "p.guiqula", {"c1": result()})
    assert list(tmp_path.iterdir()) == []            # no p.guiqula.tmp
