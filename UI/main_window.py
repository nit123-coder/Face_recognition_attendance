import cv2
from datetime import date, timedelta
from pathlib import Path

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QPushButton, QLabel, QComboBox,
    QVBoxLayout, QHBoxLayout, QGridLayout, QTableWidget, QTableWidgetItem,
    QListWidget, QDockWidget, QStatusBar, QTabWidget, QScrollArea, QFrame,
    QMessageBox,QHeaderView
)
from PySide6.QtCore import Qt, QTimer

try:
    from .admin_window import AdminWindow
    from .attendance_viewer_widget import AttendanceViewerWidget
    from .camera_selector_widget import CameraSelectorWidget
    from .scanner_widget import ScannerWidget
    from .ip_webcam_widget import IPWebcamWidget
    from .camera_preview_widget import CameraPreviewWidget, MaximizedCameraWindow
    from .attendance_analysis import AttendanceAnalyticsDialog
    from .admin_profile_dialog import AdminProfileDialog
    from .database import get_attendance_logs_by_date, get_attendance_summary_last_days
except ImportError:
    from admin_window import AdminWindow
    from attendance_viewer_widget import AttendanceViewerWidget
    from camera_selector_widget import CameraSelectorWidget
    from scanner_widget import ScannerWidget
    from ip_webcam_widget import IPWebcamWidget
    from camera_preview_widget import CameraPreviewWidget, MaximizedCameraWindow
    from attendance_analysis import AttendanceAnalyticsDialog
    from database import get_attendance_logs_by_date, get_attendance_summary_last_days


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('Face Recognition Attendance System')
        self.setStyleSheet("QMainWindow { background-color: gray; }")

        self.attendance_time_format = '24-hour'
        self.entry_time_options = [f'{h:02d}:00' for h in range(24)]
        self.late_time_options = [f'{h:02d}:00' for h in range(24)]
        self.exit_time_options = [f'{h:02d}:00' for h in range(24)]
        self.selected_entry_time = '09:00'
        self.selected_late_time = '10:00'
        self.selected_exit_time = '17:00'
        self.attendance_current_records = []
        self.attendance_search_date = None

        self.available_camera_items = []
        self.active_cameras = []
        self.camera_filter = 'Auto detect cameras'
        self.active_camera_previews = {}  # camera_name -> CameraPreviewWidget
        self.maximized_windows = {}  # camera_name -> MaximizedCameraWindow
        self._build_ui()
        self._populate_camera_list()
        self._populate_attendance()

    def _build_ui(self):

        central_widget = QWidget()
        central_widget.setStyleSheet('background-color: #8DAEB1;')
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)

        header_label = QLabel('Face Recognition Attendance System')
        header_label.setStyleSheet('background-color: #8DAEB1; font-size: 20px; font-weight: bold; color: #1f1f1f;')
        header_label.setAlignment(Qt.AlignCenter)

        time_settings_section = QWidget()
        time_settings_section.setStyleSheet('background-color: #8DAEB1;')
        time_settings_layout = QHBoxLayout(time_settings_section)
        time_settings_layout.setContentsMargins(0, 0, 0, 0)
        time_settings_layout.setSpacing(10)

        time_settings_layout.addWidget(QLabel('Entry time:'))
        self.entry_time_combo = QComboBox()
        self.entry_time_combo.setMinimumWidth(100)
        self.entry_time_combo.addItems(self.entry_time_options)
        self.entry_time_combo.setCurrentText(self.selected_entry_time)
        self.entry_time_combo.setStyleSheet('color:black; background-color: #BCEDBB; padding: 6px; border-radius: 4px;')
        time_settings_layout.addWidget(self.entry_time_combo)

        time_settings_layout.addWidget(QLabel('Late time:'))
        self.late_time_combo = QComboBox()
        self.late_time_combo.setMinimumWidth(100)
        self.late_time_combo.addItems(self.late_time_options)
        self.late_time_combo.setCurrentText(self.selected_late_time)
        self.late_time_combo.setStyleSheet('color:black; background-color: #BCEDBB; padding: 6px; border-radius: 4px;')
        time_settings_layout.addWidget(self.late_time_combo)

        time_settings_layout.addWidget(QLabel('Exit time:'))
        self.exit_time_combo = QComboBox()
        self.exit_time_combo.setMinimumWidth(100)
        self.exit_time_combo.addItems(self.exit_time_options)
        self.exit_time_combo.setCurrentText(self.selected_exit_time)
        self.exit_time_combo.setStyleSheet('color:black; background-color: #BCEDBB; padding: 6px; border-radius: 4px;')
        time_settings_layout.addWidget(self.exit_time_combo)

        time_format_label = QLabel(f'Time format: {self.attendance_time_format}')
        time_format_label.setStyleSheet('font-size: 13px; font-weight: 600; color: #1f1f1f;')
        time_settings_layout.addWidget(time_format_label)
        time_settings_layout.addStretch()

        button_section = QWidget()
        button_section.setStyleSheet(
            'background-color: #8DAEB1; border-radius: 24px; padding: 18px;'
        )
        button_grid = QGridLayout(button_section)
        button_grid.setSpacing(18)
        button_grid.setContentsMargins(16, 16, 16, 16)

        self.candidate_record_btn = QPushButton('candidate records')
        self.attendance_record_btn = QPushButton('attendance records')
        self.admin_scan_btn = QPushButton('Scan via admin camera')
        self.phone_scan_btn = QPushButton('Scan via phone')
        self.cctv_scan_btn = QPushButton('scan via cctv')
        self.attendance_analysis_btn = QPushButton('attendance analysis')
        self.attendance_analysis_btn.setEnabled(True)
        self.attendance_analysis_btn.setToolTip('View attendance analytics and metrics')

        for button in [
            self.candidate_record_btn,
            self.attendance_record_btn,
            self.admin_scan_btn,
            self.attendance_analysis_btn,
            self.cctv_scan_btn,
            self.phone_scan_btn,
        ]:
            button.setMinimumHeight(60)
            button.setStyleSheet(
                'QPushButton { background-color: #BCEDBB; color: #1f1f1f; border: none; '
                'border-radius: 30px; font-size: 14px; font-weight: 600; padding: 12px 24px; }'
                'QPushButton:disabled { background-color: #f5c7b1; color: #8a8a8a; }'
                'QPushButton:hover:!disabled { background-color: #ffb99a; }'
            )

        button_grid.addWidget(self.candidate_record_btn, 0, 0)
        button_grid.addWidget(self.attendance_record_btn, 0, 1)
        button_grid.addWidget(self.admin_scan_btn, 1, 0)
        button_grid.addWidget(self.attendance_analysis_btn, 1, 1)
        button_grid.addWidget(self.cctv_scan_btn, 2, 0)
        button_grid.addWidget(self.phone_scan_btn, 2, 1)

        main_layout.addWidget(header_label)
        main_layout.addWidget(time_settings_section)
        main_layout.addWidget(button_section)

        self.candidate_record_btn.clicked.connect(lambda: self.open_admin(0))
        # Restore original behavior: open AdminWindow on attendance tab so
        # the existing date selector and attendance controls remain available.
        self.attendance_record_btn.clicked.connect(lambda: self.open_admin(1))
        self.admin_scan_btn.clicked.connect(self.open_scanner)
        self.phone_scan_btn.clicked.connect(self.open_phone_scanner)
        self.cctv_scan_btn.clicked.connect(self.open_cctv_scanner)
        self.attendance_analysis_btn.clicked.connect(self.open_attendance_analysis)

        # Compatibility with original launcher code
        self.scan_btn = self.admin_scan_btn

        self._build_docks()
        self._build_status_bar()
        self.resize(1200, 800)

    def _build_docks(self):
        self._build_attendance_dock()
        self._build_camera_dock()

    def _build_attendance_dock(self):
        screen_geom = QApplication.primaryScreen().availableGeometry()
        bottom_min_height = max(340, screen_geom.height() // 2)

        attendance_container = QWidget()
        attendance_container.setStyleSheet('background-color: #BCEDBB;')
        attendance_layout = QVBoxLayout(attendance_container)
        attendance_layout.setContentsMargins(12, 12, 12, 12)
        attendance_layout.setSpacing(10)

        self.attendance_header_label = QLabel('Last 7 days attendance')
        self.attendance_header_label.setStyleSheet('color: #000000; font-size: 14px; font-weight: 700;')
        attendance_layout.addWidget(self.attendance_header_label)

        attendance_filter_row = QWidget()
        attendance_filter_row.setStyleSheet('background-color: transparent;')
        attendance_filter_layout = QHBoxLayout(attendance_filter_row)
        attendance_filter_layout.setContentsMargins(0, 0, 0, 0)
        attendance_filter_layout.setSpacing(10)

        refresh_btn = QPushButton('Refresh')
        refresh_btn.setMinimumHeight(40)
        refresh_btn.setStyleSheet('QPushButton { background-color: #2196F3; color: white; border: none; border-radius: 20px; padding: 8px 16px; } QPushButton:hover { background-color: #0b7dda; }')
        refresh_btn.clicked.connect(self._refresh_attendance_table)
        attendance_filter_layout.addWidget(refresh_btn)

        self.auto_refresh_label = QLabel('Auto-refresh every 60 seconds')
        self.auto_refresh_label.setStyleSheet('color: #333; font-size: 12px;')
        attendance_filter_layout.addWidget(self.auto_refresh_label)
        attendance_filter_layout.addStretch()
        attendance_layout.addWidget(attendance_filter_row)

        self.attendance_tab_widget = QTabWidget()
        self.attendance_tab_widget.setStyleSheet(
            "QTabWidget::pane { background: #f7fff3; border: 1px solid #c9dec1; }"
            "QTabBar::tab { background: #BCEDBB; color:black; padding: 8px 16px; border: 1px solid #c9dec1; border-bottom: none; }"
            "QTabBar::tab:selected { background: #e7f5d8; color: blue; margin-bottom: -1px; }"
        )
        self.attendance_tab_widget.currentChanged.connect(self._attendance_tab_changed)

        self.attendance_dates = [date.today() - timedelta(days=i) for i in range(6, -1, -1)]
        self.attendance_tables = []
        for attendance_date in self.attendance_dates:
            page = QWidget()
            page_layout = QVBoxLayout(page)
            page_layout.setContentsMargins(0, 0, 0, 0)
            page_layout.setSpacing(0)

            table = QTableWidget(0, 7)
            table.setStyleSheet('background: #eaf9d8; color:black; border: 1px solid #dde7d3;')
            table.setHorizontalHeaderLabels([
                'Candidate ID', 'Name', 'Timestamp', 'Type', 'Status', 'Snapshot Path', 'View'
            ])

            table.setAlternatingRowColors(True)
            table.verticalHeader().setVisible(False)

            # --- HEADER OPTIMIZATION ---
            header = table.horizontalHeader()

            # 1. Set a standard global minimum section size (e.g., 150px to 200px) 
            # instead of checking DPI manually.
            header.setMinimumSectionSize(150)

            # 2. Tell specific columns how to behave using ResizeMode
            # Let columns 0 to 4 resize automatically based on their text content
            for col in range(5):
                header.setSectionResizeMode(col, QHeaderView.ResizeToContents)

            # 3. Explicitly set your 2nd last column ('Snapshot Path', index 5) to a fixed width.
            # In standard UI design, ~300 pixels perfectly represents roughly 3 inches on standard displays.
            header.setSectionResizeMode(5, QHeaderView.Interactive) # allows user to tweak it if needed
            table.setColumnWidth(5, 500) 

            # 4. Stretch the last section ('View') to fill up whatever empty space is left over
            header.setStretchLastSection(True)

            page_layout.addWidget(table)

            label = 'Today' if attendance_date == date.today() else 'Yesterday' if attendance_date == date.today() - timedelta(days=1) else attendance_date.strftime('%a %d %b')
            self.attendance_tab_widget.addTab(page, label)
            self.attendance_tables.append(table)

        attendance_layout.addWidget(self.attendance_tab_widget)

        self.attendance_summary = QLabel('Attendance summary for the selected day')
        self.attendance_summary.setWordWrap(True)
        self.attendance_summary.setStyleSheet('color: #333; font-size: 12px;')
        attendance_layout.addWidget(self.attendance_summary)

        self.attendance_dock = QDockWidget('Attendance Records', self)
        self.attendance_dock.setWidget(attendance_container)
        self.attendance_dock.setAllowedAreas(Qt.BottomDockWidgetArea)
        self.attendance_dock.setMinimumHeight(bottom_min_height)
        self.attendance_dock.setStyleSheet(
            'QDockWidget::title { background-color: #9EBC9D; padding: 8px; }'
            'QDockWidget { background-color: #BCEDBB; }'
        )
        self.addDockWidget(Qt.BottomDockWidgetArea, self.attendance_dock)

        self.attendance_refresh_timer = QTimer(self)
        self.attendance_refresh_timer.timeout.connect(self._refresh_attendance_table)
        self.attendance_refresh_timer.start(60_000)

    def _build_camera_dock(self):
        screen_geom = QApplication.primaryScreen().availableGeometry()
        right_min_width = max(520, screen_geom.width() // 2)

        cameras_container = QWidget()
        cameras_container.setStyleSheet('background-color: #8DAEB1;')
        cameras_layout = QVBoxLayout(cameras_container)
        cameras_layout.setContentsMargins(3, 3, 3, 3)
        cameras_layout.setSpacing(7)

        camera_selector_layout = QHBoxLayout()
        camera_selector_layout.addWidget(QLabel('Select camera:'))
        self.camera_combo = QComboBox()
        self.camera_combo.setStyleSheet("color:black; background-color: #BCEDBB; border: 1px solid #c9dec1; padding: 6px; border-radius: 4px;")
        self.camera_combo.setEditable(False)
        self.camera_combo.addItem('Auto detect cameras')
        self.camera_combo.currentIndexChanged.connect(self._camera_combo_changed)
        camera_selector_layout.addWidget(self.camera_combo)
        camera_selector_layout.addStretch()
        cameras_layout.addLayout(camera_selector_layout)

        self.camera_status = QLabel('Ready for scanning')
        self.camera_status.setStyleSheet('font-size: 11px; color: #666;')
        cameras_layout.addWidget(self.camera_status)

        self.cameras_scroll = QScrollArea()
        self.cameras_scroll.setWidgetResizable(True)
        self.cameras_scroll.setStyleSheet('QScrollArea { border: none; background-color: transparent; }')

        self.cameras_grid_widget = QWidget()
        self.cameras_grid_layout = QGridLayout(self.cameras_grid_widget)
        self.cameras_grid_layout.setContentsMargins(0, 0, 0, 0)
        self.cameras_grid_layout.setSpacing(10)

        self.cameras_scroll.setWidget(self.cameras_grid_widget)
        cameras_layout.addWidget(self.cameras_scroll)

        self.camera_grid_positions = [(row, col) for row in range(2) for col in range(4)]
        self.camera_slot_widgets = []
        for idx, (row, col) in enumerate(self.camera_grid_positions):
            placeholder = self._create_camera_placeholder(idx + 1)
            self.camera_slot_widgets.append(placeholder)
            self.cameras_grid_layout.addWidget(placeholder, row, col)

        self.cameras_dock = QDockWidget('Camera Section', self)
        self.cameras_dock.setStyleSheet(
            'QDockWidget::title { background-color: #8DAEB1; padding: 8px; }'
            'QDockWidget { background-color: #BCEDBB; }'
        )
        self.cameras_dock.setWidget(cameras_container)
        self.cameras_dock.setAllowedAreas(Qt.RightDockWidgetArea)
        self.cameras_dock.setMinimumWidth(right_min_width)
        self.addDockWidget(Qt.RightDockWidgetArea, self.cameras_dock)

    def _build_status_bar(self):
        self.status_bar = QStatusBar(self)
        self.setStatusBar(self.status_bar)
        # Admin profile button (left side)
        self.admin_profile_btn = QPushButton('👤')
        self.admin_profile_btn.setToolTip('Admin profile')
        self.admin_profile_btn.setMinimumHeight(26)
        self.admin_profile_btn.setMaximumWidth(40)
        self.admin_profile_btn.clicked.connect(self.open_admin_profile)
        self.status_bar.addWidget(self.admin_profile_btn)

        self.toggle_attendance_btn = QPushButton('Toggle Attendance Panel')
        self.toggle_camera_btn = QPushButton('Toggle Cameras Panel')
        self.toggle_attendance_btn.clicked.connect(self._toggle_attendance_dock)
        self.toggle_camera_btn.clicked.connect(self._toggle_camera_dock)

        self.status_bar.addPermanentWidget(self.toggle_attendance_btn)
        self.status_bar.addPermanentWidget(self.toggle_camera_btn)

    def open_admin_profile(self):
        try:
            dlg = AdminProfileDialog(self)
            dlg.exec()
        except Exception as e:
            QMessageBox.warning(self, 'Profile Error', f'Unable to open admin profile: {e}')

    def _populate_camera_list(self):
        self.available_camera_items = []
        try:
            for idx in range(8):
                cap = cv2.VideoCapture(idx, cv2.CAP_DSHOW)
                if cap is not None and cap.isOpened():
                    self.available_camera_items.append(f'Camera {idx}')
                    cap.release()
                else:
                    if cap is not None:
                        cap.release()
        except Exception:
            pass

        if not self.available_camera_items:
            self.available_camera_items.append('No cameras detected')

        self._update_camera_filter_combo()

    def _update_camera_filter_combo(self):
        current_selection = self.camera_filter
        self.camera_combo.blockSignals(True)
        self.camera_combo.clear()
        self.camera_combo.addItem('Auto detect cameras')
        for item in self.available_camera_items:
            self.camera_combo.addItem(item)
        for item in self.active_cameras:
            if item not in self.available_camera_items:
                self.camera_combo.addItem(item)

        index = self.camera_combo.findText(current_selection)
        if index >= 0:
            self.camera_combo.setCurrentIndex(index)
        else:
            self.camera_combo.setCurrentIndex(0)
            self.camera_filter = 'Auto detect cameras'
        self.camera_combo.blockSignals(False)

    def _camera_combo_changed(self, index):
        self.camera_filter = self.camera_combo.itemText(index)

    def _create_camera_placeholder(self, slot_number: int):
        placeholder = QFrame()
        placeholder.setProperty('slot_type', 'placeholder')
        placeholder.setStyleSheet(
            'QFrame { background-color: #1f1f1f; border: 1px dashed #555; border-radius: 8px; }'
        )
        placeholder_layout = QVBoxLayout(placeholder)
        placeholder_layout.setContentsMargins(10, 10, 10, 10)
        placeholder_layout.setSpacing(4)
        placeholder_layout.addStretch()

        label = QLabel(f'Camera Slot {slot_number}')
        label.setStyleSheet('color: #ccc; font-weight: bold;')
        label.setAlignment(Qt.AlignCenter)
        placeholder_layout.addWidget(label)

        hint = QLabel('Start a scan to populate this slot')
        hint.setStyleSheet('color: #888; font-size: 11px;')
        hint.setAlignment(Qt.AlignCenter)
        placeholder_layout.addWidget(hint)
        placeholder_layout.addStretch()
        return placeholder

    def _find_free_camera_slot(self):
        for idx, widget in enumerate(self.camera_slot_widgets):
            if widget.property('slot_type') == 'placeholder':
                return idx
        return None

    def _add_camera_preview(self, camera_name: str):
        """Add a camera preview widget to the dock."""
        if camera_name in self.active_camera_previews:
            return

        preview = CameraPreviewWidget(camera_name)
        preview.camera_closed.connect(self._on_camera_preview_closed)
        preview.camera_maximized.connect(self._on_camera_preview_maximized)

        self.active_camera_previews[camera_name] = preview
        slot_index = self._find_free_camera_slot()
        if slot_index is None:
            slot_index = len(self.camera_slot_widgets)
            self.camera_slot_widgets.append(preview)
            row = slot_index // 4
            col = slot_index % 4
            self.cameras_grid_layout.addWidget(preview, row, col)
        else:
            old_widget = self.camera_slot_widgets[slot_index]
            self.cameras_grid_layout.removeWidget(old_widget)
            old_widget.setParent(None)
            self.camera_slot_widgets[slot_index] = preview
            row, col = self.camera_grid_positions[slot_index]
            self.cameras_grid_layout.addWidget(preview, row, col)

        self.camera_status.setText(f'Scanning: {", ".join(self.active_cameras)}')

    def _remove_camera_preview(self, camera_name: str):
        """Remove a camera preview widget from the dock."""
        if camera_name not in self.active_camera_previews:
            return

        preview = self.active_camera_previews.pop(camera_name)
        slot_index = next(
            (idx for idx, widget in enumerate(self.camera_slot_widgets) if widget is preview),
            None,
        )
        if slot_index is not None:
            self.cameras_grid_layout.removeWidget(preview)
            preview.setParent(None)
            placeholder = self._create_camera_placeholder(slot_index + 1)
            self.camera_slot_widgets[slot_index] = placeholder
            row, col = self.camera_grid_positions[slot_index]
            self.cameras_grid_layout.addWidget(placeholder, row, col)

        if self.active_cameras:
            self.camera_status.setText(f'Scanning: {", ".join(self.active_cameras)}')
        else:
            self.camera_status.setText('Ready for scanning')

    def _set_active_camera(self, camera_name: str):
        """Called when a camera starts scanning."""
        if camera_name not in self.active_cameras:
            self.active_cameras.append(camera_name)
        self._add_camera_preview(camera_name)
        self._update_camera_filter_combo()

    def _clear_active_camera(self, camera_name: str | None = None):
        """Called when a camera stops scanning."""
        if camera_name is None:
            cameras_to_remove = list(self.active_cameras)
            self.active_cameras.clear()
            for cam_name in cameras_to_remove:
                self._remove_camera_preview(cam_name)
        elif camera_name in self.active_cameras:
            self.active_cameras.remove(camera_name)
            self._remove_camera_preview(camera_name)
        self._update_camera_filter_combo()

    def _on_camera_preview_closed(self, camera_name: str):
        """Handle camera preview close button click."""
        self._clear_active_camera(camera_name)

    def _on_camera_preview_maximized(self, camera_name: str):
        """Handle camera preview maximize button click."""
        if camera_name not in self.maximized_windows:
            window = MaximizedCameraWindow(camera_name, self)
            window.camera_closed.connect(lambda: self._close_maximized_window(camera_name))
            self.maximized_windows[camera_name] = window
            window.show()

    def _close_maximized_window(self, camera_name: str):
        """Close a maximized camera window."""
        if camera_name in self.maximized_windows:
            window = self.maximized_windows.pop(camera_name)
            window.close()

    def _populate_attendance(self):
        self.attendance_tab_widget.setCurrentIndex(len(self.attendance_dates) - 1)
        self._load_attendance_data_for_tab(self.attendance_tab_widget.currentIndex())

    def _attendance_tab_changed(self, index: int):
        if 0 <= index < len(self.attendance_tables):
            self._load_attendance_data_for_tab(index)

    def _fill_attendance_table(self, records):
        target_table = self.attendance_tables[self.attendance_tab_widget.currentIndex()]
        target_table.setRowCount(len(records))
        for row, (_, candidate_id, candidate_name, log_time, log_type, status, snapshot_path) in enumerate(records):
            target_table.setItem(row, 0, QTableWidgetItem(candidate_id))
            target_table.setItem(row, 1, QTableWidgetItem(candidate_name))
            target_table.setItem(row, 2, QTableWidgetItem(log_time))
            # For absent rows the helper returns a date-only timestamp (YYYY-MM-DD).
            # Leave the "Type" column blank for absent candidates instead of showing 'Unknown'.
            is_absent = isinstance(log_time, str) and len(log_time) == 10 and log_time.count('-') == 2
            target_table.setItem(row, 3, QTableWidgetItem('' if is_absent else (log_type or 'Unknown')))
            target_table.setItem(row, 4, QTableWidgetItem(status or 'Unknown'))
            target_table.setItem(row, 5, QTableWidgetItem(snapshot_path or ''))

            view_btn = QPushButton('View')
            view_btn.setEnabled(bool(snapshot_path))
            view_btn.setStyleSheet(
                'QPushButton { background-color: #1976d2; color: white; border: none; '
                'border-radius: 10px; padding: 4px 10px; } '
                'QPushButton:hover { background-color: #155fa0; }'
            )
            target_table.setCellWidget(row, 6, view_btn)

        self.attendance_current_records = records

    def _load_attendance_data_for_tab(self, index: int):
        self.attendance_search_date = self.attendance_dates[index].isoformat()
        try:
            from .database import get_attendance_with_absent
            records = get_attendance_with_absent(self.attendance_search_date)
        except Exception:
            # fallback to legacy function
            records = get_attendance_logs_by_date(self.attendance_search_date)

        self._fill_attendance_table(records)

        # Compute present/absent using registered candidates (exclude unknowns)
        try:
            from .database import get_all_candidates
        except Exception:
            from database import get_all_candidates

        try:
            all_candidates = get_all_candidates()
        except Exception:
            all_candidates = []

        total_registered = len([cid for cid, *_ in all_candidates if cid and not str(cid).startswith('unknown')])
        present_candidates = {candidate_id for _, candidate_id, _, _, _, _, _ in records if candidate_id and not str(candidate_id).startswith('unknown')}
        present_count = len(present_candidates)
        absent_count = max(0, total_registered - present_count)

        summary_lines = [f'Total Present Candidates {self.attendance_search_date}: {present_count}']
        summary_lines.append(f'Total Absent candidates: {absent_count}')
        self.attendance_summary.setText('\n'.join(summary_lines))
        self.attendance_header_label.setText(f'Attendance for {self.attendance_dates[index].strftime("%a %d %b")}')

    def _refresh_attendance_table(self):
        current_tab_index = self.attendance_tab_widget.currentIndex()
        self._load_attendance_data_for_tab(current_tab_index)

    def _toggle_attendance_dock(self):
        visible = not self.attendance_dock.isVisible()
        self.attendance_dock.setVisible(visible)

    def _toggle_camera_dock(self):
        visible = not self.cameras_dock.isVisible()
        self.cameras_dock.setVisible(visible)

    def open_admin(self, tab_index: int = 0):
        """Open admin window with candidate or attendance records.
        
        Args:
            tab_index: 0 for candidate records, 1 for attendance records
        """
        if not hasattr(self, 'admin_window') or self.admin_window is None:
            self.admin_window = AdminWindow()
        
        # Use setCurrentIndex for backward compatibility
        self.admin_window.setCurrentIndex(tab_index)

    def open_scanner(self):
        self.camera_selector = CameraSelectorWidget(
            on_open_laptop=self._open_scanner_window,
            on_open_phone=self.open_phone_scanner,
        )
        self.camera_selector.show()

    def _open_scanner_window(self, index=0, name='Laptop camera'):
        self.scanner = ScannerWidget(
            entry_time=self.entry_time_combo.currentText(),
            late_time=self.late_time_combo.currentText(),
            exit_time=self.exit_time_combo.currentText(),
        )
        self.scanner.camera_index = index
        self.scanner.camera_name = name
        self.scanner.camera_started.connect(self._on_scanner_started)
        self.scanner.camera_stopped.connect(self._clear_active_camera)
        self.scanner.frame_captured.connect(self._on_scanner_frame)
        self.scanner.show()
        self.scanner.start_camera()

    def _on_scanner_started(self, camera_name: str):
        """Called when laptop camera starts."""
        self._set_active_camera(camera_name)

    def _on_scanner_frame(self, frame):
        """Update camera preview with frame from scanner."""
        if hasattr(self, 'scanner') and self.scanner.camera_name in self.active_camera_previews:
            self.active_camera_previews[self.scanner.camera_name].update_frame(frame)
            self.active_camera_previews[self.scanner.camera_name].set_scanning(True)
            # Update maximized window if open
            if self.scanner.camera_name in self.maximized_windows:
                self.maximized_windows[self.scanner.camera_name].update_frame(frame)

    def open_phone_scanner(self):
        self.phone_scanner = IPWebcamWidget(
            entry_time=self.entry_time_combo.currentText(),
            late_time=self.late_time_combo.currentText(),
            exit_time=self.exit_time_combo.currentText(),
            mode='phone',
        )
        self.phone_scanner.camera_started.connect(self._on_phone_scanner_started)
        self.phone_scanner.camera_stopped.connect(self._clear_active_camera)
        self.phone_scanner.frame_captured.connect(self._on_phone_scanner_frame)
        self.phone_scanner.show()

    def _on_phone_scanner_started(self, camera_name: str):
        """Called when phone camera starts."""
        self._set_active_camera(camera_name)

    def _on_phone_scanner_frame(self, frame):
        """Update camera preview with frame from phone scanner."""
        if hasattr(self, 'phone_scanner') and self.phone_scanner.camera_name in self.active_camera_previews:
            self.active_camera_previews[self.phone_scanner.camera_name].update_frame(frame)
            self.active_camera_previews[self.phone_scanner.camera_name].set_scanning(True)
            # Update maximized window if open
            if self.phone_scanner.camera_name in self.maximized_windows:
                self.maximized_windows[self.phone_scanner.camera_name].update_frame(frame)

    def open_cctv_scanner(self):
        self.cctv_scanner = IPWebcamWidget(
            entry_time=self.entry_time_combo.currentText(),
            late_time=self.late_time_combo.currentText(),
            exit_time=self.exit_time_combo.currentText(),
            mode='cctv',
        )
        self.cctv_scanner.camera_started.connect(self._on_cctv_scanner_started)
        self.cctv_scanner.camera_stopped.connect(self._clear_active_camera)
        self.cctv_scanner.frame_captured.connect(self._on_cctv_scanner_frame)
        self.cctv_scanner.show()

    def _on_cctv_scanner_started(self, camera_name: str):
        """Called when CCTV camera starts."""
        self._set_active_camera(camera_name)

    def _on_cctv_scanner_frame(self, frame):
        """Update camera preview with frame from CCTV scanner."""
        if hasattr(self, 'cctv_scanner') and self.cctv_scanner.camera_name in self.active_camera_previews:
            self.active_camera_previews[self.cctv_scanner.camera_name].update_frame(frame)
            self.active_camera_previews[self.cctv_scanner.camera_name].set_scanning(True)
            # Update maximized window if open
            if self.cctv_scanner.camera_name in self.maximized_windows:
                self.maximized_windows[self.cctv_scanner.camera_name].update_frame(frame)

    def open_attendance_analysis(self):
        """Open the attendance analytics dashboard."""
        self.analytics_window = AttendanceAnalyticsDialog(self)
        self.analytics_window.show()

    def open_attendance_viewer(self):
        self.attendance_window = AttendanceViewerWidget()
        self.attendance_window.show()
