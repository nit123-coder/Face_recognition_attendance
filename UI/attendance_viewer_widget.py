"""Attendance records and analytics UI."""
import os
import subprocess
import platform

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QTableWidget,
    QTableWidgetItem, QMessageBox
)
from PySide6.QtCore import Qt, QTimer

from .database import get_attendance_summary_last_days
try:
    from .database import get_attendance_with_absent
except Exception:
    # fallback if helper not available
    from .database import get_attendance_logs_last_days as get_attendance_with_absent


class AttendanceViewerWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('Attendance Viewer')
        self.setMinimumWidth(1000)
        self.setMinimumHeight(560)
        self._build_ui()
        self._load_records()
        self._start_auto_refresh()

    def _build_ui(self):
        main_layout = QVBoxLayout()

        control_layout = QHBoxLayout()
        refresh_btn = QPushButton('Refresh')
        refresh_btn.setMinimumHeight(36)
        refresh_btn.setStyleSheet(
            'QPushButton { background-color: #2196F3; color: white; border: none; '
            'border-radius: 5px; font-weight: 600; }'
            'QPushButton:hover { background-color: #0b7dda; }'
        )
        refresh_btn.clicked.connect(self._load_records)
        control_layout.addWidget(refresh_btn)

        control_layout.addStretch()

        self.table = QTableWidget()
        self.table.setColumnCount(7)
        self.table.setHorizontalHeaderLabels([
            'Candidate ID', 'Name', 'Timestamp', 'Type', 'Status', 'Snapshot Path', 'View'
        ])
        self.table.horizontalHeader().setStretchLastSection(False)
        self.table.setColumnWidth(0, 110)
        self.table.setColumnWidth(1, 180)
        self.table.setColumnWidth(2, 160)
        self.table.setColumnWidth(3, 100)
        self.table.setColumnWidth(4, 100)
        self.table.setColumnWidth(5, 260)
        self.table.setAlternatingRowColors(True)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.SingleSelection)

        self.summary_label = QLabel('Showing attendance for the last 7 days.')
        self.summary_label.setWordWrap(True)

        main_layout.addLayout(control_layout)
        main_layout.addWidget(self.table)
        main_layout.addWidget(self.summary_label)
        self.setLayout(main_layout)

    def _start_auto_refresh(self):
        self.auto_refresh_timer = QTimer(self)
        self.auto_refresh_timer.timeout.connect(self._load_records)
        self.auto_refresh_timer.start(60_000)

    def _load_records(self):
        days = 7
        # Collect records for each day using the "with absent" helper so absent rows
        # are included per day (the helper returns date-only timestamps for absentees).
        all_records = []
        from datetime import date, timedelta
        for i in range(days):
            d = date.today() - timedelta(days=i)
            try:
                recs = get_attendance_with_absent(d.isoformat())
            except Exception:
                # fallback to legacy function if signature differs
                recs = []
            all_records.extend(recs)

        self.table.setRowCount(len(all_records))
        for row, (_, candidate_id, candidate_name, log_time, log_type, status, snapshot_path) in enumerate(all_records):
            self.table.setItem(row, 0, QTableWidgetItem(candidate_id))
            self.table.setItem(row, 1, QTableWidgetItem(candidate_name))
            self.table.setItem(row, 2, QTableWidgetItem(log_time))
            is_absent = isinstance(log_time, str) and len(log_time) == 10 and log_time.count('-') == 2
            self.table.setItem(row, 3, QTableWidgetItem('' if is_absent else (log_type or 'Unknown')))
            self.table.setItem(row, 4, QTableWidgetItem(status or 'Unknown'))

            snapshot_item = QTableWidgetItem(snapshot_path or 'N/A')
            snapshot_item.setToolTip(snapshot_path or 'No snapshot available')
            snapshot_item.setData(Qt.UserRole, snapshot_path)
            self.table.setItem(row, 5, snapshot_item)

            view_btn = QPushButton('View')
            view_btn.setEnabled(bool(snapshot_path))
            view_btn.clicked.connect(lambda checked, p=snapshot_path: self._open_snapshot(p))
            self.table.setCellWidget(row, 6, view_btn)

        summary = get_attendance_summary_last_days(days=days)
        summary_text = f'Last {days} days: {len(all_records)} total attendances'
        if summary:
            summary_text += '\nTop candidates: ' + ', '.join(f'{name} ({count})' for name, count in summary[:5])
        self.summary_label.setText(summary_text)

    def _open_snapshot(self, photo_path):
        if not photo_path:
            QMessageBox.information(self, 'No Photo', 'There is no detected photo for the selected entry.')
            return
        if not os.path.exists(photo_path):
            QMessageBox.warning(self, 'Missing File', 'Saved photo file does not exist anymore.')
            return

        try:
            if platform.system() == 'Windows':
                os.startfile(photo_path)
            elif platform.system() == 'Darwin':
                subprocess.Popen(['open', photo_path])
            else:
                subprocess.Popen(['xdg-open', photo_path])
        except Exception as exc:
            QMessageBox.warning(self, 'Error', f'Unable to open photo: {exc}')
