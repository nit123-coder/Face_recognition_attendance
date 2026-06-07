import sys
import importlib.util
from PySide6.QtCore import Qt
from UI.main_window import MainWindow
from PySide6.QtWidgets import (
    QApplication, QDialog, QLineEdit, QLabel, QPushButton,
    QVBoxLayout, QFormLayout, QWidget, QHBoxLayout, QMessageBox
)
from UI import database

def _module_exists(name: str) -> bool: 
    return importlib.util.find_spec(name) is not None

class ForgotPasswordDialog(QDialog):
    """Dialog that validates account identity before presenting password reset inputs."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Dialog)
        self.setWindowModality(Qt.ApplicationModal)
        self.setStyleSheet('background-color: black;')
        self.setWindowTitle('Reset Password')
        self._build_ui()

    def _build_ui(self):
        self.setMinimumSize(1000, 600)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        container = QWidget(self)
        container.setStyleSheet(
            'background-color: gray; border-radius: 18px; border: 1px solid #c8ccd4;'
        )
        container_layout = QVBoxLayout(container)
        container_layout.setContentsMargins(24, 24, 24, 24)
        container_layout.setSpacing(16)

        title_label = QLabel('Reset Admin Password')
        title_label.setAlignment(Qt.AlignCenter)
        title_label.setStyleSheet('border:none; font-size: 18px; font-weight: bold;')

        # Step 1 Fields: Identity Verification
        self.username_edit = QLineEdit()
        self.username_edit.setPlaceholderText('Enter your username')
        self.email_edit = QLineEdit()
        self.email_edit.setPlaceholderText('Enter registered email address')

        self.form_layout = QFormLayout()
        self.form_layout.setLabelAlignment(Qt.AlignRight)
        self.form_layout.setFormAlignment(Qt.AlignCenter)
        self.form_layout.addRow('Username:', self.username_edit)
        self.form_layout.addRow('Email:', self.email_edit)

        # Step 2 Fields: Instantiated dynamically but hidden at start
        self.new_password_edit = QLineEdit()
        self.new_password_edit.setEchoMode(QLineEdit.Password)
        self.new_password_edit.setPlaceholderText('Minimum 6 characters')
        self.confirm_password_edit = QLineEdit()
        self.confirm_password_edit.setEchoMode(QLineEdit.Password)
        self.confirm_password_edit.setPlaceholderText('Confirm new password')

        # Action Buttons
        self.verify_btn = QPushButton('Verify Identity')
        self.verify_btn.setFixedHeight(44)
        self.verify_btn.setStyleSheet(
            'QPushButton { background-color: #1976d2; color: white; border: none; border-radius: 12px; font-weight: bold; }'
            'QPushButton:hover { background-color: #1565c0; }'
        )
        self.verify_btn.clicked.connect(self._on_verify_clicked)

        self.reset_btn = QPushButton('Update Password')
        self.reset_btn.setFixedHeight(44)
        self.reset_btn.setStyleSheet(
            'QPushButton { background-color: #4caf50; color: white; border: none; border-radius: 12px; font-weight: bold; }'
            'QPushButton:hover { background-color: #45a049; }'
        )
        self.reset_btn.clicked.connect(self._on_reset_clicked)
        self.reset_btn.hide()  # Kept invisible until identity checks pass

        cancel_btn = QPushButton('Back')
        cancel_btn.setFixedHeight(44)
        cancel_btn.setStyleSheet(
            'QPushButton { background-color: #b0bec5; color: #1f2937; border: none; border-radius: 12px; font-weight: bold; }'
            'QPushButton:hover { background-color: #9aa7b1; }'
        )
        cancel_btn.clicked.connect(self.reject)

        self.buttons_layout = QHBoxLayout()
        self.buttons_layout.setSpacing(12)
        self.buttons_layout.addWidget(self.verify_btn)
        self.buttons_layout.addWidget(self.reset_btn)
        self.buttons_layout.addWidget(cancel_btn)

        container_layout.addWidget(title_label)
        container_layout.addLayout(self.form_layout)
        container_layout.addLayout(self.buttons_layout)
        container_layout.addStretch(1)

        layout.addStretch(1)
        layout.addWidget(container, 0, Qt.AlignCenter)
        layout.addStretch(1)

    def _on_verify_clicked(self):
        username = self.username_edit.text()
        email = self.email_edit.text()

        if database.verify_admin_email(username, email):
            QMessageBox.information(self, "Identity Verified", "Account verified. Please enter your new password details below.")
            
            # Lock existing fields
            self.username_edit.setEnabled(False)
            self.email_edit.setEnabled(False)
            
            # Append rows into the running layout form instance
            self.form_layout.addRow('New Password:', self.new_password_edit)
            self.form_layout.addRow('Confirm Password:', self.confirm_password_edit)
            
            # Switch buttons visibility
            self.verify_btn.hide()
            self.reset_btn.show()
        else:
            QMessageBox.warning(self, "Verification Failed", "No match found for that username and email combination.")

    def _on_reset_clicked(self):
        username = self.username_edit.text()
        new_pwd = self.new_password_edit.text()
        conf_pwd = self.confirm_password_edit.text()

        if len(new_pwd) < 6:
            QMessageBox.warning(self, "Validation Error", "Password must be at least 6 characters long.")
            return
        if new_pwd != conf_pwd:
            QMessageBox.warning(self, "Validation Error", "Passwords do not match!")
            return

        if database.update_admin_password(username, new_pwd):
            QMessageBox.information(self, "Success", "Password successfully changed!")
            self.accept()
        else:
            QMessageBox.critical(self, "database Error", "Failed to update database records.")


class AdminSignupDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Dialog)
        self.setWindowModality(Qt.ApplicationModal)
        self.setStyleSheet('background-color: black;')
        self.setWindowTitle('Admin Sign Up')
        self._build_ui()

    def _build_ui(self):
        self.setMinimumSize(1000, 600)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        container = QWidget(self)
        container.setStyleSheet(
            'background-color: gray; border-radius: 18px; border: 1px solid #c8ccd4;'
        )
        container_layout = QVBoxLayout(container)
        container_layout.setContentsMargins(24, 24, 24, 24)
        container_layout.setSpacing(16)

        title_label = QLabel('Create Admin Account')
        title_label.setAlignment(Qt.AlignCenter)
        title_label.setStyleSheet('border:none; font-size: 18px; font-weight: bold;')

        self.username_edit = QLineEdit()
        self.username_edit.setPlaceholderText('Choose a unique username')
        
        self.email_edit = QLineEdit()
        self.email_edit.setPlaceholderText('Enter your email address')
        
        self.password_edit = QLineEdit()
        self.password_edit.setEchoMode(QLineEdit.Password)
        self.password_edit.setPlaceholderText('Minimum 6 characters')
        
        self.confirm_password_edit = QLineEdit()
        self.confirm_password_edit.setEchoMode(QLineEdit.Password)
        self.confirm_password_edit.setPlaceholderText('Re-enter password')

        form_layout = QFormLayout()
        form_layout.setLabelAlignment(Qt.AlignRight)
        form_layout.setFormAlignment(Qt.AlignCenter)
        form_layout.addRow('Username:', self.username_edit)
        form_layout.addRow('Email ID:', self.email_edit)
        form_layout.addRow('Password:', self.password_edit)
        form_layout.addRow('Confirm Password:', self.confirm_password_edit)

        signup_btn = QPushButton('Register')
        signup_btn.setFixedHeight(44)
        signup_btn.setStyleSheet(
            'QPushButton { background-color: #1976d2; color: white; border: none; border-radius: 12px; font-weight: bold; }'
            'QPushButton:hover { background-color: #1565c0; }'
        )
        signup_btn.clicked.connect(self._on_register_clicked)

        cancel_btn = QPushButton('Back to Login')
        cancel_btn.setFixedHeight(44)
        cancel_btn.setStyleSheet(
            'QPushButton { background-color: #b0bec5; color: #1f2937; border: none; border-radius: 12px; font-weight: bold; }'
            'QPushButton:hover { background-color: #9aa7b1; }'
        )
        cancel_btn.clicked.connect(self.reject)

        buttons_layout = QHBoxLayout()
        buttons_layout.setSpacing(12)
        buttons_layout.addWidget(signup_btn)
        buttons_layout.addWidget(cancel_btn)

        container_layout.addWidget(title_label)
        container_layout.addLayout(form_layout)
        container_layout.addLayout(buttons_layout)
        container_layout.addStretch(1)

        layout.addStretch(1)
        layout.addWidget(container, 0, Qt.AlignCenter)
        layout.addStretch(1)

    def _on_register_clicked(self):
        username = self.username_edit.text()
        email = self.email_edit.text()
        password = self.password_edit.text()
        confirm_password = self.confirm_password_edit.text()

        if password != confirm_password:
            QMessageBox.warning(self, "Validation Error", "Passwords do not match!")
            return

        success, message = database.register_admin(username, email, password)
        if success:
            # Show a blocking, parented modal message box so the user must
            # acknowledge success. After the user clicks OK, close the
            # signup dialog to return control to the login dialog.
            QMessageBox.information(self, "Success", message, QMessageBox.Ok)
            self.accept()
            return
        else:
            QMessageBox.warning(self, "Registration Failed", message)


class AdminLoginDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Dialog)
        self.setWindowModality(Qt.ApplicationModal)
        self.setStyleSheet('background-color: black;')
        self.setWindowTitle('Admin Login')
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        container = QWidget(self)
        container.setMinimumSize(1000, 600)
        container.setStyleSheet(
            'background-color: #BCEDBB; border-radius: 18px; border: 1px solid #c8ccd4;'
        )

        container_layout = QVBoxLayout(container)
        container_layout.setContentsMargins(24, 24, 24, 24)
        container_layout.setSpacing(16)

        title_label = QLabel('Admin Login')
        title_label.setMinimumHeight(40)
        title_label.setAlignment(Qt.AlignCenter)
        title_label.setStyleSheet('color:orange; border:none; font-size: 48px; font-weight: bold;')

        self.admin_name_label = QLabel("Admin Name: ")
        self.admin_name_label.setMinimumHeight(50)
        self.admin_name_label.setStyleSheet("border:none; color:blue; font-size:18px; font-weight:bold;")
        self.admin_name_edit = QLineEdit()
        self.admin_name_edit.setMinimumHeight(50)
        self.admin_name_edit.setStyleSheet("font-size:18px;font-weight:bold;  background: transparent; color:black; border:none;")
        self.admin_name_edit.setPlaceholderText('Enter admin name')

        self.password_label = QLabel("Password:   ")
        self.password_label.setMinimumHeight(50)
        self.password_label.setStyleSheet("border:none; color:blue; font-size:18px; font-weight:bold;")        
        self.password_edit = QLineEdit()
        self.password_edit.setMinimumHeight(50)
        self.password_edit.setStyleSheet("font-size:18px; font-weight:bold; background: transparent; color:black; border:none;")
        self.password_edit.setEchoMode(QLineEdit.Password)
        self.password_edit.setPlaceholderText('Enter password')

        form_layout = QFormLayout()
        form_layout.setVerticalSpacing(15)
        form_layout.setLabelAlignment(Qt.AlignRight)
        form_layout.setFormAlignment(Qt.AlignCenter)
        form_layout.addRow(self.admin_name_label, self.admin_name_edit)
        form_layout.addRow(self.password_label, self.password_edit)

        # self.setStyleSheet("""
        # QFormLayout QLabel {min-height:50px; font-size: 16px; font-weight:bold; color:blue;}
        # QFormLayout QLineEdit {min-height: 40px; padding:5px; border:none, font-size:16px;}
        #                 """)
        login_button = QPushButton('Login')
        login_button.setFixedHeight(44)
        login_button.setStyleSheet(
            'QPushButton { background-color: #4caf50; color: white; border: none; border-radius: 12px; font-weight: bold; } '
            'QPushButton:hover { background-color: #45a049; }'
        )
        login_button.clicked.connect(self._on_login_clicked)

        cancel_button = QPushButton('Cancel')
        cancel_button.setFixedHeight(44)
        cancel_button.setStyleSheet(
            'QPushButton { background-color: #b0bec5; color: #1f2937; border: none; border-radius: 12px; font-weight: bold; } '
            'QPushButton:hover { background-color: #9aa7b1; }'
        )
        cancel_button.clicked.connect(self.reject)

        buttons_row = QWidget()
        buttons_layout = QHBoxLayout(buttons_row)
        buttons_layout.setContentsMargins(0, 0, 0, 0)
        buttons_layout.setSpacing(12)
        buttons_layout.addWidget(login_button)
        buttons_layout.addWidget(cancel_button)

        # Bottom text options (Signup & Forgot Password links)
        links_layout = QHBoxLayout()
        
        signup_label = QLabel('<a href="#">New admin: Sign up</a>')
        signup_label.setAlignment(Qt.AlignLeft)
        signup_label.setTextFormat(Qt.RichText)
        signup_label.setTextInteractionFlags(Qt.TextBrowserInteraction)
        signup_label.linkActivated.connect(self._on_signup_clicked)
        signup_label.setStyleSheet('color: #1976d2;')
        
        forgot_label = QLabel('<a href="#">Forgot Password?</a>')
        forgot_label.setAlignment(Qt.AlignRight)
        forgot_label.setTextFormat(Qt.RichText)
        forgot_label.setTextInteractionFlags(Qt.TextBrowserInteraction)
        forgot_label.linkActivated.connect(self._on_forgot_clicked)
        forgot_label.setStyleSheet('color: #d32f2f;')

        links_layout.addWidget(signup_label)
        links_layout.addWidget(forgot_label)

        container_layout.addWidget(title_label)
        container_layout.addLayout(form_layout)
        container_layout.addWidget(buttons_row)
        container_layout.addLayout(links_layout)
        container_layout.addStretch(1)

        layout.addStretch(1)
        layout.addWidget(container, 0, Qt.AlignCenter)
        layout.addStretch(1)

    def _on_login_clicked(self):
        username = self.admin_name_edit.text()
        password = self.password_edit.text()

        if database.verify_admin_login(username, password):
            self.accept()
        else:
            QMessageBox.warning(self, "Login Error", "Invalid Admin Name or Password.")

    def _on_signup_clicked(self, link: str):
        self.hide()
        signup_dialog = AdminSignupDialog(self.parentWidget())
        signup_dialog.exec()
        self.show()

    def _on_forgot_clicked(self, link: str):
        self.hide()
        forgot_dialog = ForgotPasswordDialog(self.parentWidget())
        forgot_dialog.exec()
        self.show()


if __name__ == '__main__':
    app = QApplication(sys.argv)
    
    # SPECIAL DEMAND IMPLEMENTATION:
    # 1. Initialize and show MainWindow immediately in the background
    window = MainWindow()
    window.candidate_record_btn.clicked.connect(lambda: window.open_admin(0))
    window.scan_btn.clicked.connect(window.open_scanner)
    window.showMaximized()

    # 2. Launch modal login prompt directly over top of MainWindow
    login_dialog = AdminLoginDialog(window)
    
    # 3. If cancel is chosen or dialog gets closed, terminate both windows gracefully
    if login_dialog.exec() != QDialog.Accepted:
        window.close()
        sys.exit(0)
    else:
        # Save logged-in admin username on the main window so other UI can reference it
        try:
            username = login_dialog.admin_name_edit.text()
            window.current_admin_username = username
            # fetch email
            admin_row = database.get_admin(username)
            if admin_row:
                _, email = admin_row
                window.current_admin_email = email
            else:
                window.current_admin_email = ''
        except Exception:
            window.current_admin_username = None
            window.current_admin_email = None

    sys.exit(app.exec())