"""Project files (PLAN.md 3.5): a ``.guiqula`` file is a zip holding
``document.json`` (later also cached results); a bare ``.json`` document is
read and written too, which is how presets are stored so that they diff in
git (decision 14.4). Presets ship inside the package (guiqula/presets) and
load by name."""
import json
import zipfile
from pathlib import Path

from guiqula.core.document import Document, DocumentError

PRESETS = Path(__file__).resolve().parents[1] / "presets"


def presets():
    return sorted(p.stem for p in PRESETS.glob("*.json"))


def preset_path(name):
    path = PRESETS / f"{name}.json"
    if not path.is_file():
        raise DocumentError(f"no preset {name!r}; presets: {presets()}")
    return path


def resolve(path_or_name):
    """A path, or the name of a shipped preset."""
    path = Path(path_or_name)
    if path.exists():
        return path
    if path.suffix == "" and path.name in presets():
        return preset_path(path.name)
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


def save(document, path):
    """Write a .guiqula zip, or bare JSON for any other suffix. The file is
    written next to the target and renamed over it, so a crash never leaves
    a half-written project."""
    path = Path(path)
    temporary = path.with_name(path.name + ".tmp")
    text = document.to_json()
    if path.suffix == ".guiqula":
        with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("document.json", text)
    else:
        temporary.write_text(text + "\n")
    temporary.replace(path)
    return path
