"""The job panel (PLAN.md section 4, decision 14.2): one row per job with
its progress and a Cancel button, and the state of the worker processes."""
from PySide6.QtCore import Signal
from PySide6.QtWidgets import (QHeaderView, QLabel, QProgressBar, QTableWidget,
                               QTableWidgetItem, QToolButton, QVBoxLayout, QWidget)

COLUMNS = ("job", "what", "status", "progress", "")


class JobPanel(QWidget):
    cancel_requested = Signal(str)          # job id

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("jobPanel")
        self.table = QTableWidget(0, len(COLUMNS))
        self.table.setObjectName("jobTable")
        self.table.setHorizontalHeaderLabels(COLUMNS)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.workers = QLabel("workers: starting")
        self.workers.setObjectName("workerStatus")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.addWidget(self.table)
        layout.addWidget(self.workers)
        self.rows = {}

    def update_job(self, job):
        row = self.rows.get(job.id)
        if row is None:
            if job.kind == "build":
                return                  # interactive builds are not listed
            row = self.table.rowCount()
            self.table.insertRow(row)
            self.rows[job.id] = row
            self.table.setItem(row, 0, QTableWidgetItem(job.id))
            self.table.setItem(row, 1, QTableWidgetItem(f"{job.kind} {job.label}"))
            self.table.setItem(row, 2, QTableWidgetItem(""))
            bar = QProgressBar()
            bar.setRange(0, 100)
            bar.setObjectName(f"progress_{job.id}")
            self.table.setCellWidget(row, 3, bar)
            button = QToolButton()
            button.setText("Cancel")
            button.setObjectName(f"cancel_{job.id}")
            button.clicked.connect(lambda checked=False, j=job.id: self.cancel_requested.emit(j))
            self.table.setCellWidget(row, 4, button)
            self.table.scrollToBottom()
        status = job.status if not job.error else f"{job.status}: {job.error}"
        self.table.item(row, 2).setText(status)
        self.table.item(row, 2).setToolTip(job.traceback or status)
        self.table.cellWidget(row, 3).setValue(int(round(100 * job.progress)))
        self.table.cellWidget(row, 4).setEnabled(not job.done)

    def update_workers(self, infos):
        parts = []
        for info in infos:
            state = "dead" if not info["alive"] else ("busy" if info["job"] else
                                                      "ready" if info["ready"] else "starting")
            restarts = info["starts"] - 1
            parts.append(f"{info['role']} pid {info['pid']} {state}"
                         + (f" (restarted {restarts}x)" if restarts else ""))
        self.workers.setText("workers: " + " · ".join(parts))
