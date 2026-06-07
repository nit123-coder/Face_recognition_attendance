import json
import time
from datetime import datetime, date, time as dtime
from pathlib import Path

import cv2
import face_recognition
import numpy as np
from PySide6.QtCore import QThread, Signal

from .database import (
    get_all_candidates,
    get_known_face_vectors_for_candidates,
    get_candidate_in_logs_for_date,
    log_attendance_log,
    log_unknown_attendance,
    KNOWN_FACES_DIR,
    UNKNOWN_FACE_DIR,
)


class FaceMatchingWorker(QThread):
    frameReady = Signal(object)
    attendanceLogged = Signal(str, str, str, str, str)
    unknownDetected = Signal(str)
    warningRaised = Signal(str)
    errorOccurred = Signal(str)

    def __init__(self, camera_index: int = 0, tolerance: float = 0.45, entry_time: str = '09:00', late_time: str = '10:00', exit_time: str = '17:00', parent=None):
        super().__init__(parent)
        self.camera_index = camera_index
        self.tolerance = tolerance
        self.entry_time = self._parse_time(entry_time)
        self.late_time = self._parse_time(late_time)
        self.exit_time = self._parse_time(exit_time)
        self.checkout_cutoff_time = dtime(18, 0)
        self._running = False
        self.camera = None
        self.known_encodings = []
        self.known_candidates = []
        self.known_names = []
        self.last_logged = {}
        self.last_unknown_time = 0.0

    def run(self):
        self._load_known_faces()
        self.camera = self._open_camera(self.camera_index)
        if self.camera is None:
            self.errorOccurred.emit("Unable to open camera feed.")
            return

        self._running = True
        while self._running:
            ret, frame = self.camera.read()
            if not ret or frame is None:
                self.errorOccurred.emit("No frame returned from camera.")
                break

            frame = cv2.flip(frame, 1)
            rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            self._process_frame(frame, rgb_frame)
            self.msleep(80)

        if self.camera is not None:
            self.camera.release()
            self.camera = None

    def stop(self):
        self._running = False
        self.wait(1000)

    def _open_camera(self, index: int):
        for backend in (cv2.CAP_DSHOW, cv2.CAP_MSMF, cv2.CAP_ANY):
            cap = cv2.VideoCapture(index, backend)
            if cap.isOpened():
                return cap
            cap.release()
        return None

    def _load_known_faces(self):
        self.known_encodings = []
        self.known_candidates = []
        self.known_names = []

        rows = get_known_face_vectors_for_candidates()
        for candidate_id, candidate_name, _, face_vector_text in rows:
            if not face_vector_text:
                continue
            try:
                vector = np.array(json.loads(face_vector_text), dtype=float)
                if vector.size == 128:
                    self.known_encodings.append(vector)
                    self.known_candidates.append(candidate_id)
                    self.known_names.append(candidate_name)
                continue
            except Exception:
                pass

        if not self.known_encodings:
            self._load_known_faces_from_images()

    def _parse_time(self, time_str: str):
        try:
            hours, minutes = [int(part) for part in time_str.split(':')]
            return dtime(hours, minutes)
        except Exception:
            return dtime(0, 0)

    def _process_frame(self, frame, rgb_frame):
        display_frame = frame.copy()
        try:
            small_frame = cv2.resize(rgb_frame, (0, 0), fx=0.5, fy=0.5)
            face_locations = face_recognition.face_locations(small_frame, model='hog')
            face_encodings = face_recognition.face_encodings(small_frame, face_locations)

            for face_location, face_encoding in zip(face_locations, face_encodings):
                top, right, bottom, left = [int(v * 2) for v in face_location]
                candidate_id, candidate_name, score = self._match_face_encoding(face_encoding)
                cropped_path = self._save_face_snapshot(frame, (top, right, bottom, left), candidate_id or 'unknown')

                log_type = None
                status = None
                blocked = False
                if candidate_id is not None:
                    result = self._determine_log_type(candidate_id)
                    if result is not None:
                        log_type, status, blocked = result

                    if blocked:
                        message = (
                            f"Attempted check-in/out outside the configured window for {candidate_name}."
                        )
                        self.warningRaised.emit(message)

                    if candidate_id is not None and log_type is not None and self._should_log(candidate_id, log_type, status):
                        try:
                            success = log_attendance_log(candidate_id, candidate_name, log_type, status, cropped_path)
                            if not success:
                                # Emit an error so UI can display/log it
                                self.errorOccurred.emit(f"Failed to write attendance for {candidate_id}")
                            else:
                                self.attendanceLogged.emit(candidate_id, candidate_name, log_type, status, cropped_path)
                        except Exception as e:
                            self.errorOccurred.emit(f"Exception while logging attendance: {e}")
                else:
                    if time.time() - self.last_unknown_time > 8:
                        # Save full-frame image for unknown (do not crop)
                        try:
                            save_name = f"unknown_full_{int(time.time())}.jpg"
                            save_dir = UNKNOWN_FACE_DIR
                            save_dir.mkdir(parents=True, exist_ok=True)
                            full_path = save_dir / save_name
                            cv2.imwrite(str(full_path), frame)
                        except Exception:
                            full_path = cropped_path or ''

                        # Save unknown person entry, face vector, and attendance log
                        try:
                            # face_encoding is available in this scope
                            from .database import register_unknown_and_log
                            # pass face_encoding as vector (if available)
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

                            register_unknown_and_log(str(full_path), face_vector=vector, log_type=lt, status=st)
                        except Exception as e:
                            self.errorOccurred.emit(f"Failed to register unknown: {e}")

                        # signal and cooldown
                        # removed popup per spec; still emit unknown event for UI updates if needed
                        self.unknownDetected.emit(str(full_path))
                        self.last_unknown_time = time.time()

                identity_label = f"{candidate_id}: {candidate_name}" if candidate_id else 'Unknown'
                label_y = top - 10 if top - 10 > 10 else top + 20
                cv2.rectangle(display_frame, (left, top), (right, bottom), (0, 255, 0), 2)
                cv2.putText(display_frame, identity_label, (left, label_y), cv2.FONT_HERSHEY_SIMPLEX, 0.75, (0, 255, 0), 2)
        except Exception as exc:
            self.errorOccurred.emit(str(exc))
        finally:
            self.frameReady.emit(display_frame)

    def _load_known_faces_from_images(self):
        for candidate_id, candidate_name, _, _ in get_all_candidates():
            candidate_folder = KNOWN_FACES_DIR / candidate_id
            if not candidate_folder.exists():
                continue

            for image_file in sorted(candidate_folder.glob('*.jpg')) + sorted(candidate_folder.glob('*.png')):
                try:
                    image = face_recognition.load_image_file(str(image_file))
                    encodings = face_recognition.face_encodings(image)
                    if not encodings:
                        continue
                    self.known_encodings.append(encodings[0])
                    self.known_candidates.append(candidate_id)
                    self.known_names.append(candidate_name)
                except Exception:
                    continue

    def _match_face_encoding(self, face_encoding):
        # Use face distance matching to find the closest known candidate encoding.
        # The `tolerance` threshold controls acceptance: lower is stricter, higher is more permissive.
        if not self.known_encodings:
            return None, None, None

        face_distances = face_recognition.face_distance(self.known_encodings, face_encoding)
        best_index = int(np.argmin(face_distances))
        best_score = float(face_distances[best_index])
        if best_score <= self.tolerance:
            return self.known_candidates[best_index], self.known_names[best_index], best_score
        return None, None, best_score

    def _determine_log_type(self, candidate_id: str):
        # Determine based on clock + prior logs for known candidate
        def by_clock():
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

        result = by_clock()
        if result is None:
            return None

        # For known candidates, consult prior logs to avoid duplicate/invalid logs
        log_type, status, _ = result
        today = date.today().isoformat()
        prior_logs = get_candidate_in_logs_for_date(candidate_id, today)
        has_check_in = any(row[0] == 'In' for row in prior_logs)
        has_check_out = any(row[0] == 'Out' for row in prior_logs)

        if log_type == 'In':
            if has_check_in:
                return None
            return 'In', status, False
        if log_type == 'Out':
            # Allow Out to be logged even if In was not previously recorded.
            if has_check_out:
                return None
            return 'Out', status, False
        return None

    def _determine_log_type_by_clock(self):
        """Determine log_type/status using only the configured times (no prior-log checks).

        Useful for unknown candidates which are registered at detection time.
        Returns tuple (log_type, status, blocked) or None.
        """
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

    def _save_face_snapshot(self, frame, face_location, identity: str):
        top, right, bottom, left = face_location
        top = max(0, top)
        left = max(0, left)
        bottom = min(frame.shape[0], bottom)
        right = min(frame.shape[1], right)
        face_crop = frame[top:bottom, left:right]
        if face_crop.size == 0:
            return ''

        if identity == 'unknown':
            save_dir = UNKNOWN_FACE_DIR
            save_dir.mkdir(parents=True, exist_ok=True)
            file_name = f"unknown_{int(time.time())}.jpg"
        else:
            save_dir = KNOWN_FACES_DIR / identity
            save_dir.mkdir(parents=True, exist_ok=True)
            file_name = f"{identity}_{int(time.time())}.jpg"

        file_path = save_dir / file_name
        cv2.imwrite(str(file_path), face_crop)
        return str(file_path)

    def _should_log(self, candidate_id: str, log_type: str, status: str) -> bool:
        today = date.today().isoformat()
        prior_logs = get_candidate_in_logs_for_date(candidate_id, today)
        if log_type == 'In' and any(row[0] == 'In' for row in prior_logs):
            return False
        if log_type == 'Out' and any(row[0] == 'Out' for row in prior_logs):
            return False

        entry = self.last_logged.get(candidate_id)
        now = time.time()
        if entry is None:
            self.last_logged[candidate_id] = {'time': now, 'type': log_type, 'status': status}
            return True
        if now - entry['time'] > 12 or entry['type'] != log_type or entry['status'] != status:
            self.last_logged[candidate_id] = {'time': now, 'type': log_type, 'status': status}
            return True
        return False
