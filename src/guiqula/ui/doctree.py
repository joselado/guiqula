"""A read-only view of the Document for phase 1: systems, their geometry
and term stacks with status and Hilbert-space mode, and calculations with
their result status. The editable outliner is phase 2."""
from PySide6.QtWidgets import QTreeWidget, QTreeWidgetItem

from guiqula.registry import pipeline

MARK = {"ok": "●", "disabled": "○", "invalid": "✗"}


class DocumentTree(QTreeWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("documentTree")
        self.setHeaderLabels(["entry", "status"])
        self.setColumnWidth(0, 260)

    def refresh(self, session, builds):
        """builds: system id -> latest build summary from the interactive worker."""
        self.clear()
        document = session.document
        for system in document.systems:
            build = builds.get(system.id)
            runtime = {r["id"]: r for r in build["reports"]} if build and \
                build.get("key") == _key(document, system.id) else {}
            top = QTreeWidgetItem([f"{system.id}  {system.name}", system.kind])
            self.addTopLevelItem(top)
            try:
                plan = pipeline.plan_system(document, system.id)
            except Exception as error:     # a broken document still displays
                QTreeWidgetItem(top, ["(cannot plan)", str(error)])
                continue
            geometry = QTreeWidgetItem(top, ["Geometry", system.geometry.base.kind])
            hamiltonian = QTreeWidgetItem(top, ["Hamiltonian", plan.mode + (
                f" (upgraded by {', '.join(plan.upgraded_by)})" if plan.upgraded_by else "")])
            if build and runtime:
                top.setText(1, f"{system.kind} · {build['sites']} sites · "
                               f"dimension {build['dimension']}")
            for stage in plan.stages:
                if stage.stage not in ("op", "term"):
                    continue
                status = "disabled" if not stage.enabled else "invalid" if stage.problem else "ok"
                message = stage.problem or ""
                report = runtime.get(stage.id)
                if report is not None and report["status"] == "invalid":
                    status, message = "invalid", report["message"]
                parent = geometry if stage.stage == "op" else hamiltonian
                item = QTreeWidgetItem(parent, [f"{MARK[status]} {stage.id}  {stage.kind}",
                                                message or status])
                item.setToolTip(1, message or status)
        calcs = QTreeWidgetItem(["Calculations", ""])
        self.addTopLevelItem(calcs)
        for calc in document.calculations:
            job = session.calc_jobs.get(calc.id)
            status = session.status(calc.id)
            if job is not None and status == "running":
                status = f"running {job.progress:.0%}"
            QTreeWidgetItem(calcs, [f"{calc.id}  {calc.kind} on {calc.system}", status])
        self.expandAll()


def _key(document, system_id):
    try:
        return pipeline.plan_system(document, system_id).key
    except Exception:
        return None
