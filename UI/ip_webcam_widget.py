"""IP Webcam / remote stream scanner."""
import cv2
import json
import numpy as np
import time
import urllib.request
import io
import os
from datetime import date, datetime, time as dtime

from pathlib import Path
from PySide6.QtCore import QTimer, Qt, QThread, Signal
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import (
    QWidget, QLabel, QPushButton, QVBoxLayout, QHBoxLayout, QLineEdit,
    QSpinBox, QComboBox, QInputDialog, QMessageBox, QApplication
)

from .database import (
    get_all_candidates,
    get_known_face_vectors_for_candidates,
    get_candidate_in_logs_for_date,
    log_attendance_log,
    log_unknown_attendance,
)
from .config import load_config, save_config

KNOWN_FACES_DIR = Path(__file__).parent.parent / 'known_faces'
ATTENDANCE_PHOTOS_DIR = Path(__file__).parent.parent / 'attendance_photos'
KNOWN_FACES_DIR.mkdir(parents=True, exist_ok=True)
ATTENDANCE_PHOTOS_DIR.mkdir(parents=True, exist_ok=True)




class RTSPCameraReader:
    """
    Dedicated media engine to connect, authenticate, and decode 
    industrial CCTV network streams via RTSP.
    """
    def __init__(self, rtsp_url: str):
        self.rtsp_url = rtsp_url
        self.cap = None

    def open_stream(self) -> bool:
        """Establishes connection to the CCTV network hardware."""
        try:
            # Initialize connection using FFmpeg backend decoder
            self.cap = cv2.VideoCapture(self.rtsp_url, cv2.CAP_FFMPEG)
            
            # --- HIGH RESOLUTION PROTECTIVE FILTER/BLOCKER ---
            # CCTV main-streams (4K/1080p) will lag face recognition loops.
            # If the incoming camera resolution exceeds standard desktop limits,
            # we reject it and force the administrator to use the camera's Sub-Stream.
            if self.cap.isOpened():
                width = self.cap.get(cv2.CAP_PROP_FRAME_WIDTH)
                height = self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT)
                
                if width > 1280 or height > 720:
                    print(f"🛑 [BLOCK TRIGGERED] Stream rejected. Resolution ({int(width)}x{int(height)}) is too high!")
                    self.release()
                    return False
            
            # Real-time lag mitigation: Force internal cache to hold only 1 frame
            if self.cap:
                self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
                
            return self.cap.isOpened()
        except Exception as e:
            print(f"RTSP Protocol connection error: {e}")
            return False

    def grab_frame(self):
        """Grabs the latest decoupled video matrix row frame."""
        if self.cap and self.cap.isOpened():
            ret, frame = self.cap.read()
            if ret:
                return frame
        return None

    def release(self):
        """Termitnates network sockets and frees hardware channels."""
        if self.cap:
            self.cap.release()
            self.cap = None


class RTSPStreamReaderThread(QThread):
    """
    Background worker thread dedicated to pulling frames from CCTV hardware
    without blocking the primary PyQt graphical user interface.
    """
    frame_ready = Signal(object)
    error_occurred = Signal(str)
    status_update = Signal(str)

    def __init__(self, rtsp_url: str):
        super().__init__()
        self.rtsp_url = rtsp_url
        self.running = True
        self.engine = None

    def run(self):
        self.status_update.emit("Connecting to CCTV hardware via RTSP...")
        self.engine = RTSPCameraReader(self.rtsp_url)
        
        if not self.engine.open_stream():
            self.error_occurred.emit(
                "RTSP Connection Blocked or Failed!\n\n"
                "Possible reasons:\n"
                "1. Resolution is higher than 1280x720 (Main-stream blocked)\n"
                "2. Incorrect username/password/IP configuration."
            )
            return

        self.status_update.emit("CCTV Secure Stream Connected. Scanning active...")
        consecutive_failures = 0

        while self.running:
            frame = self.engine.grab_frame()
            if frame is not None:
                consecutive_failures = 0
                self.frame_ready.emit(frame)
            else:
                consecutive_failures += 1
                # If network drops link connection for ~2 consecutive seconds
                if consecutive_failures > 60:
                    self.error_occurred.emit("Lost communication sequence with CCTV hardware.")
                    break
            
            # Throttle processing loop to keep pace with standard video framerate (~30 FPS)
            time.sleep(0.033)

        self.engine.release()

    def stop(self):
        self.running = False


class MJPEGStreamReader:
    """Custom MJPEG stream parser for IP Webcam."""

    def __init__(self, url: str):
        self.url = url
        self.stream = None
        self.bytes = bytes()

    def read_frame(self):
        """Read a single frame from the MJPEG stream."""
        if self.stream is None:
            return None

        try:
            chunk_size = 4096
            data = self.stream.read(chunk_size)
            if not data:
                return None
            self.bytes += data
            a = self.bytes.find(b'\xff\xd8')  # JPEG start
            b = self.bytes.find(b'\xff\xd9')  # JPEG end

            if a != -1 and b != -1 and b > a:
                jpg = self.bytes[a:b+2]
                self.bytes = self.bytes[b+2:]
                img = cv2.imdecode(np.frombuffer(jpg, dtype=np.uint8), cv2.IMREAD_COLOR)
                return img

            if len(self.bytes) > 100000:  # Prevent memory buildup
                self.bytes = self.bytes[-10000:]
            return None
        except Exception as e:
            print(f'MJPEG read error: {e}')
            self.bytes = bytes()
            return None

    def open(self):
        """Open the stream with proper headers."""
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'Accept': 'image/jpeg, application/octet-stream',
            }
            req = urllib.request.Request(self.url, headers=headers)
            self.stream = urllib.request.urlopen(req, timeout=10)
            return True
        except Exception as e:
            print(f'Stream open error: {e}')
            return False

    def release(self):
        if self.stream:
            try:
                self.stream.close()
            except:
                pass
            self.stream = None


class ShotPollingReader:
    """Fallback: Poll single frames from IP Webcam's /shot.jpg endpoint."""

    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip('/video').rstrip('/')
        self.shot_url = f'{self.base_url}/shot.jpg'

    def read_frame(self):
        try:
            req = urllib.request.Request(
                self.shot_url,
                headers={'User-Agent': 'Mozilla/5.0'}
            )
            resp = urllib.request.urlopen(req, timeout=5)
            img_array = np.asarray(bytearray(resp.read()), dtype=np.uint8)
            return cv2.imdecode(img_array, cv2.IMREAD_COLOR)
        except Exception as e:
            print(f'Shot polling error: {e}')
            return None

    def release(self):
        pass


class StreamReaderThread(QThread):
    """Background thread to read frames from IP Webcam stream."""
    frame_ready = Signal(object)
    error_occurred = Signal(str)
    status_update = Signal(str)

    def __init__(self, stream_url: str):
        super().__init__()
        self.stream_url = stream_url
        self.running = True
        self.cap = None
        self.mjpeg_reader = None
        self.shot_reader = None
        self.use_shot_mode = False

    def run(self):
        try:
            # First try MJPEG stream
            self.mjpeg_reader = MJPEGStreamReader(self.stream_url)
            if self.mjpeg_reader.open():
                self.status_update.emit('Using MJPEG stream mode...')
                self._read_mjpeg_loop()
            else:
                self._try_shot_polling_mode()

        except Exception as e:
            self.error_occurred.emit(f'Stream error: {e}')
        finally:
            if self.mjpeg_reader:
                self.mjpeg_reader.release()
            if self.shot_reader:
                self.shot_reader.release()

    def _read_mjpeg_loop(self):
        """Read frames from MJPEG stream."""
        consecutive_failures = 0
        max_failures = 120

        while self.running:
            frame = self.mjpeg_reader.read_frame()

            if frame is not None:
                consecutive_failures = 0
                self.frame_ready.emit(frame)
            else:
                consecutive_failures += 1
                if consecutive_failures > max_failures:
                    self.status_update.emit('Attempting to reconnect to MJPEG stream...')
                    self.mjpeg_reader.release()
                    time.sleep(1)
                    if self.mjpeg_reader.open():
                        consecutive_failures = 0
                        continue
                    self.error_occurred.emit('Lost connection to MJPEG stream.')
                    break

            time.sleep(0.033)  # ~30 FPS

    def _try_shot_polling_mode(self):
        """Fallback: Use /shot.jpg polling."""
        self.status_update.emit('Trying shot.jpg polling mode...')
        self.shot_reader = ShotPollingReader(self.stream_url)

        consecutive_failures = 0
        max_failures = 10

        while self.running:
            frame = self.shot_reader.read_frame()

            if frame is not None:
                consecutive_failures = 0
                self.frame_ready.emit(frame)
            else:
                consecutive_failures += 1
                if consecutive_failures > max_failures:
                    self.error_occurred.emit('Shot polling failed. Check IP Webcam app is running.')
                    break

            time.sleep(0.1)  # ~10 FPS for polling mode

    def stop(self):
        self.running = False


class IPWebcamWidget(QWidget):
    """Scanner using IP Webcam stream from phone."""
    camera_started = Signal(str)
    camera_stopped = Signal(str)
    frame_captured = Signal(object)  # Emits frame for preview

    def __init__(self, entry_time: str = '09:00', late_time: str = '10:00', exit_time: str = '17:00', mode: str = 'phone'):
        super().__init__()
        self.mode = mode
        self.config = load_config()
        self.stream_thread = None
        
        if mode == 'cctv':
            self.setWindowTitle('CCTV Scanner')
            self.camera_name = 'CCTV Stream'
            self.default_url = self.config.get('cctv_stream_url', 'rtsp://192.168.1.100:554/stream')
            self.mode_label = 'Scan via CCTV'
        else:
            self.setWindowTitle('IP Webcam Scanner')
            self.camera_name = 'Phone IP Webcam'
            self.default_url = self.config.get('phone_stream_url', '')
            self.mode_label = 'Scan via Phone'
        
        self.known_face_vectors = []
        self.known_candidate_ids = []
        self.known_candidate_names = []
        self.face_recognition_available = False
        self.tolerance = 0.45
        self.last_logged_candidate_id = None
        self.last_log_time = 0
        self.entry_time = self._parse_time(entry_time)
        self.late_time = self._parse_time(late_time)
        self.exit_time = self._parse_time(exit_time)
        self.checkout_cutoff_time = dtime(18, 0)

        self._build_ui()
        self._load_known_faces()

    def _build_ui(self):
        main_layout = QVBoxLayout()

        # Title showing mode
        mode_title = QLabel(self.mode_label)
        mode_title.setStyleSheet('font-weight: bold; font-size: 14px;')
        main_layout.addWidget(mode_title)

        # Stream URL configuration
        url_layout = QHBoxLayout()
        url_label = QLabel('Stream URL:')
        self.url_input = QLineEdit(self.default_url)
        if self.mode == 'cctv':
            self.url_input.setPlaceholderText('rtsp://192.168.1.100:554/stream')
        else:
            self.url_input.setPlaceholderText('http://192.168.1.50:8080/video')
        self.url_clear_btn = QPushButton('Test URL')
        self.url_clear_btn.clicked.connect(self._test_url)
        url_layout.addWidget(url_label)
        url_layout.addWidget(self.url_input)
        url_layout.addWidget(self.url_clear_btn)

        # Camera preview
        self.preview_label = QLabel('Stream preview will appear here.')
        self.preview_label.setAlignment(Qt.AlignCenter)
        self.preview_label.setMinimumSize(640, 360)

        # Info label
        self.info_label = QLabel('Enter stream URL and press "Start Scanning".')
        self.info_label.setWordWrap(True)

        # Rotation control
        rotate_layout = QHBoxLayout()
        rotate_label = QLabel('Phone stream rotation:')
        self.rotation_combo = QComboBox()
        self.rotation_combo.addItems(['0°', '90°', '180°', '270°'])
        self.rotation_combo.setCurrentIndex(0)
        rotate_layout.addWidget(rotate_label)
        rotate_layout.addWidget(self.rotation_combo)

        # Controls
        self.start_btn = QPushButton('Start Scanning')
        self.stop_btn = QPushButton('Stop Scanning')
        self.stop_btn.setEnabled(False)

        self.start_btn.clicked.connect(self._start_stream)
        self.stop_btn.clicked.connect(self._stop_stream)

        button_layout = QHBoxLayout()
        button_layout.addWidget(self.start_btn)
        button_layout.addWidget(self.stop_btn)

        main_layout.addLayout(url_layout)
        main_layout.addLayout(rotate_layout)
        main_layout.addWidget(self.preview_label)
        main_layout.addLayout(button_layout)
        main_layout.addWidget(self.info_label)
        self.setLayout(main_layout)
        self.resize(700, 520)

    def _load_known_faces(self):
        try:
            import face_recognition
            self.face_recognition_available = True
        except Exception:
            self.face_recognition_available = False
            self.info_label.setText('face_recognition not available.')
            return

        self.known_face_vectors = []
        self.known_candidate_ids = []
        self.known_candidate_names = []

        rows = get_known_face_vectors_for_candidates()
        for candidate_id, candidate_name, _, face_vector_text in rows:
            if not face_vector_text:
                continue
            try:
                vector = np.array(json.loads(face_vector_text), dtype=float)
                if vector.size == 128:
                    self.known_face_vectors.append(vector)
                    self.known_candidate_ids.append(candidate_id)
                    self.known_candidate_names.append(candidate_name)
            except Exception:
                continue

        if not self.known_face_vectors:
            for candidate_id, candidate_name, _, _ in get_all_candidates():
                candidate_dir = KNOWN_FACES_DIR / candidate_id
                if not candidate_dir.exists():
                    continue
                for image_file in sorted(candidate_dir.glob('*.jpg')) + sorted(candidate_dir.glob('*.png')):
                    try:
                        image = face_recognition.load_image_file(str(image_file))
                        encodings = face_recognition.face_encodings(image)
                        if encodings:
                            self.known_face_vectors.append(encodings[0])
                            self.known_candidate_ids.append(candidate_id)
                            self.known_candidate_names.append(candidate_name)
                    except Exception:
                        continue

        if self.known_candidate_names:
            known_names_text = ', '.join(self.known_candidate_names[:5])
            if len(self.known_candidate_names) > 5:
                known_names_text += f', ... (+{len(self.known_candidate_names) - 5} more)'
            status = f'Loaded {len(self.known_candidate_names)} known candidate face vectors: {known_names_text}'
        else:
            status = 'No known face vectors available. Register candidates in Admin Dashboard.'

        self.info_label.setText(status)

    def _parse_time(self, time_str: str):
        try:
            hours, minutes = [int(part) for part in time_str.split(':')]
            return dtime(hours, minutes)
        except Exception:
            return dtime(0, 0)

    def _match_face_encoding(self, face_encoding):
        if not self.known_face_vectors:
            return None, None, None

        try:
            import face_recognition
            face_distances = face_recognition.face_distance(self.known_face_vectors, face_encoding)
        except Exception:
            return None, None, None

        best_index = int(np.argmin(face_distances))
        best_score = float(face_distances[best_index])
        if best_score <= self.tolerance:
            return self.known_candidate_ids[best_index], self.known_candidate_names[best_index], best_score
        return None, None, best_score

    def _determine_log_type(self, candidate_id: str):
        now = datetime.now()
        current_time = now.time()
        today = date.today().isoformat()
        prior_logs = get_candidate_in_logs_for_date(candidate_id, today)
        has_check_in = any(log_type == 'In' for log_type, _, _ in prior_logs)
        has_check_out = any(log_type == 'Out' for log_type, _, _ in prior_logs)

        if current_time < self.entry_time:
            return None
        if current_time < self.late_time:
            if has_check_in:
                return None
            return 'In', 'Present', False
        if current_time < self.exit_time:
            if has_check_in:
                return None
            return 'In', 'Late', False
        if current_time <= self.checkout_cutoff_time:
            # Allow Out logging even when In was not previously recorded
            if has_check_out:
                return None
            return 'Out', 'Checked Out', False
        return None

    def _determine_log_type_by_clock(self):
        """Determine log_type/status using only configured times (no prior-log checks)."""
        now = datetime.now()
        current_time = now.time()
        if current_time < self.entry_time:
            return None
        if current_time < self.late_time:
            return 'In', 'Present', False
        if current_time < self.exit_time:
            return 'In', 'Late', False
        if current_time <= self.checkout_cutoff_time:
            return 'Out', 'Checked Out', False
        return None

    def _test_url(self):
        """Test if the stream URL is valid."""
        url = self.url_input.text().strip()
        if not url:
            QMessageBox.warning(self, 'Error', 'Please enter a stream URL.')
            return

        self.info_label.setText('Testing stream URL...')
        import requests
        try:
            # Quick HTTP probe for MJPEG
            if url.startswith('http'):
                try:
                    r = requests.get(url, timeout=5, stream=True)
                    if r.status_code == 200:
                        QMessageBox.information(self, 'Success', 'Stream URL responded HTTP 200 OK')
                        if self.mode == 'cctv':
                            self.config['cctv_stream_url'] = url
                        else:
                            self.config['phone_stream_url'] = url
                        save_config(self.config)
                        self.info_label.setText(f'Stream OK. Ready to scan. Known faces: {len(self.known_candidate_names)}')
                        r.close()
                        return
                    else:
                        # fallthrough to cv2 test
                        r.close()
                except Exception:
                    pass

            # Fallback to cv2 capture (handles RTSP/MJPEG)
            cap = cv2.VideoCapture(url)
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            ret, frame = cap.read()
            cap.release()
            if ret and frame is not None:
                QMessageBox.information(self, 'Success', f'Stream URL is valid!\nResolution: {frame.shape[1]}x{frame.shape[0]}')
                if self.mode == 'cctv':
                    self.config['cctv_stream_url'] = url
                else:
                    self.config['phone_stream_url'] = url
                save_config(self.config)
                self.info_label.setText(f'Stream OK. Ready to scan. Known faces: {len(self.known_candidate_names)}')
            else:
                QMessageBox.warning(self, 'Error', 'Cannot read from stream. Check if IP Webcam is running or URL is correct.')
                self.info_label.setText('Stream test failed.')
        except Exception as e:
            QMessageBox.warning(self, 'Error', f'Stream error: {e}')
            self.info_label.setText(f'Error: {e}')

    def _start_stream(self):
        url = self.url_input.text().strip()
        if not url:
            QMessageBox.warning(self, 'Error', 'Please enter a stream URL.')
            return

        if self.stream_thread is not None:
            return

        self.stream_thread = StreamReaderThread(url)
        self.stream_thread.frame_ready.connect(self._process_frame)
        self.stream_thread.error_occurred.connect(self._on_stream_error)
        self.stream_thread.status_update.connect(self.info_label.setText)
        self.stream_thread.start()

        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.url_input.setEnabled(False)
        self.url_clear_btn.setEnabled(False)
        self.info_label.setText('Scanning phone camera stream...')
        self.camera_started.emit(self.camera_name)

    def _stop_stream(self):
        was_running = self.stream_thread is not None
        if self.stream_thread:
            self.stream_thread.stop()
            self.stream_thread.wait()
            self.stream_thread = None

        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.url_input.setEnabled(True)
        self.url_clear_btn.setEnabled(True)
        self.info_label.setText('Scanning stopped.')
        self.preview_label.clear()
        self.preview_label.setText('Stream preview will appear here.')
        if was_running:
            self.camera_stopped.emit(self.camera_name)

    def _on_stream_error(self, error_msg: str):
        self._stop_stream()
        self.info_label.setText(f'Stream error: {error_msg}')
        QMessageBox.warning(self, 'Stream Error', error_msg)

    def _process_frame(self, frame):
        if frame is None:
            return

        frame = self._apply_rotation(frame)
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        display_frame = frame.copy()
        face_names = []

        if self.face_recognition_available:
            try:
                import face_recognition
                small_frame = cv2.resize(rgb_frame, (0, 0), fx=0.5, fy=0.5)
                face_locations = face_recognition.face_locations(small_frame, model='hog')
                face_encodings = face_recognition.face_encodings(small_frame, face_locations)

                for face_location, face_encoding in zip(face_locations, face_encodings):
                    top, right, bottom, left = [int(v * 2) for v in face_location]
                    candidate_id, candidate_name, score = self._match_face_encoding(face_encoding)
                    snapshot_path = self._save_detected_face(candidate_id or 'unknown', frame, (top, right, bottom, left))

                    if candidate_id is not None:
                        log_result = self._determine_log_type(candidate_id)
                        if log_result is not None:
                            log_type, status, blocked = log_result
                            if blocked:
                                self.info_label.setText(
                                    f'Check-out without prior check-in for {candidate_name}. Logged as warning.'
                                )
                            if self.last_logged_candidate_id != candidate_id or (time.time() - self.last_log_time) > 10:
                                log_attendance_log(candidate_id, candidate_name, log_type, status, snapshot_path or '')
                                self.last_logged_candidate_id = candidate_id
                                self.last_log_time = time.time()
                                face_names.append(candidate_name)
                    else:
                        if snapshot_path and (time.time() - self.last_log_time) > 8:
                            try:
                                from .database import register_unknown_and_log
                                vector = None
                                try:
                                    vector = face_encoding.tolist() if hasattr(face_encoding, 'tolist') else list(map(float, face_encoding))
                                except Exception:
                                    vector = None
                                # determine log type/status by clock for unknowns
                                log_result = self._determine_log_type_by_clock()
                                if log_result is not None:
                                    lt, st, _ = log_result
                                else:
                                    lt, st = 'Unknown', 'Unknown'
                                register_unknown_and_log(snapshot_path, face_vector=vector, log_type=lt, status=st)
                            except Exception:
                                # fallback to legacy logger
                                log_unknown_attendance(snapshot_path)

                            self.last_log_time = time.time()
                            face_names.append('Unknown')

                    identity_label = f"{candidate_id}: {candidate_name}" if candidate_id and candidate_name else 'Unknown'
                    cv2.rectangle(display_frame, (left, top), (right, bottom), (0, 255, 0), 2)
                    label_y = top - 10 if top - 10 > 10 else top + 20
                    cv2.putText(display_frame, identity_label, (left, label_y), cv2.FONT_HERSHEY_SIMPLEX, 0.75, (0, 255, 0), 2)

            except Exception as exc:
                print(f'face_recognition error: {exc}')

        self._show_image(display_frame)
        if face_names:
            self.info_label.setText('Detected: ' + ', '.join(face_names))

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
        photo_name = f'{user_id}_{int(time.time())}.jpg'
        photo_path = user_dir / photo_name
        cv2.imwrite(str(photo_path), face_crop)
        return str(photo_path)

    def _show_image(self, frame):
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        h, w, ch = rgb.shape
        bytes_per_line = ch * w
        qt_image = QImage(rgb.data, w, h, bytes_per_line, QImage.Format.Format_RGB888)
        pixmap = QPixmap.fromImage(qt_image)
        scaled = pixmap.scaled(self.preview_label.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.preview_label.setPixmap(scaled)
        self.frame_captured.emit(rgb)  # Emit frame for dock preview

    def _apply_rotation(self, frame):
        rotation_map = {
            '0°': None,
            '90°': cv2.ROTATE_90_CLOCKWISE,
            '180°': cv2.ROTATE_180,
            '270°': cv2.ROTATE_90_COUNTERCLOCKWISE,
        }
        angle = self.rotation_combo.currentText()
        if angle in rotation_map and rotation_map[angle] is not None:
            return cv2.rotate(frame, rotation_map[angle])
        return frame

    def closeEvent(self, event):
        self._stop_stream()
        super().closeEvent(event)
