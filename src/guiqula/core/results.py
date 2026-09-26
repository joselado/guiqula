"""Results of calculations (PLAN.md 3.4): plain data that crosses the
worker boundary by pickling and is drawn in the UI process.

A result drawn on the atoms (plot kinds structure_scalar and
structure_vector) carries the geometry it was computed on in
``structure`` (engine/structure.describe: positions, lattice,
dimensionality, sublattice, bonds, image_bonds), since the UI process has
no built geometry of the snapshot it came from; ``arrays`` holds only what
the calculation itself returns, which is what an exported script
reproduces."""
from dataclasses import dataclass, field

# plot kinds the UI draws (ui/plots.py implements each once)
PLOT_KINDS = ("lines", "colored_scatter", "heatmap", "structure_scalar", "structure_vector",
              "scalar")


@dataclass
class Result:
    calculation: str            # calculation id
    kind: str                   # calculation kind
    key: str                    # calculation key at run time (staleness)
    params: dict                # normalized parameters used
    arrays: dict                # name -> numpy array
    plot: dict                  # plot kind and which arrays to draw
    reports: list = field(default_factory=list)   # per-entry build reports
    mode: str = ""              # Hilbert space the Hamiltonian was built in
    document: str = ""          # JSON snapshot of the Document that was run
    meta: dict = field(default_factory=dict)      # timing, pyqula provenance, cores
    structure: dict | None = None                 # geometry arrays, for plots on the atoms

    @property
    def skipped(self):
        """Entries flagged invalid and skipped while building (decision 14.3)."""
        return [r for r in self.reports if r["status"] == "invalid"]

    @property
    def meanfield(self):
        """What the mean field reported (its total energy), or None when it
        did not run."""
        for report in self.reports:
            if report.get("stage") == "meanfield" and report["status"] == "ok":
                return report.get("notes", {})
        return None

    def summary(self):
        return {"calculation": self.calculation, "kind": self.kind, "key": self.key,
                "arrays": {k: list(getattr(v, "shape", ())) for k, v in self.arrays.items()},
                "plot": self.plot["kind"], "mode": self.mode,
                "skipped": [r["id"] for r in self.skipped], "meanfield": self.meanfield,
                "seconds": self.meta.get("seconds"),
                "sites": None if self.structure is None else len(self.structure["positions"])}
