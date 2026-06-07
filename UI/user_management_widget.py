"""User registration and face image management UI."""
import os
import platform
import shutil
import tempfile
import time
from pathlib import Path

import cv2
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import (
    QWidget, QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLineEdit, QLabel,
    QListWidget, QListWidgetItem, QFileDialog, QMessageBox, QInputDialog
)

from .database import (
    add_user, get_all_users, delete_user, add_face_image,
    get_face_images_for_user, delete_face_image, get_user_by_id
)

KNOWN_FACES_DIR = Path(__file__).parent.parent / 'known_faces'
KNOWN_FACES_DIR.mkdir(exist_ok=True)


class FaceCaptureDialog(QDialog):
    def __init__(self, parent, user_id: int, user_name: str):
        super().__init__(parent)
        self.user_id = user_id
        self.user_name = user_name
        self.setWindowTitle(f'Capture Face Photos for {user_name}')
        self.camera = None
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._update_frame)
        self.current_frame = None
        self.captured_count = 0
        self.max_photos = 3
        self._build_ui()
        self.start_camera()

    def _build_ui(self):
        layout = QVBoxLayout()

        self.preview_label = QLabel('Waiting for camera...')
        self.preview_label.setAlignment(Qt.AlignCenter)
        self.preview_label.setMinimumSize(640, 360)

        self.info_label = QLabel(
            'Camera preview is shown here. Capture three photos: center, slight left, slight right.\n'
            'You do not need exact angles — approximate turns are fine. Captured images are saved in raw orientation.'
        )
        self.info_label.setWordWrap(True)

        button_layout = QHBoxLayout()
        self.capture_btn = QPushButton('Capture Photo')
        self.close_btn = QPushButton('Close')
        self.capture_btn.clicked.connect(self._capture_photo)
        self.close_btn.clicked.connect(self.close)
        button_layout.addWidget(self.capture_btn)
        button_layout.addWidget(self.close_btn)

        layout.addWidget(self.preview_label)
        layout.addWidget(self.info_label)
        layout.addLayout(button_layout)
        self.setLayout(layout)
        self.resize(700, 520)

    def start_camera(self):
        # Use the default laptop/external webcam. If admin attaches an external camera,
        # that device may appear as camera index 1 or higher. For now we use index 0.
        self.camera = cv2.VideoCapture(0, cv2.CAP_DSHOW)
        if not self.camera.isOpened():
            self.info_label.setText('Unable to open camera. Check that the webcam is connected.')
            self.capture_btn.setEnabled(False)
            return

        self.capture_btn.setEnabled(True)
        self.timer.start(30)

    def closeEvent(self, event):
        self.stop_camera()
        super().closeEvent(event)

    def stop_camera(self):
        self.timer.stop()
        if self.camera is not None:
            self.camera.release()
            self.camera = None

    def _update_frame(self):
        if self.camera is None:
            return

        ret, frame = self.camera.read()
        if not ret or frame is None:
            self.info_label.setText('Cannot read from camera.')
            return

        self.current_frame = frame.copy()
        display_frame = cv2.flip(frame, 1)
        rgb = cv2.cvtColor(display_frame, cv2.COLOR_BGR2RGB)
        h, w, ch = rgb.shape
        bytes_per_line = ch * w
        qt_image = QImage(rgb.data, w, h, bytes_per_line, QImage.Format.Format_RGB888)
        pixmap = QPixmap.fromImage(qt_image)
        scaled = pixmap.scaled(self.preview_label.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.preview_label.setPixmap(scaled)

    def _capture_photo(self):
        if self.current_frame is None:
            QMessageBox.warning(self, 'No Image', 'No camera frame is currently available.')
            return
        # Determine automatic description based on sequence
        seq = self.captured_count
        default_desc = ['center', 'left', 'right']
        desc_label = default_desc[seq] if seq < len(default_desc) else f'photo_{seq+1}'
        description, ok = QInputDialog.getText(
            self, 'Description', f'Enter a short note for this photo (default: {desc_label}):', QLineEdit.Normal, desc_label
        )
        if not ok:
            return

        temp_path = Path(tempfile.gettempdir()) / f'capture_{self.user_id}_{int(time.time())}.jpg'
        cv2.imwrite(str(temp_path), self.current_frame)
        success = add_face_image(self.user_id, str(temp_path), description.strip())
        try:
            temp_path.unlink()
        except Exception:
            pass

        if success:
            self.captured_count += 1
            if self.captured_count >= self.max_photos:
                QMessageBox.information(self, 'Captured', 'All required photos captured (3).')
                self.capture_btn.setEnabled(False)
                self.info_label.setText('Captured 3 photos. Close the dialog to finish.')
            else:
                QMessageBox.information(self, 'Captured', f'Photo saved ({self.captured_count}/{self.max_photos}). Take the next pose.')
                self.info_label.setText(f'Captured {self.captured_count}/{self.max_photos}. Take next pose.')
        else:
            QMessageBox.warning(self, 'Error', 'Could not save the captured face image.')


class UserManagementWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('User Management')
        self.setMinimumWidth(600)
        self.setMinimumHeight(520)
        self._build_ui()
        self._load_users()

    def _build_ui(self):
        main_layout = QVBoxLayout()

        list_label = QLabel('Registered Users:')
        self.user_list = QListWidget()
        self.user_list.itemSelectionChanged.connect(self._on_user_selected)

        button_layout = QHBoxLayout()
        self.add_btn = QPushButton('Add User')
        self.upload_face_btn = QPushButton('Upload Face Photos')
        self.capture_face_btn = QPushButton('Capture Face Photos')
        self.view_face_btn = QPushButton('View Selected Photo')
        self.delete_btn = QPushButton('Delete User')

        self.add_btn.clicked.connect(self._add_user)
        self.upload_face_btn.clicked.connect(self._upload_face)
        self.capture_face_btn.clicked.connect(self._capture_face)
        self.view_face_btn.clicked.connect(self._view_face)
        self.delete_btn.clicked.connect(self._delete_user)

        self.upload_face_btn.setEnabled(False)
        self.capture_face_btn.setEnabled(False)
        self.view_face_btn.setEnabled(False)
        self.delete_btn.setEnabled(False)

        button_layout.addWidget(self.add_btn)
        button_layout.addWidget(self.upload_face_btn)
        button_layout.addWidget(self.capture_face_btn)
        button_layout.addWidget(self.view_face_btn)
        button_layout.addWidget(self.delete_btn)

        photo_label = QLabel('Saved Face Images:')
        self.photo_list = QListWidget()
        self.photo_list.itemSelectionChanged.connect(self._on_photo_selected)

        photo_button_layout = QHBoxLayout()
        self.delete_photo_btn = QPushButton('Delete Selected Photo')
        self.delete_photo_btn.clicked.connect(self._delete_face_image)
        self.delete_photo_btn.setEnabled(False)
        photo_button_layout.addWidget(self.delete_photo_btn)

        self.info_label = QLabel('Select a user to manage.')
        self.info_label.setWordWrap(True)

        main_layout.addWidget(list_label)
        main_layout.addWidget(self.user_list)
        main_layout.addLayout(button_layout)
        main_layout.addWidget(photo_label)
        main_layout.addWidget(self.photo_list)
        main_layout.addLayout(photo_button_layout)
        main_layout.addWidget(self.info_label)
        self.setLayout(main_layout)

    def _load_users(self):
        self.user_list.clear()
        self.users = get_all_users()
        for user in self.users:
            user_id, name, external_id, email, created_at = user
            display = name
            if external_id:
                display += f' (ID: {external_id})'
            elif email:
                display += f' ({email})'
            item = QListWidgetItem(display)
            item.setData(Qt.UserRole, user_id)
            self.user_list.addItem(item)
        if not self.users:
            self.info_label.setText('No users registered. Click "Add User" to create one.')
            self.photo_list.clear()

    def _on_user_selected(self):
        if self.user_list.currentItem():
            self.upload_face_btn.setEnabled(True)
            self.capture_face_btn.setEnabled(True)
            self.view_face_btn.setEnabled(False)
            self.delete_btn.setEnabled(True)
            self.delete_photo_btn.setEnabled(False)
            user_id = self.user_list.currentItem().data(Qt.UserRole)
            self._load_face_images(user_id)
        else:
            self.upload_face_btn.setEnabled(False)
            self.capture_face_btn.setEnabled(False)
            self.view_face_btn.setEnabled(False)
            self.delete_btn.setEnabled(False)
            self.delete_photo_btn.setEnabled(False)
            self.photo_list.clear()
            self.info_label.setText('Select a user to manage.')

    def _on_photo_selected(self):
        self.view_face_btn.setEnabled(bool(self.photo_list.currentItem()))
        self.delete_photo_btn.setEnabled(bool(self.photo_list.currentItem()))

    def _load_face_images(self, user_id: int):
        self.photo_list.clear()
        images = get_face_images_for_user(user_id)
        count = 0
        for image_id, filename, description, face_vector, created_at in images:
            display = filename
            if description:
                display += f' — {description}'
            item = QListWidgetItem(display)
            item.setData(Qt.UserRole, {
                'id': image_id,
                'filename': filename,
                'path': str(KNOWN_FACES_DIR / str(user_id) / filename)
            })
            self.photo_list.addItem(item)
            count += 1

        user = get_user_by_id(user_id)
        if user:
            _, name, external_id, email, created_at = user
            label = f"{name}"
            if external_id:
                label += f" (ID: {external_id})"
            if count:
                self.info_label.setText(f'{label} has {count} saved face image(s). Select one to view or delete.')
            else:
                self.info_label.setText(f'{label} has no saved face images yet. Upload photos from different angles.')

    def _add_user(self):
        name, ok = QInputDialog.getText(self, 'Add User', 'Enter user name:')
        if not ok or not name.strip():
            return
        external_id, ok2 = QInputDialog.getText(self, 'Add User', 'Enter user ID/code:', QLineEdit.Normal, '')
        if not ok2:
            return
        email, ok3 = QInputDialog.getText(self, 'Add User', 'Enter email (optional):', QLineEdit.Normal, '')
        if not ok3:
            return

        if add_user(name.strip(), external_id.strip(), email.strip()):
            QMessageBox.information(self, 'Success', f'User {name} added successfully.')
            self._load_users()
        else:
            QMessageBox.warning(self, 'Error', f'A user with that name or ID already exists.')

    def _upload_face(self):
        if not self.user_list.currentItem():
            return

        user_id = self.user_list.currentItem().data(Qt.UserRole)
        files, _ = QFileDialog.getOpenFileNames(
            self, 'Select face images to upload', '',
            'Image Files (*.jpg *.jpeg *.png);;All Files (*)'
        )
        if not files:
            return

        saved = 0
        for file_path in files:
            description, ok = QInputDialog.getText(self, 'Face Image Description', 'Enter a short description (e.g. left profile, right profile):', QLineEdit.Normal, '')
            if ok:
                if add_face_image(user_id, file_path, description.strip()):
                    saved += 1

        if saved:
            QMessageBox.information(self, 'Success', f'Saved {saved} face image(s).')
        else:
            QMessageBox.warning(self, 'Note', 'No face images were saved.')
        self._load_face_images(user_id)

    def _capture_face(self):
        if not self.user_list.currentItem():
            return
        user_id = self.user_list.currentItem().data(Qt.UserRole)
        user = get_user_by_id(user_id)
        if not user:
            return

        dialog = FaceCaptureDialog(self, user_id, user[1])
        dialog.exec()
        self._load_face_images(user_id)

    def _view_face(self):
        item = self.photo_list.currentItem()
        if not item:
            return
        data = item.data(Qt.UserRole)
        photo_path = data.get('path') if isinstance(data, dict) else None
        if not photo_path or not os.path.exists(photo_path):
            QMessageBox.warning(self, 'Not Found', 'Selected face image no longer exists.')
            return

        try:
            if platform.system() == 'Windows':
                os.startfile(photo_path)
            elif platform.system() == 'Darwin':
                import subprocess
                subprocess.Popen(['open', photo_path])
            else:
                import subprocess
                subprocess.Popen(['xdg-open', photo_path])
        except Exception as e:
            QMessageBox.warning(self, 'Error', f'Cannot open image: {e}')

    def _delete_face_image(self):
        item = self.photo_list.currentItem()
        if not item:
            return
        data = item.data(Qt.UserRole)
        image_id = data.get('id') if isinstance(data, dict) else None
        if image_id is None:
            return

        reply = QMessageBox.question(
            self, 'Confirm Delete',
            'Delete the selected face image from this user?',
            QMessageBox.Yes | QMessageBox.No
        )
        if reply != QMessageBox.Yes:
            return

        if delete_face_image(image_id):
            QMessageBox.information(self, 'Deleted', 'Face image deleted successfully.')
            self._load_face_images(self.user_list.currentItem().data(Qt.UserRole))
        else:
            QMessageBox.warning(self, 'Error', 'Could not delete the selected face image.')

    def _delete_user(self):
        if not self.user_list.currentItem():
            return
        user_id = self.user_list.currentItem().data(Qt.UserRole)
        user = get_user_by_id(user_id)
        if not user:
            return
        name, external_id = user[1], user[2]
        display_name = f'{name} (ID: {external_id})' if external_id else name

        reply = QMessageBox.question(
            self,
            'Confirm Delete',
            f'Are you sure you want to delete {display_name} and all their records?',
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            if delete_user(user_id):
                QMessageBox.information(self, 'Success', f'User {display_name} deleted.')
                self._load_users()
            else:
                QMessageBox.warning(self, 'Error', 'Failed to delete user.')
