"""Camera source selector and unified scanner interface."""
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QPushButton, QLabel
)

import cv2
from .scanner_widget import ScannerWidget


class CameraSelectorWidget(QWidget):
    """Let user choose between laptop camera and IP Webcam."""
    def __init__(self, on_open_laptop=None, on_open_phone=None):
        super().__init__()
        self.on_open_laptop = on_open_laptop
        self.on_open_phone = on_open_phone
        self.setWindowTitle('Select Camera Source')
        self.setMinimumWidth(600)
        self.setMinimumHeight(500)
        self._build_ui()

    def _build_ui(self):
        main_layout = QVBoxLayout()

        # Title
        title = QLabel('Select Camera Source')
        title.setStyleSheet("font-size: 16px; font-weight: bold;")
        main_layout.addWidget(title)

        # Info
        info = QLabel(
            'Choose which camera to use for face scanning:\n'
            'Detected local camera devices are listed below.'
        )
        info.setWordWrap(True)
        main_layout.addWidget(info)

        # Buttons
        # Detect available local cameras and add a button per device
        camera_list = self._detect_cameras()
        for idx, name in camera_list:
            btn = QPushButton(f'📷 {name} (index {idx})')
            btn.setMinimumHeight(56)
            # bind index into lambda default arg
            btn.clicked.connect(lambda _, i=idx, n=name: self._open_camera(i, n))
            main_layout.addWidget(btn)

        if not camera_list:
            # fallback single laptop button
            self.laptop_btn = QPushButton('📷 Use Laptop Camera (index 0)')
            self.laptop_btn.setMinimumHeight(60)
            self.laptop_btn.clicked.connect(lambda: self._open_camera(0, 'Laptop camera'))
            main_layout.addWidget(self.laptop_btn)
        main_layout.addStretch()

        self.setLayout(main_layout)

    def _open_laptop(self):
        # kept for compatibility; open default index 0
        self._open_camera(0, 'Laptop camera')

    def _open_phone(self):
        # Phone option removed from this selector by design.
        if self.on_open_phone:
            self.on_open_phone()
        self.close()

    def _open_camera(self, index: int, name: str):
        if self.on_open_laptop:
            # if external handler provided, call it with the selected camera
            try:
                self.on_open_laptop(index, name)
            except TypeError:
                self.on_open_laptop()
            self.close()
            return

        self.scanner = ScannerWidget()
        self.scanner.camera_index = index
        self.scanner.camera_name = name
        self.scanner.show()
        # Start capturing immediately
        try:
            self.scanner.start_camera()
        except Exception:
            pass
        self.close()

    def _detect_cameras(self, max_check=5):
        """Probe local camera indices and return list of (index, friendly_name)."""
        found = []
        for i in range(max_check):
            cap = cv2.VideoCapture(i, cv2.CAP_DSHOW)
            if not cap.isOpened():
                cap.release()
                cap = cv2.VideoCapture(i, cv2.CAP_MSMF)
            if not cap.isOpened():
                cap.release()
                cap = cv2.VideoCapture(i, cv2.CAP_ANY)
            if not cap.isOpened():
                cap.release()
                continue

            # attempt to grab one frame to verify
            ret, _ = cap.read()
            cap.release()
            if ret:
                # label first detected as front, others as external
                label = 'Front camera' if not found else f'External camera {len(found)}'
                found.append((i, label))
        return found
