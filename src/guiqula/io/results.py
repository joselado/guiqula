"""Results on disk: ``<name>.npz`` with the arrays and ``<name>.json`` with
everything else (parameters, plot spec, build reports, provenance, and the
Document snapshot that produced it). Readable without guiqula."""
import json
from pathlib import Path

import numpy as np

from guiqula.core.results import Result


def save(result, path):
    path = Path(path)
    stem = path.with_suffix("") if path.suffix in (".npz", ".json") else path
    arrays = stem.with_suffix(".npz")
    np.savez(arrays, **result.arrays)
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
        arrays = {k: data[k] for k in data.files}
    document = json.dumps(meta.pop("document")) if meta.get("document") else ""
    return Result(arrays=arrays, document=document, **meta)
