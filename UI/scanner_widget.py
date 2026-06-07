import os
import time
import cv2
import numpy as np

from pathlib import Path
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import QWidget, QLabel, QPushButton, QVBoxLayout, QHBoxLayout, QMessageBox
import numpy as np

from .face_matching_worker import FaceMatchingWorker

KNOWN_FACES_DIR = Path(__file__).parent.parent / 'known_faces'
ATTENDANCE_PHOTOS_DIR = Path(__file__).parent.parent / 'attendance_photos'
KNOWN_FACES_DIR.mkdir(parents=True, exist_ok=True)
ATTENDANCE_PHOTOS_DIR.mkdir(parents=True, exist_ok=True)


class ScannerWidget(QWidget):
    camera_started = Signal(str)
    camera_stopped = Signal(str)
    frame_captured = Signal(object)  # Emits frame for preview

    def __init__(self, entry_time: str = '09:00', late_time: str = '10:00', exit_time: str = '17:00'):
        super().__init__()
        self.setWindowTitle('Camera Scanner')
        self.camera = None
        self.camera_index = 0
        self.camera_name = f'Laptop camera {self.camera_index}'
        self.worker = None
        self.known_faces = []
        self.known_names = []
        self.face_recognition_available = False
        self.entry_time = entry_time
        self.late_time = late_time
        self.exit_time = exit_time

        self._build_ui()

    def _build_ui(self):
        self.preview_label = QLabel('Camera preview will appear here.')
        self.preview_label.setAlignment(Qt.AlignCenter)
        self.preview_label.setMinimumSize(640, 360)

        self.info_label = QLabel('Ready. Press Start to open the laptop camera.')
        self.info_label.setWordWrap(True)

        self.start_btn = QPushButton('Start Camera')
        self.stop_btn = QPushButton('Stop Camera')
        self.stop_btn.setEnabled(False)

        self.start_btn.clicked.connect(self.start_camera)
        self.stop_btn.clicked.connect(self.stop_camera)

        top_layout = QHBoxLayout()
        top_layout.addWidget(self.start_btn)
        top_layout.addWidget(self.stop_btn)

        main_layout = QVBoxLayout()
        main_layout.addWidget(self.preview_label)
        main_layout.addLayout(top_layout)
        main_layout.addWidget(self.info_label)
        self.setLayout(main_layout)
        self.resize(700, 520)

    def start_camera(self):
        if self.worker is not None:
            return

        self.worker = FaceMatchingWorker(
            camera_index=self.camera_index,
            entry_time=self.entry_time,
            late_time=self.late_time,
            exit_time=self.exit_time,
        )
        self.worker.frameReady.connect(self._show_image)
        self.worker.attendanceLogged.connect(self._on_attendance_logged)
        self.worker.unknownDetected.connect(self._on_unknown_detected)
        self.worker.warningRaised.connect(self._on_warning)
        self.worker.errorOccurred.connect(self._on_error)
        self.worker.start()

        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.info_label.setText('Camera started. Detecting faces...')
        self.camera_started.emit(self.camera_name)

    def _create_video_capture(self, index):
        """Create a VideoCapture with a backend fallback on Windows."""
        for backend in (cv2.CAP_DSHOW, cv2.CAP_MSMF, cv2.CAP_ANY):
            cap = cv2.VideoCapture(index, backend)
            if cap.isOpened():
                return cap
            cap.release()
        return None

    def stop_camera(self):
        if self.worker is not None:
            self.worker.stop()
            self.worker = None

        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.info_label.setText('Camera stopped.')
        self.preview_label.clear()
        self.preview_label.setText('Camera preview will appear here.')
        self.camera_stopped.emit(self.camera_name)

    def closeEvent(self, event):
        self.stop_camera()
        super().closeEvent(event)

    def _on_attendance_logged(self, candidate_id: str, candidate_name: str, log_type: str, status: str, snapshot_path: str):
        self.info_label.setText(f"{log_type} logged for {candidate_name} ({status})")

    def _on_unknown_detected(self, snapshot_path: str):
        # Removed popup for unknown detection per spec; update status line only
        self.info_label.setText("Unknown face detected and logged.")

    def _on_warning(self, message: str):
        QMessageBox.warning(self, "Attendance Warning", message)
        self.info_label.setText(message)

    def _on_error(self, message: str):
        QMessageBox.critical(self, "Camera Error", message)
        self.info_label.setText(message)

    def _save_detected_face(self, user_id: int, frame, face_location):
        top, right, bottom, left = face_location
        top = max(0, top)
        left = max(0, left)
        bottom = min(frame.shape[0], bottom)
        right = min(frame.shape[1], right)
        face_crop = frame[top:bottom, left:right]
        if face_crop.size == 0:
            return None

        user_dir = ATTENDANCE_PHOTOS_DIR / str(user_id)
        user_dir.mkdir(parents=True, exist_ok=True)
        file_name = f'{user_id}_{int(time.time())}.jpg'
        file_path = user_dir / file_name
        cv2.imwrite(str(file_path), face_crop)
        return str(file_path)

    def _show_image(self, frame):
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        # Ensure contiguous memory before creating QImage
        rgb = np.ascontiguousarray(rgb)
        h, w, ch = rgb.shape
        bytes_per_line = ch * w
        qt_image = QImage(rgb.data, w, h, bytes_per_line, QImage.Format.Format_RGB888)
        pixmap = QPixmap.fromImage(qt_image)
        scaled = pixmap.scaled(self.preview_label.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.preview_label.setPixmap(scaled)
        self.frame_captured.emit(rgb)  # Emit frame for dock preview
