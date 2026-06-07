from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel
from .candidate_records_window import CandidateRecordsWindow
from .attendance_records_window import AttendanceRecordsWindow


class AdminWindow(QWidget):
    """Admin window launcher for candidate and attendance records."""
    
    def __init__(self):
        super().__init__()
        self.setWindowTitle('Admin Dashboard')
        self.setMinimumWidth(400)
        self.setMinimumHeight(300)
        
        self.candidate_window = None
        self.attendance_window = None
        
        layout = QVBoxLayout()
        
        # Title
        title = QLabel('Admin Dashboard')
        title.setStyleSheet("font-size: 16px; font-weight: bold; color: #1f1f1f;")
        layout.addWidget(title)
        
        # Instructions
        instructions = QLabel(
            'Use the main window buttons to access:\n'
            '• Candidate Records - Register and manage candidates\n'
            '• Attendance Records - View attendance logs'
        )
        instructions.setStyleSheet("font-size: 12px; color: #666; margin: 20px;")
        layout.addWidget(instructions)
        
        layout.addStretch()
        self.setLayout(layout)
        
        self.tabs = None  # For backward compatibility with main_window.py
    
    def show_candidate_records(self):
        """Launch or focus the Candidate Records window."""
        if self.candidate_window is None or not self.candidate_window.isVisible():
            self.candidate_window = CandidateRecordsWindow(self)
        self.candidate_window.show()
        self.candidate_window.raise_()
        self.candidate_window.activateWindow()
    
    def show_attendance_records(self):
        """Launch or focus the Attendance Records window."""
        if self.attendance_window is None or not self.attendance_window.isVisible():
            self.attendance_window = AttendanceRecordsWindow(self)
        self.attendance_window.show()
        self.attendance_window.raise_()
        self.attendance_window.activateWindow()
    
    def setCurrentIndex(self, index: int):
        """Backward compatibility method for existing code.
        
        Args:
            index: 0 for candidate records (was User Management tab)
                   1 for attendance records (was Attendance Records tab)
        """
        if index == 0:
            self.show_candidate_records()
        elif index == 1:
            self.show_attendance_records()
