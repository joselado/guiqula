"""Export figure, data and script (decision 13.16; PLAN.md phase 5, design
item 12): one folder per result with what reproduces it without guiqula,
for a report, a course or a paper.

- ``figure.png`` and ``figure.pdf``: the plot as the result view draws it,
  in the light theme (a white background whatever the window shows); the
  window draws it, through the ``figure`` callable, since figures belong
  to the UI process;
- ``data.npz`` and ``data.json``: the arrays and everything else
  (io/results.py), ``data.csv`` too for curves (one column per curve);
- ``script.py``: the pyqula script that computes the arrays, exported
  from the Document the result was computed with (its snapshot), so a
  stale result is reproduced as it is, not as the Document now reads;
- ``document.json``: that Document, which guiqula opens;
- ``README.txt``: what each file is.
"""
import csv
import time
from pathlib import Path

import numpy as np

import guiqula
from guiqula.core.document import Document
from guiqula.io import results as result_files
from guiqula.io.script import export_script

CURVES = ("lines", "colored_scatter")


def curves_table(result):
    """(header, rows) of a curve result: x, then one column per curve;
    None for the other plot kinds."""
    plot = result.plot
    if plot.get("kind") not in CURVES:
        return None
    y = np.asarray(result.arrays[plot["y"]], dtype=float)
    x = np.asarray(result.arrays[plot["x"]], dtype=float) if plot.get("x") \
        else np.arange(len(y), dtype=float)
    y = y.reshape(len(x), -1)
    xname = plot.get("x") or "index"
    names = [plot["y"]] if y.shape[1] == 1 else [f"{plot['y']}_{i}" for i in range(y.shape[1])]
    return [xname] + names, np.column_stack([x, y])


def scalar_rows(result):
    """[(label, value)] of a result of numbers (plot kind scalar), else None."""
    plot = result.plot
    if plot.get("kind") != "scalar":
        return None
    out = []
    for name, label in plot.get("rows", []):
        value = np.asarray(result.arrays[name])
        out.append((label, value.item() if value.size == 1 else value.tolist()))
    return out


def write(folder, result, figure=None, trusted=True, results=None, stale=False):
    """Write the bundle of a result into folder (made if needed); returns
    the paths written. figure(png_path, pdf_path) draws the plot (the
    window's); results: the ResultRefs a from_result Field reads."""
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    written = []
    if figure is not None:
        png, pdf = folder / "figure.png", folder / "figure.pdf"
        figure(png, pdf)
        written += [png, pdf]
    written += list(result_files.save(result, folder / "data"))
    table = curves_table(result)
    if table is not None:
        header, rows = table
        path = folder / "data.csv"
        with path.open("w", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(header)
            writer.writerows(rows.tolist())
        written.append(path)
    numbers = scalar_rows(result)
    if numbers is not None:
        path = folder / "data.csv"
        with path.open("w", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(["quantity", "value"])
            writer.writerows(numbers)
        written.append(path)
    document = Document.from_json(result.document) if result.document else None
    if document is not None:
        skipped = {r["id"]: r["message"] for r in result.skipped}
        script = folder / "script.py"
        script.write_text(export_script(document, result.calculation, skipped, trusted,
                                        results or {}))
        path = folder / "document.json"
        path.write_text(document.to_json())
        written += [script, path]
    readme = folder / "README.txt"
    readme.write_text(_readme(result, [p.name for p in written], stale))
    written.append(readme)
    return written


def _readme(result, names, stale):
    what = {"figure.png": "the plot (also figure.pdf)",
            "data.npz": "the arrays (numpy.load); data.json has the parameters, the plot "
                        "spec, the build reports and the Document snapshot",
            "data.csv": "the same numbers as a table",
            "script.py": "the pyqula script computing the arrays (python script.py)",
            "document.json": "the guiqula document the result was computed with"}
    lines = [f"{result.calculation}: {result.kind} ({result.mode})",
             f"exported {time.strftime('%Y-%m-%d %H:%M')} by guiqula {guiqula.__version__}",
             ""]
    if stale:
        lines += ["The document was changed after this result was computed; these files "
                  "reproduce the result, not the document as it is now.", ""]
    lines += [f"{name}: {text}" for name, text in what.items() if name in names]
    return "\n".join(lines) + "\n"
