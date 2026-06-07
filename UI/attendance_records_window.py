"""Attendance Records Window - View and analyze attendance logs."""

from pathlib import Path
from PySide6.QtCore import Qt, QDate
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QComboBox, QMessageBox,
    QDialogButtonBox
)
from .database import get_attendance_logs_by_date
try:
    from .database import get_attendance_with_absent
except Exception:
    get_attendance_with_absent = None
from .database import get_candidate


class AttendanceRecordsWindow(QDialog):
    """Window for viewing and analyzing attendance logs."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Attendance Records")
        self.setMinimumSize(1000, 650)
        self.resize(1200, 750)
        self.setStyleSheet(
            "QDialog { background-color: gray; }")
        
        self.selected_date = QDate.currentDate()
        self.init_ui()
        self.load_attendance_logs()

    def init_ui(self):
        """Initialize the attendance window UI."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        header = QLabel("Attendance Records")
        header.setStyleSheet("font-size: 18px; font-weight: bold; color: #1f1f1f;")
        layout.addWidget(header)

        control_layout = QHBoxLayout()
        control_layout.setSpacing(12)

        date_search_layout = QHBoxLayout()
        date_search_layout.setSpacing(8)

        date_search_layout.addWidget(QLabel('Day:'))
        self.day_combo = QComboBox()
        self.day_combo.addItems([str(day) for day in range(1, 32)])
        self.day_combo.setCurrentText(str(self.selected_date.day()))
        date_search_layout.addWidget(self.day_combo)

        date_search_layout.addWidget(QLabel('Month:'))
        self.month_combo = QComboBox()
        month_names = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
        for idx, name in enumerate(month_names, start=1):
            self.month_combo.addItem(name, idx)
        self.month_combo.setCurrentIndex(self.selected_date.month() - 1)
        date_search_layout.addWidget(self.month_combo)

        date_search_layout.addWidget(QLabel('Year:'))
        self.year_combo = QComboBox()
        current_year = self.selected_date.year()
        for year in range(current_year - 2, current_year + 2):
            self.year_combo.addItem(str(year))
        self.year_combo.setCurrentText(str(current_year))
        date_search_layout.addWidget(self.year_combo)

        search_btn = QPushButton('Search')
        search_btn.setMinimumHeight(36)
        search_btn.setMinimumWidth(50)  # Set the minimum width to 50 pixels for the search button and refresh_btn.setMinimumWidth(50)
        search_btn.setStyleSheet(
            'QPushButton { background-color: #4CAF50; color: white; border: none; '
            'border-radius: 5px; font-weight: 600; }'
            'QPushButton:hover { background-color: #45a049; }'
        )
        search_btn.clicked.connect(self.on_search_date)
        date_search_layout.addWidget(search_btn)

        refresh_btn = QPushButton("Refresh")
        refresh_btn.setMinimumHeight(36)
        refresh_btn.setMinimumWidth(50)
        refresh_btn.setStyleSheet(
            "QPushButton { background-color: #2196F3; color: white; border: none; "
            "border-radius: 5px; font-weight: 600; }"
            "QPushButton:hover { background-color: #0b7dda; }"
        )
        refresh_btn.clicked.connect(self.load_attendance_logs)
        date_search_layout.addWidget(refresh_btn)

        export_btn = QPushButton("Export Date")
        export_btn.setMinimumHeight(36)
        export_btn.setMinimumWidth(76)
        export_btn.setStyleSheet(
            "QPushButton { background-color: #4CAF50; color: white; border: none; "
            "border-radius: 5px; font-weight: 600; }"
            "QPushButton:hover { background-color: #45a049; }"
        )
        export_btn.clicked.connect(self.export_csv)
        date_search_layout.addWidget(export_btn)

        date_search_layout.addStretch()
        control_layout.addLayout(date_search_layout, 1)
        layout.addLayout(control_layout)

        self.attendance_table = QTableWidget()
        # Add Department column (extra for the admin attendance view)
        self.attendance_table.setColumnCount(8)
        self.attendance_table.setHorizontalHeaderLabels([
            "Candidate ID", "Name", "Department", "Timestamp", "Type", "Status", "Snapshot Path", "View"
        ])
        self.attendance_table.horizontalHeader().setStretchLastSection(False)
        self.attendance_table.setColumnWidth(0, 110)
        self.attendance_table.setColumnWidth(1, 180)
        self.attendance_table.setColumnWidth(2, 120)  # Department
        self.attendance_table.setColumnWidth(3, 160)
        self.attendance_table.setColumnWidth(4, 80)
        self.attendance_table.setColumnWidth(5, 120)
        self.attendance_table.setColumnWidth(6, 260)
        self.attendance_table.setStyleSheet(
            "QTableWidget { background-color: gray; border: 1px solid #ddd; }"
            "QTableWidget::item { padding: 6px; }"
            "QHeaderView::section { background-color: lightgray; color:black; padding: 6px; font-weight: bold; }"
        )
        self.attendance_table.setAlternatingRowColors(True)
        #self.attendance_table.setEditTriggers(QTableWidget.NoEditTriggers)
        #self.attendance_table.setSelectionBehavior(QTableWidget.SelectRows)
        #self.attendance_table.setSelectionMode(QTableWidget.SingleSelection)
        layout.addWidget(self.attendance_table)

        footer_layout = QHBoxLayout()
        footer_layout.addStretch()
        self.setLayout(layout)

    def on_search_date(self):
        """Reload attendance logs for the selected date."""
        year = int(self.year_combo.currentText())
        month = self.month_combo.currentData()
        day = int(self.day_combo.currentText())

        if not QDate.isValid(year, month, day):
            QMessageBox.warning(self, 'Invalid Date', 'The selected date is not valid. Please choose a valid day, month, and year.')
            return

        self.selected_date = QDate(year, month, day)
        self.load_attendance_logs()

    def load_attendance_logs(self):
        """Load attendance logs for the selected date."""
        date_string = self.selected_date.toString('yyyy-MM-dd')
        records = []
        # Prefer the helper that includes absent rows; fall back to legacy logs
        if get_attendance_with_absent is not None:
            try:
                records = get_attendance_with_absent(date_string)
            except Exception:
                records = get_attendance_logs_by_date(date_string)
        else:
            records = get_attendance_logs_by_date(date_string)

        self.attendance_table.setRowCount(len(records))

        for row, (log_id, candidate_id, candidate_name, log_time, log_type, status, snapshot_path) in enumerate(records):
            # Determine department from personal_details when possible
            dept = ''
            try:
                candidate = get_candidate(candidate_id)
                if candidate and len(candidate) >= 3:
                    dept = candidate[2] or ''
            except Exception:
                dept = ''

            self.attendance_table.setItem(row, 0, QTableWidgetItem(candidate_id or ''))
            self.attendance_table.setItem(row, 1, QTableWidgetItem(candidate_name or ''))
            self.attendance_table.setItem(row, 2, QTableWidgetItem(dept))
            self.attendance_table.setItem(row, 3, QTableWidgetItem(log_time or ''))
            self.attendance_table.setItem(row, 4, QTableWidgetItem(log_type or ''))
            self.attendance_table.setItem(row, 5, QTableWidgetItem(status or ''))

            snapshot_item = QTableWidgetItem(snapshot_path or "N/A")
            snapshot_item.setToolTip(snapshot_path or "No snapshot available")
            self.attendance_table.setItem(row, 6, snapshot_item)

            view_btn = QPushButton("View")
            view_btn.setEnabled(bool(snapshot_path))
            view_btn.clicked.connect(lambda checked, p=snapshot_path: self.open_snapshot_dialog(p))
            self.attendance_table.setCellWidget(row, 7, view_btn)

    def open_snapshot_dialog(self, snapshot_path: str):
        """Open a popup dialog that displays the captured snapshot image."""
        if not snapshot_path:
            QMessageBox.warning(self, "Missing Snapshot", "No snapshot path available.")
            return

        snapshot_file = Path(snapshot_path)
        if not snapshot_file.exists():
            QMessageBox.warning(self, "File Not Found", "The requested snapshot image file does not exist.")
            return

        dialog = QDialog(self)
        dialog.setWindowTitle("Captured Photo")
        dialog.setMinimumSize(600, 450)
        dialog.setLayout(QVBoxLayout())

        image_label = QLabel()
        image_label.setAlignment(Qt.AlignCenter)
        pixmap = QPixmap(str(snapshot_file))
        scaled = pixmap.scaled(860, 640, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        image_label.setPixmap(scaled)
        dialog.layout().addWidget(image_label)

        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.rejected.connect(dialog.reject)
        dialog.layout().addWidget(buttons)

        dialog.exec()

    def export_csv(self):
        """Export selected date's attendance logs to CSV."""
        date_string = self.selected_date.toString('yyyy-MM-dd')
        records = get_attendance_logs_by_date(date_string)

        if not records:
            QMessageBox.warning(self, "No Data", "No attendance logs exist for the selected date.")
            return

        try:
            export_path = Path.home() / f"attendance_logs_{date_string}.csv"
            with open(export_path, 'w', encoding='utf-8') as csv_file:
                csv_file.write("Candidate ID,Name,Department,Timestamp,Type,Status,Snapshot Path\n")
                for _, candidate_id, candidate_name, log_time, log_type, status, snapshot_path in records:
                    # lookup department
                    dept = ''
                    try:
                        candidate = get_candidate(candidate_id)
                        if candidate and len(candidate) >= 3:
                            dept = candidate[2] or ''
                    except Exception:
                        dept = ''
                    csv_file.write(
                        f'"{candidate_id}","{candidate_name}","{dept}","{log_time}","{log_type}","{status}","{snapshot_path or ""}"\n'
                    )

            QMessageBox.information(
                self,
                "Export Success",
                f"Attendance logs exported to:\n{export_path}"
            )
        except Exception as exc:
            QMessageBox.critical(self, "Export Error", f"Error exporting logs: {exc}")
