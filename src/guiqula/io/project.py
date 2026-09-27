"""Project files (PLAN.md 3.5): a ``.guiqula`` file is a zip holding
``document.json`` and the results of its calculations
(``results/<calculation>.npz`` and ``.json``, as io/results.py writes a
result file); a bare ``.json`` document is read and written too, without
results, which is how presets are stored so that they diff in git
(decision 14.4). Presets ship inside the package (guiqula/presets) and
load by name. A result keeps the key it was computed with, so after a
load it is stale exactly when the Document it belongs to says so. The
converged mean-field Hamiltonian is not kept (its total energy is, in the
result's reports): a run computes it again (section 11)."""
import json
import zipfile
from pathlib import Path

from guiqula.core.document import Document, DocumentError
from guiqula.io import results as result_files

RESULTS = "results/"

PRESETS = Path(__file__).resolve().parents[1] / "presets"


def presets():
    return sorted(p.stem for p in PRESETS.glob("*.json"))


def preset_path(name):
    path = PRESETS / f"{name}.json"
    if not path.is_file():
        raise DocumentError(f"no preset {name!r}; presets: {presets()}")
    return path


def resolve(path_or_name):
    """A path, or the name of a shipped preset. A bare name (no folder, no
    suffix) that names a preset is the preset, even when the working
    directory has a file or folder of that name (the gallery and the
    Presets menu hand over bare names; project files have a suffix); write
    ./name for such a file."""
    text = str(path_or_name)
    path = Path(text)
    bare = path.suffix == "" and "/" not in text and "\\" not in text
    if bare and path.name in presets():
        return preset_path(path.name)
    if path.is_file():
        return path
    if path.is_dir():
        raise DocumentError(f"{path_or_name}: a folder, not a document")
    raise DocumentError(f"{path_or_name}: no such file and no such preset; presets: {presets()}")


def load(path_or_name):
    path = resolve(path_or_name)
    if zipfile.is_zipfile(path):
        with zipfile.ZipFile(path) as archive:
            try:
                text = archive.read("document.json").decode()
            except KeyError:
                raise DocumentError(f"{path}: no document.json inside") from None
    else:
        text = path.read_text()
    try:
        return Document.from_data(json.loads(text))
    except json.JSONDecodeError as error:
        raise DocumentError(f"{path}: not JSON ({error})") from None


def load_results(path_or_name):
    """{calculation id: Result} kept in a .guiqula file (none elsewhere)."""
    path = resolve(path_or_name)
    if not zipfile.is_zipfile(path):
        return {}
    out = {}
    with zipfile.ZipFile(path) as archive:
        names = set(archive.namelist())
        for name in sorted(names):
            if name.startswith(RESULTS) and name.endswith(".json"):
                stem = name[:-len(".json")]
                if stem + ".npz" in names:
                    result = result_files.from_bytes(archive.read(stem + ".npz"),
                                                     archive.read(name).decode())
                    out[result.calculation] = result
    return out


def save(document, path, results=None):
    """Write a .guiqula zip (with results: {calculation id: Result}), or
    bare JSON for any other suffix. The file is written next to the target
    and renamed over it, so a crash never leaves a half-written project."""
    path = Path(path)
    temporary = path.with_name(path.name + ".tmp")
    text = document.to_json()
    if path.suffix == ".guiqula":
        with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("document.json", text)
            present = {c.id for c in document.calculations}
            for calc, result in sorted((results or {}).items()):
                if calc in present:
                    npz, meta = result_files.to_bytes(result)
                    archive.writestr(f"{RESULTS}{calc}.npz", npz)
                    archive.writestr(f"{RESULTS}{calc}.json", meta)
    else:
        temporary.write_text(text + "\n")
    temporary.replace(path)
    return path
