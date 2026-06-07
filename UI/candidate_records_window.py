"""Candidate Records Window - Register and manage candidates with face recognition data."""

from pathlib import Path
import cv2
import numpy as np
from datetime import datetime

from PySide6.QtWidgets import (
    QDialog, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QComboBox, QPushButton, QTableWidget, QTableWidgetItem,
    QGraphicsView, QGraphicsScene, QGraphicsPixmapItem, QMessageBox, QTabWidget,
    QFileDialog, QAbstractItemView
)
from PySide6.QtGui import QPixmap, QImage
from PySide6.QtCore import Qt, QTimer
from .database import (
    register_candidate, get_all_candidates, delete_candidate,
    update_face_vector, get_candidate_face_vectors, get_candidate,
    KNOWN_FACES_DIR
)


# ==================== Camera Utility Functions ====================

def scan_available_cameras(max_index: int = 8) -> list:
    """Scan system for available cameras.
    
    Args:
        max_index: Maximum camera index to check (default 8)
    
    Returns:
        List of available camera indexes [0, 1, 2, ...]
    """
    available_cameras = []
    for index in range(max_index):
        try:
            cap = cv2.VideoCapture(index, cv2.CAP_DSHOW)
            if cap is not None and cap.isOpened():
                ret = cap.read()
                if ret:
                    available_cameras.append(index)
                cap.release()
        except Exception:
            pass
    return available_cameras


class CameraPreviewGraphicsView(QGraphicsView):
    """Custom QGraphicsView for displaying camera frames and pose photos."""
    
    def __init__(self, pose_name: str):
        super().__init__()
        self.pose_name = pose_name
        self.scene = QGraphicsScene()
        self.setScene(self.scene)
        self.setMinimumSize(220, 220)
        self.setMaximumSize(260, 260)
        self.pixmap_item = None
        self.current_image_path = None
        
        # Set dark background
        self.setStyleSheet("background-color: #1a1a1a;")
        
    def set_image(self, image_path: str = None, cv2_image=None):
        """Set image from file path or numpy array (cv2 format)."""
        self.scene.clear()
        self.pixmap_item = None
        self.current_image_path = image_path
        
        if cv2_image is not None:
            # Convert BGR (cv2 format) to RGB
            rgb_image = cv2.cvtColor(cv2_image, cv2.COLOR_BGR2RGB)
            h, w, ch = rgb_image.shape
            bytes_per_line = 3 * w
            qt_image = QImage(rgb_image.data, w, h, bytes_per_line, QImage.Format_RGB888)
            pixmap = QPixmap.fromImage(qt_image)
        elif image_path and Path(image_path).exists():
            pixmap = QPixmap(image_path)
        else:
            return
        
        # Scale pixmap to fit view
        pixmap = pixmap.scaled(200, 200, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.pixmap_item = QGraphicsPixmapItem(pixmap)
        self.scene.addItem(self.pixmap_item)
        self.fitInView(self.scene.itemsBoundingRect(), Qt.KeepAspectRatio)
    
    def clear_scene(self):
        """Clear the scene and reset state."""
        self.scene.clear()
        self.pixmap_item = None
        self.current_image_path = None
    
    def get_current_image(self):
        """Return current image data (conversion to RGB array if needed)."""
        if self.pixmap_item is None:
            return None
        pixmap = self.pixmap_item.pixmap()
        image = pixmap.toImage()
        width = image.width()
        height = image.height()
        ptr = image.bits()
        ptr.setsize(image.byteCount())
        arr = np.array(ptr).reshape(height, width, 4)  # 4 channels for RGBA
        return arr[:, :, :3]  # Return only RGB


class RegisterUserView(QWidget):
    """View for registering new candidates with 5-pose face captures."""
    
    def __init__(self):
        super().__init__()
        self.candidate_id = None
        self.candidate_name = None
        self.department = None
        self.camera_frame = None
        self.pose_graphics_views = {}
        
        # Camera management
        self.available_cameras = []
        self.current_camera_index = None
        self.camera_capture = None
        self.camera_thread = None
        self.is_streaming = False
        self.live_stream_view = None
        self.camera_timer = None
        
        self.init_ui()
        self.scan_cameras()
    
    def __del__(self):
        """Cleanup resources when view is destroyed."""
        # Avoid manipulating Qt widgets during object destruction (they may be deleted already).
        try:
            if getattr(self, 'camera_timer', None) is not None:
                self.camera_timer.stop()
        except Exception:
            pass
        try:
            if getattr(self, 'camera_capture', None) is not None:
                self.camera_capture.release()
                self.camera_capture = None
        except Exception:
            pass
        
    def scan_cameras(self):
        """Scan for available cameras."""
        self.available_cameras = scan_available_cameras()
        if self.camera_combo:
            self.camera_combo.clear()
            if self.available_cameras:
                for idx in self.available_cameras:
                    self.camera_combo.addItem(f"Camera {idx}", idx)
            else:
                self.camera_combo.addItem("No cameras detected", -1)

        
    def init_ui(self):
        """Initialize the register user interface."""
        layout = QHBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(2)

        # Left panel: camera source and live preview
        left_panel = QVBoxLayout()
        left_panel.setSpacing(10)

        camera_top = QHBoxLayout()
        camera_top.setSpacing(8)
        
        camera_label = QLabel("Select Camera Source:")
        camera_label.setStyleSheet("font-weight: 600; font-size: 12px;")
        camera_top.addWidget(camera_label)

        self.camera_combo = QComboBox()
        self.camera_combo.setMinimumWidth(160)
        camera_top.addWidget(self.camera_combo)

        self.start_camera_btn = QPushButton("Start")
        self.start_camera_btn.setFixedSize(80, 32)
        self.start_camera_btn.setStyleSheet(
            "QPushButton { background-color: #FF9800; color: white; border: none; "
            "border-radius: 5px; font-weight: 600; }"
            "QPushButton:hover { background-color: #F57C00; }"
        )
        self.start_camera_btn.clicked.connect(self.toggle_camera_stream)
        camera_top.addWidget(self.start_camera_btn)
        camera_top.addStretch()

        left_panel.addLayout(camera_top)

        self.camera_status_label = QLabel("Camera: Idle")
        self.camera_status_label.setStyleSheet("color: #666; font-size: 11px;")
        left_panel.addWidget(self.camera_status_label)

        self.live_stream_view = CameraPreviewGraphicsView("live_preview")
        self.live_stream_view.setMinimumSize(520, 360)
        self.live_stream_view.setStyleSheet("background-color: #000;")
        left_panel.addWidget(self.live_stream_view)
        left_panel.addStretch()

        # Right panel: form and pose rows
        right_panel = QVBoxLayout()
        right_panel.setSpacing(10)

        # Metadata form
        form_layout = QVBoxLayout()
        form_layout.setSpacing(5)

        new_candidate_label = QLabel("Add New Candidate")
        new_candidate_label.setAlignment(Qt.AlignCenter)
        new_candidate_label.setStyleSheet("font-weight: 900; font-size: 20px;")
        form_layout.addWidget(new_candidate_label)

        id_label = QLabel("Candidate ID")
        id_label.setStyleSheet("font-weight: 600;")
        self.id_input = QLineEdit()
        self.id_input.setPlaceholderText("Enter unique ID")
        self.id_input.setFixedHeight(32)
        form_layout.addWidget(id_label)
        form_layout.addWidget(self.id_input)

        name_label = QLabel("Candidate Name")
        name_label.setStyleSheet("font-weight: 600;")
        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("Enter full name")
        self.name_input.setFixedHeight(32)
        form_layout.addWidget(name_label)
        form_layout.addWidget(self.name_input)

        dept_label = QLabel("Department")
        dept_label.setStyleSheet("font-weight: 600;")
        self.dept_input = QComboBox()
        self.dept_input.addItems(["HR", "IT", "Finance", "Operations", "Marketing", "Other"])
        self.dept_input.setFixedHeight(32)
        form_layout.addWidget(dept_label)
        form_layout.addWidget(self.dept_input)

        right_panel.addLayout(form_layout)

        # Pose rows section
        poses_layout = QVBoxLayout()
        poses_layout.setSpacing(8)

        self.pose_labels = [
            ("center", "Center"),
            ("left", "Left 30°"),
            ("right", "Right 30°"),
            ("up", "Up 30°"),
            ("down", "Down 30°"),
        ]

        self.row_buttons = {}

        for pose_key, pose_text in self.pose_labels:
            row_layout = QHBoxLayout()
            row_layout.setSpacing(8)

            thumb_view = CameraPreviewGraphicsView(pose_key)
            thumb_view.setFixedSize(100, 90)
            thumb_view.setStyleSheet("background-color: #111; border: 1px solid #ccc;")
            self.pose_graphics_views[pose_key] = thumb_view
            row_layout.addWidget(thumb_view)

            pose_label = QLabel(pose_text)
            pose_label.setFixedWidth(80)
            pose_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            row_layout.addWidget(pose_label)

            capture_btn = QPushButton("📷")
            capture_btn.setFixedSize(36, 36)
            capture_btn.setStyleSheet(
                "QPushButton { background-color: #4CAF50; color: white; border: none; border-radius: 6px; }"
                "QPushButton:hover { background-color: #43A047; }"
            )
            capture_btn.clicked.connect(lambda checked, p=pose_key: self.capture_pose(p))
            row_layout.addWidget(capture_btn)

            delete_btn = QPushButton("🗑️")
            delete_btn.setFixedSize(36, 36)
            delete_btn.setStyleSheet(
                "QPushButton { background-color: #F44336; color: white; border: none; border-radius: 6px; }"
                "QPushButton:hover { background-color: #E53935; }"
            )
            delete_btn.clicked.connect(lambda checked, p=pose_key: self.delete_pose(p))
            row_layout.addWidget(delete_btn)

            full_view_btn = QPushButton("👁️")
            full_view_btn.setFixedSize(36, 36)
            full_view_btn.setStyleSheet(
                "QPushButton { background-color: #607D8B; color: white; border: none; border-radius: 6px; }"
                "QPushButton:hover { background-color: #546E7A; }"
            )
            full_view_btn.clicked.connect(lambda checked, p=pose_key: self.show_full_view(p))
            row_layout.addWidget(full_view_btn)

            upload_btn = QPushButton("📤")
            upload_btn.setFixedSize(36, 36)
            upload_btn.setStyleSheet(
                "QPushButton { background-color: #3F51B5; color: white; border: none; border-radius: 6px; }"
                "QPushButton:hover { background-color: #3949AB; }"
            )
            upload_btn.clicked.connect(lambda checked, p=pose_key: self.upload_pose(p))
            row_layout.addWidget(upload_btn)

            row_layout.addStretch()
            poses_layout.addLayout(row_layout)

        right_panel.addLayout(poses_layout)
        right_panel.addStretch()

        # Bottom action buttons
        button_row = QHBoxLayout()
        button_row.setSpacing(12)

        save_btn = QPushButton("Save Candidate")
        save_btn.setFixedHeight(40)
        save_btn.setStyleSheet(
            "QPushButton { background-color: #2196F3; color: white; border: none; border-radius: 6px; "
            "font-weight: 700; padding: 0 18px; }"
            "QPushButton:hover { background-color: #1E88E5; }"
        )
        save_btn.clicked.connect(self.save_candidate)
        button_row.addWidget(save_btn)

        reset_btn = QPushButton("Reset Form")
        reset_btn.setFixedHeight(40)
        reset_btn.setStyleSheet(
            "QPushButton { background-color: #9E9E9E; color: white; border: none; border-radius: 6px; "
            "font-weight: 700; padding: 0 18px; }"
            "QPushButton:hover { background-color: #757575; }"
        )
        reset_btn.clicked.connect(self.reset_form)
        button_row.addWidget(reset_btn)

        right_panel.addLayout(button_row)

        # Add panels to main layout
        layout.addLayout(left_panel, 1)
        layout.addLayout(right_panel, 1)

    
    def save_candidate(self):
        """Save candidate with captured poses to database."""
        # Validate inputs
        candidate_id = self.id_input.text().strip()
        candidate_name = self.name_input.text().strip()
        department = self.dept_input.currentText()
        
        if not candidate_id or not candidate_name:
            QMessageBox.warning(self, "Incomplete", "Please enter Candidate ID and Name.")
            return
        
        # Check that all 5 poses are captured
        all_captured = all(view.scene.items() for view in self.pose_graphics_views.values())
        if not all_captured:
            QMessageBox.warning(self, "Incomplete", "Please capture all 5 poses before saving.")
            return
        
        # Create directory for candidate
        candidate_dir = KNOWN_FACES_DIR / candidate_id
        candidate_dir.mkdir(parents=True, exist_ok=True)
        
        try:
            # Register candidate in personal_details
            center_image_path = None
            image_paths = {}
            for pose_key, view in self.pose_graphics_views.items():
                if view.pixmap_item is None:
                    continue
                
                # Save image file
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                image_filename = f"{pose_key}_{timestamp}.jpg"
                image_path = candidate_dir / image_filename
                
                # Get pixmap and save
                pixmap = view.pixmap_item.pixmap()
                pixmap.save(str(image_path))
                # Keep track of saved image paths for vector extraction
                image_paths[pose_key] = str(image_path)

                # Save center image path
                if pose_key == "center":
                    center_image_path = str(image_path)
            
            # Register candidate
            if register_candidate(candidate_id, candidate_name, department, center_image_path):
                # Compute and save face vectors for each pose image we saved.
                # Keep the actual image file only for the center pose; delete others after extracting vectors.
                image_paths = {k: v for k, v in locals().get('image_paths', {}).items()} if 'image_paths' in locals() else {}

                # Try to load face_recognition to extract encodings
                try:
                    import face_recognition
                    face_recognition_available = True
                except Exception:
                    face_recognition_available = False

                for pose_key, img_path in image_paths.items():
                    face_vector = None
                    if face_recognition_available and img_path and Path(img_path).exists():
                        try:
                            img = face_recognition.load_image_file(str(img_path))
                            encodings = face_recognition.face_encodings(img)
                            if encodings:
                                # Convert to plain Python list for JSON serialization
                                face_vector = encodings[0].tolist() if hasattr(encodings[0], 'tolist') else list(map(float, encodings[0]))
                        except Exception:
                            face_vector = None

                    # Save vector (may be None if extraction failed)
                    update_face_vector(candidate_id, pose_key, face_vector=face_vector)

                    # Remove non-center pose image files to retain only center image on disk
                    try:
                        if pose_key != 'center' and img_path and Path(img_path).exists():
                            Path(img_path).unlink()
                    except Exception:
                        pass

                QMessageBox.information(
                    self, "Success",
                    f"Candidate '{candidate_name}' registered successfully!"
                )
                self.reset_form()
            else:
                QMessageBox.critical(self, "Error", "Failed to register candidate.")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Error saving candidate: {str(e)}")
    
    def reset_form(self):
        """Clear all fields and poses."""
        self.id_input.clear()
        self.name_input.clear()
        self.dept_input.setCurrentIndex(0)
        self.stop_camera_stream()
        for view in self.pose_graphics_views.values():
            view.clear_scene()
    
    def set_camera_frame(self, frame):
        """Set current camera frame from scanner."""
        self.camera_frame = frame.copy()
    
    def toggle_camera_stream(self):
        """Start or stop the camera stream."""
        if self.is_streaming:
            self.stop_camera_stream()
        else:
            self.start_camera_stream()
    
    def start_camera_stream(self):
        """Initialize and start streaming from selected camera."""
        if self.camera_combo.currentData() == -1:
            QMessageBox.warning(self, "No Camera", "No cameras available.")
            return
        
        # Release previous camera if any
        if self.camera_capture is not None:
            self.camera_capture.release()
        
        # Get selected camera index
        self.current_camera_index = self.camera_combo.currentData()
        
        try:
            # Open camera with DirectShow backend
            self.camera_capture = cv2.VideoCapture(self.current_camera_index, cv2.CAP_DSHOW)
            
            if not self.camera_capture.isOpened():
                QMessageBox.critical(self, "Error", f"Failed to open Camera {self.current_camera_index}")
                self.camera_capture = None
                return
            
            # Set camera properties for better performance
            self.camera_capture.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
            self.camera_capture.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
            self.camera_capture.set(cv2.CAP_PROP_FPS, 30)
            
            self.is_streaming = True
            self.start_camera_btn.setText("Stop Camera")
            self.start_camera_btn.setStyleSheet(
                "QPushButton { background-color: #F44336; color: white; border: none; "
                "border-radius: 4px; font-weight: 600; }"
                "QPushButton:hover { background-color: #D32F2F; }"
                "QPushButton:pressed { background-color: #B71C1C; }"
            )
            
            self.camera_status_label.setText(
                f"Camera: Connected (Index {self.current_camera_index}) | Status: Streaming"
            )
            self.camera_status_label.setStyleSheet("font-size: 11px; color: #4CAF50; font-weight: 600;")
            
            # Start camera frame update timer
            if self.camera_timer is None:
                self.camera_timer = QTimer()
                self.camera_timer.timeout.connect(self.update_camera_stream)
            
            self.camera_timer.start(30)  # Update every 30ms (~33 FPS)
            
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to start camera: {str(e)}")
            self.camera_capture = None
            self.is_streaming = False
    
    def update_camera_stream(self):
        """Update the live preview with current camera frame."""
        if self.camera_capture is None or not self.camera_capture.isOpened():
            self.stop_camera_stream()
            return
        
        ret, frame = self.camera_capture.read()
        if not ret or frame is None:
            return
        
        # Store frame for capture
        self.camera_frame = frame.copy()
        
        # Display in live preview
        if self.live_stream_view is not None:
            self.live_stream_view.set_image(cv2_image=frame)
    
    def stop_camera_stream(self):
        """Stop the camera stream."""
        if self.camera_timer is not None:
            self.camera_timer.stop()
        
        if self.camera_capture is not None:
            self.camera_capture.release()
            self.camera_capture = None
        
        self.is_streaming = False
        self.current_camera_index = None
        self.camera_frame = None
        
        self.start_camera_btn.setText("Start Camera")
        self.start_camera_btn.setStyleSheet(
            "QPushButton { background-color: #FF9800; color: white; border: none; "
            "border-radius: 4px; font-weight: 600; }"
            "QPushButton:hover { background-color: #F57C00; }"
            "QPushButton:pressed { background-color: #E65100; }"
        )
        
        self.camera_status_label.setText("Camera: Disconnected | Status: Idle")
        self.camera_status_label.setStyleSheet("font-size: 11px; color: #666;")
        
        if self.live_stream_view is not None:
            self.live_stream_view.clear_scene()
    
    def capture_pose(self, pose_key: str):
        """Capture current camera frame to specific pose slot."""
        if self.camera_frame is None:
            QMessageBox.warning(
                self,
                "No Frame",
                "No camera frame available.\n\nPlease:\n"
                "1. Select a camera from the dropdown\n"
                "2. Click 'Start Camera'\n"
                "3. Then click [Capture] for a pose"
            )
            return
        
        # Display frame in the graphics view
        self.pose_graphics_views[pose_key].set_image(cv2_image=self.camera_frame)
        QMessageBox.information(self, "Captured", f"Pose '{pose_key}' captured successfully!")
    
    def delete_pose(self, pose_key: str):
        """Clear specific pose slot."""
        self.pose_graphics_views[pose_key].clear_scene()
    
    def show_full_view(self, pose_key: str):
        """Show the captured pose image in a full-size dialog."""
        view_widget = self.pose_graphics_views.get(pose_key)
        if view_widget is None or view_widget.pixmap_item is None:
            QMessageBox.warning(self, "No Image", "No captured image available for this pose.")
            return
        
        dialog = QDialog(self)
        dialog.setWindowTitle(f"Full View - {pose_key.capitalize()}")
        dialog.setWindowState(Qt.WindowMaximized)
        dialog_layout = QVBoxLayout(dialog)
        
        full_view = CameraPreviewGraphicsView(f"full_{pose_key}")
        pixmap = view_widget.pixmap_item.pixmap()
        full_view.scene.clear()
        full_view.pixmap_item = QGraphicsPixmapItem(pixmap.scaled(
            1280, 720, Qt.KeepAspectRatio, Qt.SmoothTransformation
        ))
        full_view.scene.addItem(full_view.pixmap_item)
        full_view.fitInView(full_view.scene.itemsBoundingRect(), Qt.KeepAspectRatio)
        dialog_layout.addWidget(full_view)
        
        close_btn = QPushButton("Close")
        close_btn.setMinimumHeight(35)
        close_btn.clicked.connect(dialog.accept)
        dialog_layout.addWidget(close_btn)
        
        dialog.exec()
    
    def upload_pose(self, pose_key: str):
        """Upload an image from disk into a pose slot."""
        image_path, _ = QFileDialog.getOpenFileName(
            self,
            "Upload Pose Image",
            str(Path.home()),
            "Image Files (*.png *.jpg *.jpeg *.bmp *.gif)"
        )
        if not image_path:
            return
        
        self.pose_graphics_views[pose_key].set_image(image_path=image_path)
        QMessageBox.information(self, "Uploaded", f"Image uploaded to pose '{pose_key}'.")


class ManageUserView(QWidget):
    """View for managing and deleting registered candidates."""
    
    def __init__(self):
        super().__init__()
        self.selected_candidate_id = None
        self.init_ui()
        self.load_candidates()
    
    def init_ui(self):
        """Initialize the manage user interface."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)
        
        # Header
        header = QLabel("Manage Registered Candidates")
        header.setStyleSheet("font-size: 16px; font-weight: bold; color: #fff;")
        layout.addWidget(header)
        
        # Candidates table
        self.candidates_table = QTableWidget()
        self.candidates_table.setColumnCount(5)
        self.candidates_table.setHorizontalHeaderLabels(
            ["Candidate ID", "Name", "Department", "Poses Captured", "Center Image Path"]
        )
        self.candidates_table.horizontalHeader().setStretchLastSection(True)
        self.candidates_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.candidates_table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.candidates_table.setStyleSheet(
            "QTableWidget { background-color: gray; border: 1px solid #ddd; }"
            "QTableWidget::item { padding: 5px; }"
            "QHeaderView::section { background-color: #e0e0e0; padding: 5px; font-weight: bold; }"
        )
        self.candidates_table.itemSelectionChanged.connect(self.on_row_selected)
        layout.addWidget(self.candidates_table)
        
        # Action buttons
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        
        refresh_btn = QPushButton("Refresh")
        refresh_btn.setMinimumWidth(100)
        refresh_btn.setMinimumHeight(35)
        refresh_btn.setStyleSheet(
            "QPushButton { background-color: #2196F3; color: white; border: none; "
            "border-radius: 4px; font-weight: 600; }"
            "QPushButton:hover { background-color: #0b7dda; }"
        )
        refresh_btn.clicked.connect(self.load_candidates)
        button_layout.addWidget(refresh_btn)
        
        view_image_btn = QPushButton("👁️ View Center Image")
        view_image_btn.setMinimumWidth(160)
        view_image_btn.setMinimumHeight(35)
        view_image_btn.setStyleSheet(
            "QPushButton { background-color: #607D8B; color: white; border: none; "
            "border-radius: 4px; font-weight: 600; }"
            "QPushButton:hover { background-color: #455A64; }"
            "QPushButton:disabled { background-color: #ccc; }"
        )
        view_image_btn.clicked.connect(self.view_center_image)
        view_image_btn.setEnabled(False)
        self.view_image_btn = view_image_btn
        button_layout.addWidget(view_image_btn)
        
        delete_btn = QPushButton("Delete Candidate")
        delete_btn.setMinimumWidth(150)
        delete_btn.setMinimumHeight(35)
        delete_btn.setStyleSheet(
            "QPushButton { background-color: #f44336; color: white; border: none; "
            "border-radius: 4px; font-weight: 600; }"
            "QPushButton:hover { background-color: #da190b; }"
            "QPushButton:disabled { background-color: #ccc; }"
        )
        delete_btn.clicked.connect(self.delete_candidate_action)
        delete_btn.setEnabled(False)
        self.delete_btn = delete_btn
        button_layout.addWidget(delete_btn)
        
        layout.addLayout(button_layout)
    
    def load_candidates(self):
        """Load all candidates from database."""
        self.candidates_table.setRowCount(0)
        candidates = get_all_candidates()
        
        for row, (candidate_id, name, department, center_image_path) in enumerate(candidates):
            self.candidates_table.insertRow(row)
            
            # Candidate ID
            id_item = QTableWidgetItem(candidate_id)
            self.candidates_table.setItem(row, 0, id_item)
            
            # Name
            name_item = QTableWidgetItem(name)
            self.candidates_table.setItem(row, 1, name_item)
            
            # Department
            dept_item = QTableWidgetItem(department)
            self.candidates_table.setItem(row, 2, dept_item)
            
            # Poses count
            vectors = get_candidate_face_vectors(candidate_id)
            poses_count = len(vectors)
            poses_item = QTableWidgetItem(f"{poses_count}/5")
            poses_item.setTextAlignment(Qt.AlignCenter)
            self.candidates_table.setItem(row, 3, poses_item)
            
            # Center Image Path
            image_path_text = center_image_path if center_image_path else "N/A"
            image_item = QTableWidgetItem(image_path_text)
            image_item.setToolTip(image_path_text)  # Full path on hover
            self.candidates_table.setItem(row, 4, image_item)
    
    def on_row_selected(self):
        """Handle table row selection."""
        selected_rows = self.candidates_table.selectionModel().selectedRows()
        if selected_rows:
            row = selected_rows[0].row()
            self.selected_candidate_id = self.candidates_table.item(row, 0).text()
            self.delete_btn.setEnabled(True)
            
            # Check if image exists before enabling view button
            image_path = self.candidates_table.item(row, 4).text()
            image_exists = image_path != "N/A" and image_path and Path(image_path).exists()
            self.view_image_btn.setEnabled(image_exists)
        else:
            self.selected_candidate_id = None
            self.delete_btn.setEnabled(False)
            self.view_image_btn.setEnabled(False)
    
    def view_center_image(self):
        """Display the center image for the selected candidate."""
        if not self.selected_candidate_id:
            QMessageBox.warning(self, "No Selection", "Please select a candidate first.")
            return
        
        # Get image path from selected row
        selected_rows = self.candidates_table.selectionModel().selectedRows()
        if not selected_rows:
            return
        
        row = selected_rows[0].row()
        image_path = self.candidates_table.item(row, 4).text()
        
        if image_path == "N/A" or not image_path or not Path(image_path).exists():
            QMessageBox.warning(self, "No Image", "Center image not available for this candidate.")
            return
        
        # Create and show full-screen image viewer
        dialog = QDialog(self)
        candidate_name = self.candidates_table.item(row, 1).text()
        dialog.setWindowTitle(f"Center Image - {candidate_name}")
        dialog.setWindowState(Qt.WindowMaximized)
        dialog_layout = QVBoxLayout(dialog)
        
        # Image viewer
        image_view = CameraPreviewGraphicsView("center_image_view")
        image_view.set_image(image_path=image_path)
        dialog_layout.addWidget(image_view)
        
        # Close button
        close_btn = QPushButton("Close")
        close_btn.setMinimumHeight(35)
        close_btn.clicked.connect(dialog.accept)
        dialog_layout.addWidget(close_btn)
        
        dialog.exec()
    
    def delete_candidate_action(self):
        """Delete selected candidate with confirmation."""
        if not self.selected_candidate_id:
            QMessageBox.warning(self, "No Selection", "Please select a candidate to delete.")
            return
        
        # Get candidate name for confirmation
        candidate = get_candidate(self.selected_candidate_id)
        if not candidate:
            QMessageBox.warning(self, "Error", "Candidate not found.")
            return
        
        candidate_name = candidate[1]
        
        # Confirmation dialog
        reply = QMessageBox.question(
            self,
            "Confirm Delete",
            f"Are you sure you want to delete '{candidate_name}' and all associated face vectors?\n\n"
            "This action cannot be undone.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            try:
                if delete_candidate(self.selected_candidate_id):
                    QMessageBox.information(
                        self,
                        "Success",
                        f"Candidate '{candidate_name}' and all associated data deleted."
                    )
                    self.load_candidates()
                    self.selected_candidate_id = None
                    self.delete_btn.setEnabled(False)
                else:
                    QMessageBox.critical(self, "Error", "Failed to delete candidate.")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Error deleting candidate: {str(e)}")


class CandidateRecordsWindow(QDialog):
    """Main Candidate Records Window with tabs for Register and Manage."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Candidate Records")
        self.setMinimumSize(1000, 700)
        self.resize(1200, 800)
        self.setWindowState(Qt.WindowMaximized)
        self.init_ui()
    
    def init_ui(self):
        """Initialize the main window UI."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)
        
        # Tab widget
        self.tab_widget = QTabWidget()
        self.register_view = RegisterUserView()
        self.manage_view = ManageUserView()
        
        self.tab_widget.addTab(self.register_view, "Register User")
        self.tab_widget.addTab(self.manage_view, "Manage User")
        
        layout.addWidget(self.tab_widget)
        self.setLayout(layout)
    
    def set_camera_frame(self, frame):
        """Pass camera frame to register view for capture."""
        self.register_view.set_camera_frame(frame)
