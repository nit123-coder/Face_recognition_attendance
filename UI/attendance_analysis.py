import sqlite3
import smtplib
from datetime import datetime
import calendar
from pathlib import Path
from email.message import EmailMessage

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QTableWidget, 
    QTableWidgetItem, QLabel, QHeaderView, 
    QWidget, QMessageBox
)
from PySide6.QtCore import Qt

# Safe mapping to find the database file path relative to your project layout
DB_PATH = Path(__file__).parent.parent / 'attendance.db'


# =====================================================================
# PRODUCTION REAL-WORLD EMAIL HELPER (Placed globally at the top)
# =====================================================================
def send_absent_email(manager_email: str, candidate_details: dict):
    """
    Sends a real automated email notification using SMTP securely.
    """
    # 1. Configuration Settings
    SMTP_SERVER = "smtp.gmail.com"       # Replace with your provider's SMTP server if not using Gmail
    SMTP_PORT = 465                     # Standard port for secure SSL connections
    SENDER_EMAIL = "your-email@gmail.com" # The email address sending the alerts
    SENDER_PASSWORD = "abcd efgh ijkl mnop" # Your 16-character App Password (NOT your login password)

    # 2. Build the Email Message Payload
    msg = EmailMessage()
    msg["Subject"] = f"🔴 ALERT: Absentee Notification - {candidate_details.get('name')}"
    msg["From"] = SENDER_EMAIL
    msg["To"] = manager_email

    body_content = f"""Hello Manager,

This is an automated operational alert from the Attendance Tracking System.

The following candidate was marked ABSENT during today's system evaluation:
• Candidate ID: {candidate_details.get('id')}
• Candidate Name: {candidate_details.get('name')}
• Department: {candidate_details.get('dept')}

Please follow up with the individual regarding their schedule parameters if this absence was unexcused.

Best regards,
Automated Security Dispatch Engine
"""
    msg.set_content(body_content)

    # 3. Establish Network Connection and Transmit
    try:
        with smtplib.SMTP_SSL(SMTP_SERVER, SMTP_PORT) as server:
            server.login(SENDER_EMAIL, SENDER_PASSWORD)
            server.send_message(msg)
        print(f"✅ Real email successfully sent to manager: {manager_email}")
        return True
    except Exception as e:
        print(f"❌ Failed to transmit alert email to {manager_email}. Error: {e}")
        return False


# =====================================================================
# ANALYTICS ENGINE (RAW DB DATA EXTRACTOR)
# =====================================================================
class AttendanceAnalyticsEngine:
    """Extracts, filters, and structures metrics directly from the DB."""
    
    def __init__(self, db_path):
        self.db_path = db_path

    def _get_raw_logs_and_details(self):
        """Fetches raw structured logs joined with employee context."""
        # This method is kept for compatibility; prefer calculate_metrics to
        # pull filtered monthly data. It returns all rows joined with details.
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()
        cursor.execute('''
            SELECT 
                l.candidate_id, 
                p.candidate_name, 
                p.department,
                l.log_time, 
                l.log_type, 
                l.status
            FROM attendance_logs l
            JOIN personal_details p ON l.candidate_id = p.candidate_id
            ORDER BY l.candidate_id, l.log_time ASC
        ''')
        rows = cursor.fetchall()
        conn.close()
        return rows

    def calculate_metrics(self, entry_threshold: str = '09:00', late_threshold: str = '10:00'):
        """Compute monthly metrics for the current system month.

        Rules (simplified):
        - Exclude candidate_ids starting with 'unknown'.
        - Consider the current calendar month (system date).
        - Each day a candidate has at least one log -> present for that day.
        - Absents = days_in_month - presents (weekends counted as workdays per spec).
        - Late: first In time > late_threshold.
        - Hours worked: sum of (Out - In) where both exist for a day; single log -> 0 hours.
        """
        # Determine current month
        now = datetime.now()
        month_str = now.strftime('%Y-%m')
        year = now.year
        month = now.month
        days_in_month = calendar.monthrange(year, month)[1]

        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()
        cursor.execute('''
            SELECT 
                l.candidate_id, 
                p.candidate_name, 
                p.department,
                l.log_time, 
                l.log_type, 
                l.status
            FROM attendance_logs l
            JOIN personal_details p ON l.candidate_id = p.candidate_id
            WHERE strftime('%Y-%m', l.log_time) = ?
              AND l.candidate_id NOT LIKE 'unknown%'
            ORDER BY l.candidate_id, l.log_time ASC
        ''', (month_str,))
        rows = cursor.fetchall()
        conn.close()

        # Build per-candidate per-date logs
        timeline = {}
        profiles = {}
        for c_id, name, dept, log_time_str, log_type, status in rows:
            profiles[c_id] = {'name': name, 'dept': dept}
            try:
                dt = datetime.strptime(log_time_str, "%Y-%m-%d %H:%M:%S")
            except ValueError:
                dt = datetime.strptime(log_time_str.split(".")[0], "%Y-%m-%d %H:%M:%S")
            date_key = dt.date()
            timeline.setdefault(c_id, {}).setdefault(date_key, []).append({'time': dt, 'type': log_type, 'status': status})

        # Prepare thresholds
        def parse_time_str(tstr):
            h, m = tstr.split(':')
            return int(h), int(m)

        late_h, late_m = parse_time_str(late_threshold)

        candidate_metrics = {}
        for c_id, dates in timeline.items():
            presents = 0
            lates = 0
            total_seconds = 0.0

            for date_key, day_logs in dates.items():
                # sort logs chronologically
                times_by_type = {'In': [], 'Out': []}
                for l in day_logs:
                    if l['type'] == 'In':
                        times_by_type['In'].append(l['time'])
                    elif l['type'] == 'Out':
                        times_by_type['Out'].append(l['time'])

                if times_by_type['In']:
                    presents += 1
                    first_in = min(times_by_type['In'])
                    # late if first_in time > late_threshold
                    if (first_in.hour, first_in.minute) > (late_h, late_m):
                        lates += 1

                    if times_by_type['Out']:
                        last_out = max(times_by_type['Out'])
                        if last_out > first_in:
                            total_seconds += (last_out - first_in).total_seconds()

            total_hours = round(total_seconds / 3600.0, 2)
            absents = max(0, days_in_month - presents)

            candidate_metrics[c_id] = {
                'name': profiles.get(c_id, {}).get('name', ''),
                'dept': profiles.get(c_id, {}).get('dept', ''),
                'presents': presents,
                'absents': absents,
                'lates': lates,
                'hours': total_hours
            }

        # For candidates who have no logs this month but are in personal_details,
        # include them as fully absent
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()
        cursor.execute('SELECT candidate_id, candidate_name, department FROM personal_details')
        all_cands = cursor.fetchall()
        conn.close()

        for cid, cname, cdept in all_cands:
            if cid.startswith('unknown'):
                continue
            if cid not in candidate_metrics:
                candidate_metrics[cid] = {
                    'name': cname,
                    'dept': cdept or '',
                    'presents': 0,
                    'absents': days_in_month,
                    'lates': 0,
                    'hours': 0.0
                }

        return candidate_metrics


# =====================================================================
# QDIALOG ANALYTICS COMPONENT LAYOUT
# =====================================================================
class AttendanceAnalyticsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("System Performance & Attendance Analytics")
        self.resize(1050, 650)
        
        self.engine = AttendanceAnalyticsEngine(DB_PATH)
        self.init_ui()
        self.load_analytics_dashboard()

    def init_ui(self):
        main_layout = QVBoxLayout(self)
        
        header = QLabel("Monthly Attendance Analytics Dashboard")
        header.setStyleSheet("font-size: 18px; font-weight: bold; padding: 5px; color: white;")
        main_layout.addWidget(header)
        grid_widget = QWidget()
        grid_layout = QVBoxLayout(grid_widget)
        grid_layout.setContentsMargins(0, 5, 0, 0)

        grid_layout.addWidget(QLabel("<b>📊 Monthly Comprehensive Analysis Grid</b>"))

        self.table = QTableWidget()
        self.table.setColumnCount(7)  # Fixed column dimension mapping
        self.table.setHorizontalHeaderLabels([
            "Candidate ID", "Candidate Name", "Department", 
            "Total Presents", "Absents Logged", "Late Counts", "Total Hours Worked"
        ])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)

        grid_layout.addWidget(self.table)
        grid_widget.setLayout(grid_layout)

        main_layout.addWidget(grid_widget)

    def load_analytics_dashboard(self):
        """Orchestrates DB pipeline extraction and populates widgets securely."""
        try:
            metrics = self.engine.calculate_metrics()

            self.table.setRowCount(0)
            for c_id, data in metrics.items():
                row_idx = self.table.rowCount()
                self.table.insertRow(row_idx)
                
                self.table.setItem(row_idx, 0, QTableWidgetItem(str(c_id)))
                self.table.setItem(row_idx, 1, QTableWidgetItem(data["name"]))
                self.table.setItem(row_idx, 2, QTableWidgetItem(data["dept"]))
                self.table.setItem(row_idx, 3, QTableWidgetItem(str(data["presents"])))
                
                absent_item = QTableWidgetItem(str(data["absents"]))
                if data["absents"] > 0:
                    absent_item.setForeground(Qt.red)
                self.table.setItem(row_idx, 4, absent_item)
                
                late_item = QTableWidgetItem(str(data["lates"]))
                if data["lates"] > 2:
                    late_item.setForeground(Qt.darkYellow)
                self.table.setItem(row_idx, 5, late_item)
                
                self.table.setItem(row_idx, 6, QTableWidgetItem(f"{data['hours']} hrs"))

        except Exception as e:
            QMessageBox.critical(self, "Database Engine Error", f"An error occurred pulling analytics metadata: {str(e)}")