"""Results on disk: ``<name>.npz`` with the arrays and ``<name>.json`` with
everything else (parameters, plot spec, build reports, provenance, and the
Document snapshot that produced it). Readable without guiqula: every
array of the calculation is in the npz under its own name.

The npz also holds the geometry of a result drawn on the atoms (members
``structure_<name>``) and the results its from_result Fields read
(``reads_<calculation>_positions``, ``reads_<calculation>_<array>``); the
json's ``layout`` says which members those are, so an array of the
calculation may have any name (a Python calculation's ``structure_factor``
was read back as geometry): a member name an array takes is prefixed with
``_`` until it is free. A file without a layout (written before it
existed) has the geometry under the prefix only.
"""
import io
import json
import zipfile
from pathlib import Path

import numpy as np

from guiqula.core.results import Result, ResultRef

STRUCTURE_PREFIX = "structure_"


def _free(name, taken):
    """name, or name prefixed with _ until no other member has it."""
    while name in taken:
        name = "_" + name
    taken.add(name)
    return name


def _npz(members):
    """What numpy.savez writes, for {name: array}. savez takes the names as
    keyword arguments, so an array named 'file' or 'allow_pickle' collided
    with its own; arrays of Python objects are refused (ValueError): they
    would be pickled, and loading never unpickles."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_STORED, allowZip64=True) as archive:
        for name, value in members.items():
            with archive.open(name + ".npy", "w", force_zip64=True) as out:
                np.lib.format.write_array(out, np.asanyarray(value), allow_pickle=False)
    return buffer.getvalue()


def to_bytes(result):
    """(npz bytes, json text) of a result, as save() writes them; raises
    ValueError for arrays of Python objects."""
    members = dict(result.arrays)
    taken, layout = set(members), {}
    structure = {k: v for k, v in (result.structure or {}).items() if v is not None}
    if structure:
        layout["structure"] = {}
        for name, value in structure.items():
            member = layout["structure"][name] = _free(STRUCTURE_PREFIX + name, taken)
            members[member] = value
    if result.reads:
        layout["reads"] = {}
        for calc, ref in sorted(result.reads.items()):
            entry = layout["reads"][calc] = {"key": ref.key, "positions": None, "arrays": {}}
            if ref.positions is not None:
                entry["positions"] = _free(f"reads_{calc}_positions", taken)
                members[entry["positions"]] = ref.positions
            for name, value in ref.arrays.items():
                member = entry["arrays"][name] = _free(f"reads_{calc}_{name}", taken)
                members[member] = value
    npz = _npz(members)
    meta = {k: getattr(result, k) for k in ("calculation", "kind", "key", "params", "plot",
                                            "reports", "mode", "meta")}
    meta["document"] = json.loads(result.document) if result.document else None
    meta["layout"] = layout
    return npz, json.dumps(meta, indent=2, default=str)


def from_bytes(npz, text):
    """The Result of to_bytes()."""
    meta = json.loads(text)
    layout = meta.pop("layout", None)
    with np.load(io.BytesIO(npz)) as data:
        members = {k: data[k] for k in data.files}
    if layout is None:
        layout = {"structure": {k[len(STRUCTURE_PREFIX):]: k for k in members
                                if k.startswith(STRUCTURE_PREFIX)}}
    structure = {name: members.pop(member)
                 for name, member in layout.get("structure", {}).items()}
    if structure:
        structure.setdefault("sublattice", None)
        structure["dimensionality"] = int(structure["dimensionality"])
    reads = {}
    for calc, entry in layout.get("reads", {}).items():
        positions = members.pop(entry["positions"]) if entry["positions"] else None
        reads[calc] = ResultRef(entry["key"], positions,
                                {name: members.pop(member)
                                 for name, member in entry["arrays"].items()})
    snapshot = meta.pop("document", None)
    document = json.dumps(snapshot) if snapshot else ""
    return Result(arrays=members, document=document, structure=structure or None, reads=reads,
                  **meta)


def save(result, path):
    path = Path(path)
    stem = path.with_suffix("") if path.suffix in (".npz", ".json") else path
    npz, text = to_bytes(result)
    arrays, info = stem.with_suffix(".npz"), stem.with_suffix(".json")
    arrays.write_bytes(npz)
    info.write_text(text, encoding="utf-8")
    return arrays, info


def load(path):
    stem = Path(path).with_suffix("")
    return from_bytes(stem.with_suffix(".npz").read_bytes(),
                      stem.with_suffix(".json").read_text(encoding="utf-8"))
