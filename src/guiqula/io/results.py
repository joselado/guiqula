"""Results on disk: ``<name>.npz`` with the arrays and ``<name>.json`` with
everything else (parameters, plot spec, build reports, provenance, and the
Document snapshot that produced it). Readable without guiqula. The
geometry of a result drawn on the atoms is in the same npz, its arrays
prefixed with ``structure_`` (STRUCTURE_PREFIX)."""
import io
import json
from pathlib import Path

import numpy as np

from guiqula.core.results import Result

STRUCTURE_PREFIX = "structure_"


def to_bytes(result):
    """(npz bytes, json text) of a result, as save() writes them. Arrays of
    Python objects are refused (ValueError): they would be pickled, and
    loading never unpickles."""
    buffer = io.BytesIO()
    extra = {STRUCTURE_PREFIX + k: v for k, v in (result.structure or {}).items()
             if v is not None}
    np.savez(buffer, allow_pickle=False, **result.arrays, **extra)
    meta = {k: getattr(result, k) for k in ("calculation", "kind", "key", "params", "plot",
                                            "reports", "mode", "meta")}
    meta["document"] = json.loads(result.document) if result.document else None
    return buffer.getvalue(), json.dumps(meta, indent=2, default=str)


def from_bytes(npz, text):
    """The Result of to_bytes()."""
    meta = json.loads(text)
    with np.load(io.BytesIO(npz)) as data:
        arrays = {k: data[k] for k in data.files if not k.startswith(STRUCTURE_PREFIX)}
        structure = {k[len(STRUCTURE_PREFIX):]: data[k] for k in data.files
                     if k.startswith(STRUCTURE_PREFIX)}
    if structure:
        structure.setdefault("sublattice", None)
        structure["dimensionality"] = int(structure["dimensionality"])
    snapshot = meta.pop("document", None)
    document = json.dumps(snapshot) if snapshot else ""
    return Result(arrays=arrays, document=document, structure=structure or None, **meta)


def save(result, path):
    path = Path(path)
    stem = path.with_suffix("") if path.suffix in (".npz", ".json") else path
    npz, text = to_bytes(result)
    arrays, info = stem.with_suffix(".npz"), stem.with_suffix(".json")
    arrays.write_bytes(npz)
    info.write_text(text)
    return arrays, info


def load(path):
    stem = Path(path).with_suffix("")
    return from_bytes(stem.with_suffix(".npz").read_bytes(), stem.with_suffix(".json").read_text())
