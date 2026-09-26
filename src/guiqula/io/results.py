"""Results on disk: ``<name>.npz`` with the arrays and ``<name>.json`` with
everything else (parameters, plot spec, build reports, provenance, and the
Document snapshot that produced it). Readable without guiqula. The
geometry of a result drawn on the atoms is in the same npz, its arrays
prefixed with ``structure_`` (STRUCTURE_PREFIX)."""
import json
from pathlib import Path

import numpy as np

from guiqula.core.results import Result

STRUCTURE_PREFIX = "structure_"


def save(result, path):
    path = Path(path)
    stem = path.with_suffix("") if path.suffix in (".npz", ".json") else path
    arrays = stem.with_suffix(".npz")
    extra = {STRUCTURE_PREFIX + k: v for k, v in (result.structure or {}).items()
             if v is not None}
    np.savez(arrays, **result.arrays, **extra)
    meta = {k: getattr(result, k) for k in ("calculation", "kind", "key", "params", "plot",
                                            "reports", "mode", "meta")}
    meta["document"] = json.loads(result.document) if result.document else None
    info = stem.with_suffix(".json")
    info.write_text(json.dumps(meta, indent=2, default=str))
    return arrays, info


def load(path):
    stem = Path(path).with_suffix("")
    meta = json.loads(stem.with_suffix(".json").read_text())
    with np.load(stem.with_suffix(".npz")) as data:
        arrays = {k: data[k] for k in data.files if not k.startswith(STRUCTURE_PREFIX)}
        structure = {k[len(STRUCTURE_PREFIX):]: data[k] for k in data.files
                     if k.startswith(STRUCTURE_PREFIX)}
    if structure:
        structure.setdefault("sublattice", None)
        structure["dimensionality"] = int(structure["dimensionality"])
    snapshot = meta.pop("document", None)
    document = json.dumps(snapshot) if snapshot else ""
    return Result(arrays=arrays, document=document, structure=structure or None, **meta)
