"""Database models and utilities for attendance system."""
import sqlite3
import os
import shutil
import time
import json
from datetime import datetime
from pathlib import Path
import hashlib
import secrets

DB_PATH = Path(__file__).parent.parent / 'attendance.db'
PROJECT_ROOT = Path(__file__).parent.parent
KNOWN_FACES_DIR = PROJECT_ROOT / 'known_faces'
ATTENDANCE_PHOTOS_DIR = PROJECT_ROOT / 'attendance_photos'
UNKNOWN_FACE_DIR = PROJECT_ROOT / 'dataset' / 'unknown'


def _ensure_directories():
    KNOWN_FACES_DIR.mkdir(parents=True, exist_ok=True)
    ATTENDANCE_PHOTOS_DIR.mkdir(parents=True, exist_ok=True)
    UNKNOWN_FACE_DIR.mkdir(parents=True, exist_ok=True)


def _serialize_vector(vector):
    if vector is None:
        return None
    return json.dumps([float(x) for x in vector])


def _deserialize_vector(vector_text):
    if not vector_text:
        return None
    try:
        return [float(x) for x in json.loads(vector_text)]
    except Exception:
        return None


def init_database():
    _ensure_directories()
    conn = sqlite3.connect(str(DB_PATH))
    cursor = conn.cursor()
    # cursor.execute("DROP TABLE IF EXISTS admins")
# Create Admins Table with Email Column
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS admins (
            username TEXT PRIMARY KEY,
            email TEXT NOT NULL,
            password_hash TEXT NOT NULL,
            salt TEXT NOT NULL,
            created_at TEXT DEFAULT (STRFTIME('%Y-%m-%d %H:%M:%S', 'now', 'localtime'))
        )
    ''')
    # Candidate registration schema
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS personal_details (
            candidate_id TEXT PRIMARY KEY,
            candidate_name TEXT NOT NULL,
            center_image_path TEXT,
            department TEXT
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS face_vector_image (
            serial_no INTEGER PRIMARY KEY AUTOINCREMENT,
            candidate_id TEXT NOT NULL,
            pose_type TEXT NOT NULL,
            face_vector TEXT,
            FOREIGN KEY (candidate_id) REFERENCES personal_details (candidate_id) ON DELETE CASCADE
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS attendance_logs (
            log_id INTEGER PRIMARY KEY AUTOINCREMENT,
            candidate_id TEXT,
            candidate_name TEXT,
            log_time TEXT DEFAULT (STRFTIME('%Y-%m-%d %H:%M:%S', 'now', 'localtime')),
            log_type TEXT,
            status TEXT,
            captured_image_path TEXT,
            FOREIGN KEY (candidate_id) REFERENCES personal_details (candidate_id) ON DELETE CASCADE
        )
    ''')

    conn.commit()
    conn.close()


def get_connection():
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute('PRAGMA foreign_keys = ON')
    return conn

# ==================== Admin Authentication Functions ====================
def hash_password(password: str, salt: str = None) -> tuple[str, str]:
    """Applies unique cryptographic salting configurations."""
    if salt is None:
        salt = secrets.token_hex(16)  # Creates a totally unique 32-character string
    
    salted_password = salt + password
    password_hash = hashlib.sha256(salted_password.encode('utf-8')).hexdigest()
    return password_hash, salt

def register_admin(username: str, email: str, password: str) -> tuple[bool, str]:
    """Registers an admin safely. Prints any hidden database errors to terminal."""
    username = username.strip().lower()
    email = email.strip().lower()
    
    if not username or not email or not password:
        return False, "All fields are required."

    try:
        conn = get_connection()
        cursor = conn.cursor()
        
        # 1. Check if username exists
        cursor.execute("SELECT 1 FROM admins WHERE username = ?", (username,))
        if cursor.fetchone():
            conn.close()
            return False, "Username already exists."
        
        # 2. Scramble password securely using our Salt mechanism
        password_hash, salt = hash_password(password)
        
        # 3. Write data to the table
        cursor.execute(
            "INSERT INTO admins (username, email, password_hash, salt) VALUES (?, ?, ?, ?)",
            (username, email, password_hash, salt)
        )
        conn.commit()
        conn.close()
        return True, "Registration successful!"
        
    except sqlite3.Error as sqle:
        # Crucial: This exposes precisely why SQLite rejects your save requests
        print(f"!!! CRITICAL SQLITE ERROR: {sqle}")
        return False, f"Database write failure: {sqle}"
    except Exception as e:
        print(f"General registration error: {e}")
        return False, f"Error: {str(e)}"

def hash_password1(password: str, salt: str = None) -> tuple[str, str]:
    """Hashes a password using SHA-256 and a secure salt."""
    if salt is None:
        salt = secrets.token_hex(16)
    salted_password = salt + password
    password_hash = hashlib.sha256(salted_password.encode('utf-8')).hexdigest()
    return password_hash, salt


def register_admin1(username: str, email: str, password: str) -> tuple[bool, str]:
    """Registers a new admin with an email address."""
    username = username.strip().lower()
    email = email.strip().lower()
    
    if not username or not email or not password:
        return False, "All fields are required."
    if "@" not in email or "." not in email:
        return False, "Please enter a valid email address."
    if len(password) < 6:
        return False, "Password must be at least 6 characters long."

    try:
        conn = get_connection()
        cursor = conn.cursor()
        
        cursor.execute("SELECT 1 FROM admins WHERE username = ?", (username,))
        if cursor.fetchone():
            conn.close()
            return False, "Username already exists."
        
        password_hash, salt = hash_password(password)
        
        cursor.execute(
            "INSERT INTO admins (username, email, password_hash, salt) VALUES (?, ?, ?, ?)",
            (username, email, password_hash, salt)
        )
        conn.commit()
        conn.close()
        return True, "Registration successful!"
    except Exception as e:
        return False, f"Database error: {str(e)}"


def verify_admin_login(username: str, password: str) -> bool:
    """Verifies admin credentials against secure database hashes."""
    username = username.strip().lower()
    try:
        conn = get_connection()
        cursor = conn.cursor()
        
        # FIX 1: Explicitly select BOTH password_hash AND salt
        cursor.execute("SELECT password_hash, salt FROM admins WHERE username = ?", (username,))
        row = cursor.fetchone()
        conn.close()
        
        if not row:
            return False
            
        # FIX 2: Unpack the tuple correctly into string variables
        stored_hash, salt = row
        
        # FIX 3: Pass the retrieved 'salt' into hash_password so it creates the identical hash
        incoming_hash, _ = hash_password(password, salt)
        
        # Safe comparison
        return secrets.compare_digest(stored_hash, incoming_hash)
        
    except Exception as e:
        print(f"Login verification error: {e}")
        return False


def verify_admin_email(username: str, email: str) -> bool:
    """Checks if the username matching the given email exists."""
    username = username.strip().lower()
    email = email.strip().lower()
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT 1 FROM admins WHERE username = ? AND email = ?", (username, email))
        row = cursor.fetchone()
        conn.close()
        return row is not None
    except Exception as e:
        print(f"Email verification error: {e}")
        return False


def update_admin_password(username: str, new_password: str) -> bool:
    """Updates the password for a verified admin account."""
    username = username.strip().lower()
    try:
        password_hash, salt = hash_password(new_password)
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE admins SET password_hash = ?, salt = ? WHERE username = ?",
            (password_hash, salt, username)
        )
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f"Password update error: {e}")
        return False


def get_admin(username: str):
    """Return (username, email) for the given admin username, or None."""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT username, email FROM admins WHERE username = ?', (username,))
        row = cursor.fetchone()
        conn.close()
        return row
    except Exception as e:
        print(f"Error fetching admin: {e}")
        return None
def log_attendance_log(candidate_id: str, candidate_name: str, log_type: str, status: str, captured_image_path: str) -> bool:
    try:
        conn = get_connection()
        cursor = conn.cursor()
        current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        cursor.execute(
            '''
            INSERT INTO attendance_logs (candidate_id, candidate_name, log_time, log_type, status, captured_image_path)
            VALUES (?, ?, ?, ?, ?, ?)
            ''',
            (candidate_id, candidate_name, current_time, log_type, status, captured_image_path),
        )
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f"Error logging attendance: {e}")
        return False


def log_unknown_attendance(captured_image_path: str) -> bool:
    # Backwards-compatible wrapper: register a proper unknown entry and log attendance
    return register_unknown_and_log(str(captured_image_path))


def _generate_id_for_unkown() -> str:
    """Generate a unique candidate_id for unknown persons.

    Looks up existing candidate_ids that start with 'unknown' and finds the
    maximum numeric suffix, then returns 'unknown{n+1}'.
    """
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT candidate_id FROM personal_details WHERE candidate_id LIKE 'unknown%'")
        rows = cursor.fetchall()
        conn.close()

        max_num = 0
        for (cid,) in rows:
            if not cid:
                continue
            # strip the leading 'unknown' text and parse trailing integer
            suffix = cid.replace('unknown', '')
            try:
                num = int(suffix)
                if num > max_num:
                    max_num = num
            except Exception:
                continue

        return f'unknown{max_num + 1}'
    except Exception as e:
        print(f"Error generating unknown id: {e}")
        return f'unknown{int(time.time())}'


def register_unknown_and_log(image_path: str, face_vector=None, log_type: str = None, status: str = None) -> bool:
    """Register an unknown candidate, save face vector, and log attendance.

    - Generates a unique id like 'unknown1', 'unknown2', ...
    - Uses candidate_name = 'unknow' (per spec)
    - Stores the provided image_path as the center_image_path
    - Saves the face_vector into `face_vector_image` with pose_type 'center'
    - Logs an attendance record using log_attendance_log with type/status 'Unknown'
    """
    try:
        candidate_id = _generate_id_for_unkown()
        candidate_name = 'unknow'
        department = None

        # Register in personal_details (stores center image path)
        if not register_candidate(candidate_id, candidate_name, department, image_path):
            return False

        # Save face vector record
        try:
            add_face_vector(candidate_id, 'center', face_vector)
        except Exception:
            pass

        # Log attendance using provided log_type/status or fallback to 'Unknown'
        lt = log_type if log_type is not None else 'Unknown'
        st = status if status is not None else 'Unknown'
        return log_attendance_log(candidate_id, candidate_name, lt, st, image_path)
    except Exception as e:
        print(f"Error registering unknown and logging: {e}")
        return False


def get_attendance_logs_by_date(log_date: str):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        '''
        SELECT log_id, candidate_id, candidate_name, log_time, log_type, status, captured_image_path
        FROM attendance_logs
        WHERE date(log_time) = ?
        ORDER BY log_time DESC
        ''',
        (log_date,),
    )
    records = cursor.fetchall()
    conn.close()
    return records


def get_attendance_with_absent(log_date: str):
    """Return attendance rows for display including absent candidates.

    Each returned row matches the schema returned by get_attendance_logs_by_date:
    (log_id, candidate_id, candidate_name, log_time, log_type, status, captured_image_path)

    For absent candidates (present in personal_details but no attendance log for the date)
    a single row is returned with log_id=None, log_time=log_date, log_type='', status='absent', captured_image_path=''.

    For present candidates we return up to two rows (first two logs) in chronological order.
    Unknown candidates (candidate_id starting with 'unknown') will have their `status` set to '' in displayed rows.
    """
    conn = get_connection()
    cursor = conn.cursor()

    # Fetch all logs for the date
    cursor.execute(
        '''
        SELECT log_id, candidate_id, candidate_name, log_time, log_type, status, captured_image_path
        FROM attendance_logs
        WHERE date(log_time) = ?
        ORDER BY candidate_id, log_time ASC
        ''',
        (log_date,)
    )
    logs = cursor.fetchall()

    # Map candidate_id -> list of logs
    logs_by_candidate = {}
    for row in logs:
        cid = row[1]
        logs_by_candidate.setdefault(cid, []).append(row)

    # Fetch all registered candidates
    cursor.execute('SELECT candidate_id, candidate_name FROM personal_details ORDER BY candidate_name')
    candidates = cursor.fetchall()

    result_rows = []

    # For each registered candidate, either add their logs (up to 2) or an absent row
    for cid, cname in candidates:
        if cid in logs_by_candidate:
            entries = logs_by_candidate[cid][:2]
            for entry in entries:
                log_id, candidate_id, candidate_name, log_time, log_type, status, captured_image_path = entry
                # For unknown ids, blank the status as per spec
                if candidate_id.startswith('unknown'):
                    status = ''
                result_rows.append((log_id, candidate_id, candidate_name, log_time, log_type or '', status or '', captured_image_path or ''))
            # remove processed candidate from map
            logs_by_candidate.pop(cid, None)
        else:
            # absent row: timestamp is date only
            result_rows.append((None, cid, cname, log_date, '', 'absent', ''))

    # Any remaining logs for candidate_ids not in personal_details (should be rare) - include them
    for cid, entries in logs_by_candidate.items():
        for entry in entries[:2]:
            log_id, candidate_id, candidate_name, log_time, log_type, status, captured_image_path = entry
            if candidate_id.startswith('unknown'):
                status = ''
            result_rows.append((log_id, candidate_id, candidate_name, log_time, log_type or '', status or '', captured_image_path or ''))

    conn.close()
    return result_rows


def get_candidate_in_logs_for_date(candidate_id: str, log_date: str):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        '''
        SELECT log_type, status, log_time
        FROM attendance_logs
        WHERE candidate_id = ? AND date(log_time) = ?
        ORDER BY log_time ASC
        ''',
        (candidate_id, log_date),
    )
    rows = cursor.fetchall()
    conn.close()
    return rows


def get_known_face_vectors_for_candidates():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        '''
        SELECT p.candidate_id, p.candidate_name, f.pose_type, f.face_vector
        FROM face_vector_image f
        JOIN personal_details p ON f.candidate_id = p.candidate_id
        WHERE f.face_vector IS NOT NULL
        ''',
    )
    rows = cursor.fetchall()
    conn.close()
    return rows


def get_attendance_summary_last_days(days: int = 7):
    """Get attendance count per candidate in the last N days."""
    conn = sqlite3.connect(str(DB_PATH))
    cursor = conn.cursor()
    cursor.execute('''
        SELECT candidate_name, COUNT(log_id) as count
        FROM attendance_logs
        WHERE datetime(log_time) >= datetime('now', 'localtime', '-' || ? || ' days')
        GROUP BY candidate_id, candidate_name
        ORDER BY count DESC
    ''', (days,))
    summary = cursor.fetchall()
    conn.close()
    return summary


def get_attendance_logs_last_days(days: int = 7):
    """Fetch attendance logs for the last N days."""
    conn = sqlite3.connect(str(DB_PATH))
    cursor = conn.cursor()
    cursor.execute('''
        SELECT log_id, candidate_id, candidate_name, log_time, log_type, status, captured_image_path
        FROM attendance_logs
        WHERE datetime(log_time) >= datetime('now', 'localtime', '-' || ? || ' days')
        ORDER BY log_time DESC
    ''', (days,))
    records = cursor.fetchall()
    conn.close()
    return records


# ==================== Candidate Registration Functions ====================

def register_candidate(candidate_id: str, candidate_name: str, department: str, center_image_path: str = None) -> bool:
    """Register a new candidate with personal details."""
    try:
        conn = sqlite3.connect(str(DB_PATH))
        cursor = conn.cursor()
        cursor.execute('''
            INSERT OR REPLACE INTO personal_details (candidate_id, candidate_name, center_image_path, department)
            VALUES (?, ?, ?, ?)
        ''', (candidate_id, candidate_name, center_image_path, department))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f"Error registering candidate: {e}")
        return False


def add_face_vector(candidate_id: str, pose_type: str, face_vector=None) -> bool:
    """Add a face vector image record for a candidate pose."""
    try:
        vector_text = _serialize_vector(face_vector) if face_vector else None
        conn = sqlite3.connect(str(DB_PATH))
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO face_vector_image (candidate_id, pose_type, face_vector)
            VALUES (?, ?, ?)
        ''', (candidate_id, pose_type, vector_text))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f"Error adding face vector: {e}")
        return False


def update_face_vector(candidate_id: str, pose_type: str, face_vector=None) -> bool:
    """Update or insert a face vector for a specific pose."""
    try:
        vector_text = _serialize_vector(face_vector) if face_vector else None
        conn = sqlite3.connect(str(DB_PATH))
        cursor = conn.cursor()
        cursor.execute('''
            INSERT OR REPLACE INTO face_vector_image (candidate_id, pose_type, face_vector)
            VALUES (?, ?, ?)
        ''', (candidate_id, pose_type, vector_text))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f"Error updating face vector: {e}")
        return False


def get_all_candidates():
    """Fetch all registered candidates."""
    try:
        conn = sqlite3.connect(str(DB_PATH))
        cursor = conn.cursor()
        cursor.execute('SELECT candidate_id, candidate_name, department, center_image_path FROM personal_details ORDER BY candidate_name')
        candidates = cursor.fetchall()
        conn.close()
        return candidates
    except Exception as e:
        print(f"Error fetching candidates: {e}")
        return []


def get_candidate(candidate_id: str):
    """Fetch a specific candidate by ID."""
    try:
        conn = sqlite3.connect(str(DB_PATH))
        cursor = conn.cursor()
        cursor.execute('SELECT candidate_id, candidate_name, department, center_image_path FROM personal_details WHERE candidate_id = ?', (candidate_id,))
        candidate = cursor.fetchone()
        conn.close()
        return candidate
    except Exception as e:
        print(f"Error fetching candidate: {e}")
        return None


def get_candidate_face_vectors(candidate_id: str):
    """Fetch all face vectors for a candidate."""
    try:
        conn = sqlite3.connect(str(DB_PATH))
        cursor = conn.cursor()
        cursor.execute('''
            SELECT serial_no, pose_type, face_vector FROM face_vector_image 
            WHERE candidate_id = ? ORDER BY pose_type
        ''', (candidate_id,))
        vectors = cursor.fetchall()
        conn.close()
        return vectors
    except Exception as e:
        print(f"Error fetching face vectors: {e}")
        return []


def delete_candidate(candidate_id: str) -> bool:
    """Delete a candidate and all associated face vectors (cascading delete)."""
    try:
        conn = sqlite3.connect(str(DB_PATH))
        cursor = conn.cursor()
        
        # Get candidate details to delete image files
        cursor.execute('SELECT center_image_path FROM personal_details WHERE candidate_id = ?', (candidate_id,))
        result = cursor.fetchone()
        if result:
            center_image_path = result[0]
            if center_image_path and Path(center_image_path).exists():
                Path(center_image_path).unlink()
        
        # Delete face vectors (cascading due to FOREIGN KEY constraint)
        cursor.execute('DELETE FROM face_vector_image WHERE candidate_id = ?', (candidate_id,))
        
        # Delete candidate
        cursor.execute('DELETE FROM personal_details WHERE candidate_id = ?', (candidate_id,))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f"Error deleting candidate: {e}")
        return False


def get_candidate_face_vector_by_pose(candidate_id: str, pose_type: str):
    """Fetch a specific face vector for a candidate and pose type."""
    try:
        conn = sqlite3.connect(str(DB_PATH))
        cursor = conn.cursor()
        cursor.execute('''
            SELECT serial_no, face_vector FROM face_vector_image 
            WHERE candidate_id = ? AND pose_type = ?
        ''', (candidate_id, pose_type))
        result = cursor.fetchone()
        conn.close()
        return result
    except Exception as e:
        print(f"Error fetching face vector: {e}")
        return None


# Initialize DB on module load
init_database()
