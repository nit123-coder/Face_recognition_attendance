"""Live camera preview widget for the right dock panel."""
from PySide6.QtWidgets import (
    QWidget, QLabel, QPushButton, QVBoxLayout, QHBoxLayout,
    QDialog, QApplication
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QImage, QPixmap
import numpy as np


class CameraPreviewWidget(QWidget):
    """Single camera preview with live feed, close, and maximize buttons."""
    
    camera_closed = Signal(str)  # Emits camera name when closed
    camera_maximized = Signal(str)  # Emits camera name when maximized

    def __init__(self, camera_name: str, camera_index: int = 0, is_phone: bool = False):
        super().__init__()
        self.camera_name = camera_name
        self.camera_index = camera_index
        self.is_phone = is_phone
        self.is_maximized = False
        self.setStyleSheet("""
            CameraPreviewWidget {
                border: 2px solid #333;
                border-radius: 8px;
                background-color: #1e1e1e;
            }
        """)
        self._build_ui()

    def _build_ui(self):
        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(8, 8, 8, 8)
        main_layout.setSpacing(6)

        # Header with camera name and controls
        header_layout = QHBoxLayout()
        self.camera_label = QLabel(self.camera_name)
        self.camera_label.setStyleSheet("font-weight: bold; color: white; font-size: 12px;")
        header_layout.addWidget(self.camera_label)
        header_layout.addStretch()

        # Close button
        self.close_btn = QPushButton('✕')
        self.close_btn.setMaximumWidth(32)
        self.close_btn.setMaximumHeight(28)
        self.close_btn.setStyleSheet("""
            QPushButton {
                background-color: #d32f2f;
                color: white;
                border: none;
                border-radius: 4px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #f44336;
            }
        """)
        self.close_btn.clicked.connect(self._on_close)
        header_layout.addWidget(self.close_btn)

        # Maximize button
        self.maximize_btn = QPushButton('⛶')
        self.maximize_btn.setMaximumWidth(32)
        self.maximize_btn.setMaximumHeight(28)
        self.maximize_btn.setStyleSheet("""
            QPushButton {
                background-color: #1976d2;
                color: white;
                border: none;
                border-radius: 4px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #2196f3;
            }
        """)
        self.maximize_btn.clicked.connect(self._on_maximize)
        header_layout.addWidget(self.maximize_btn)

        main_layout.addLayout(header_layout)

        # Video preview label
        self.preview_label = QLabel('Waiting for camera...')
        self.preview_label.setAlignment(Qt.AlignCenter)
        self.preview_label.setMinimumSize(280, 210)
        self.preview_label.setMaximumSize(280, 210)
        self.preview_label.setStyleSheet("""
            QLabel {
                background-color: #000;
                color: #888;
                border-radius: 4px;
                font-size: 11px;
            }
        """)
        main_layout.addWidget(self.preview_label)

        # Status label
        self.status_label = QLabel('Not scanning')
        self.status_label.setStyleSheet("color: #aaa; font-size: 10px;")
        main_layout.addWidget(self.status_label)

        main_layout.addStretch()
        self.setLayout(main_layout)

    def update_frame(self, frame):
        """Update the preview with a new frame."""
        if frame is None:
            return

        h, w = frame.shape[:2]
        rgb_frame = frame if len(frame.shape) == 2 else frame[:, :, ::-1] if frame.shape[2] == 3 else frame[:, :, :3][:, :, ::-1]

        # Ensure contiguous memory for QImage buffer
        rgb_frame = np.ascontiguousarray(rgb_frame)

        bytes_per_line = w * 3 if len(rgb_frame.shape) == 3 else w
        qt_image = QImage(rgb_frame.data, w, h, bytes_per_line, QImage.Format.Format_RGB888)
        pixmap = QPixmap.fromImage(qt_image)
        scaled = pixmap.scaled(280, 210, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.preview_label.setPixmap(scaled)

    def set_status(self, status: str):
        """Update status label."""
        self.status_label.setText(status)

    def set_scanning(self, active: bool):
        """Update scanning state for visual feedback."""
        if active:
            self.status_label.setText('🔴 Scanning...')
            self.status_label.setStyleSheet("color: #ff5555; font-size: 10px; font-weight: bold;")
        else:
            self.status_label.setText('Not scanning')
            self.status_label.setStyleSheet("color: #aaa; font-size: 10px;")

    def _on_close(self):
        """Emit signal when close button is clicked."""
        self.camera_closed.emit(self.camera_name)

    def _on_maximize(self):
        """Emit signal when maximize button is clicked."""
        self.camera_maximized.emit(self.camera_name)


class MaximizedCameraWindow(QDialog):
    """Full-screen camera preview window."""
    
    camera_closed = Signal(str)

    def __init__(self, camera_name: str, parent=None):
        super().__init__(parent)
        self.camera_name = camera_name
        self.setWindowTitle(f'Camera: {camera_name} - Full View')
        self.setStyleSheet("""
            MaximizedCameraWindow {
                background-color: #1e1e1e;
            }
        """)
        self._build_ui()
        screen = QApplication.primaryScreen().availableGeometry()
        self.setGeometry(screen)

    def _build_ui(self):
        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(12, 12, 12, 12)
        main_layout.setSpacing(10)

        # Header
        header_layout = QHBoxLayout()
        self.title_label = QLabel(f'Camera: {self.camera_name}')
        self.title_label.setStyleSheet("font-size: 16px; font-weight: bold; color: white;")
        header_layout.addWidget(self.title_label)
        header_layout.addStretch()

        close_btn = QPushButton('Close (Esc)')
        close_btn.setStyleSheet("""
            QPushButton {
                background-color: #d32f2f;
                color: white;
                padding: 8px 16px;
                border: none;
                border-radius: 4px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #f44336;
            }
        """)
        close_btn.clicked.connect(self._on_close)
        header_layout.addWidget(close_btn)

        main_layout.addLayout(header_layout)

        # Full preview
        self.preview_label = QLabel('Waiting for camera...')
        self.preview_label.setAlignment(Qt.AlignCenter)
        self.preview_label.setStyleSheet("""
            QLabel {
                background-color: #000;
                color: #888;
                border-radius: 4px;
            }
        """)
        main_layout.addWidget(self.preview_label)

        self.setLayout(main_layout)

    def update_frame(self, frame):
        """Update the full preview with a new frame."""
        if frame is None:
            return

        h, w = frame.shape[:2]
        rgb_frame = frame if len(frame.shape) == 2 else frame[:, :, ::-1] if frame.shape[2] == 3 else frame[:, :, :3][:, :, ::-1]

        # Ensure contiguous memory for QImage buffer
        rgb_frame = np.ascontiguousarray(rgb_frame)

        bytes_per_line = w * 3 if len(rgb_frame.shape) == 3 else w
        qt_image = QImage(rgb_frame.data, w, h, bytes_per_line, QImage.Format.Format_RGB888)
        pixmap = QPixmap.fromImage(qt_image)
        screen_geom = QApplication.primaryScreen().availableGeometry()
        scaled = pixmap.scaledToHeight(screen_geom.height() - 100, Qt.SmoothTransformation)
        self.preview_label.setPixmap(scaled)

    def _on_close(self):
        """Close the window and emit signal."""
        self.camera_closed.emit(self.camera_name)
        self.close()

    def keyPressEvent(self, event):
        """Close on Escape key."""
        if event.key() == Qt.Key.Key_Escape:
            self._on_close()
        else:
            super().keyPressEvent(event)
