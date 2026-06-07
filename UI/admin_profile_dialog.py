from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QMessageBox
)

try:
    from .database import get_connection, update_admin_password, get_admin
except Exception:
    from database import get_connection, update_admin_password, get_admin


class AdminProfileDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle('Admin Profile')
        self.setMinimumWidth(420)
        self._build_ui()
        self._load_current_admin()

    def _build_ui(self):
        layout = QVBoxLayout(self)

        header = QLabel('Admin Profile')
        header.setStyleSheet('font-weight: 700; font-size: 16px;')
        layout.addWidget(header)

        row = QHBoxLayout()
        row.addWidget(QLabel('Admin:'))
        self.admin_label = QLabel('-')
        row.addWidget(self.admin_label)
        layout.addLayout(row)

        self.email_label = QLabel('Email: -')
        layout.addWidget(self.email_label)

        layout.addWidget(QLabel('Change password:'))
        self.new_pw = QLineEdit()
        self.new_pw.setEchoMode(QLineEdit.Password)
        self.new_pw.setPlaceholderText('New password')
        layout.addWidget(self.new_pw)

        self.confirm_pw = QLineEdit()
        self.confirm_pw.setEchoMode(QLineEdit.Password)
        self.confirm_pw.setPlaceholderText('Confirm new password')
        layout.addWidget(self.confirm_pw)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        change_btn = QPushButton('Change Password')
        change_btn.clicked.connect(self._change_password)
        btn_row.addWidget(change_btn)
        close_btn = QPushButton('Close')
        close_btn.clicked.connect(self.accept)
        btn_row.addWidget(close_btn)
        layout.addLayout(btn_row)
        # admin loading is handled in _load_current_admin()

    def _load_admins(self):
        try:
            conn = get_connection()
            cur = conn.cursor()
            cur.execute('SELECT username, email FROM admins')
            rows = cur.fetchall()
            conn.close()
        except Exception:
            rows = []

        self.admins = rows
        self.admin_combo.clear()
        for username, email in rows:
            self.admin_combo.addItem(username, (username, email))

        if rows:
            self._on_admin_changed(0)

    def _load_current_admin(self):
        # Determine the logged-in admin from parent window if available
        username = None
        parent = self.parent()
        if parent is not None and hasattr(parent, 'current_admin_username'):
            username = getattr(parent, 'current_admin_username')

        if not username:
            # fallback: pick first admin from DB
            try:
                conn = get_connection()
                cur = conn.cursor()
                cur.execute('SELECT username, email FROM admins LIMIT 1')
                row = cur.fetchone()
                conn.close()
                if row:
                    username = row[0]
            except Exception:
                username = None

        if not username:
            self.admin_label.setText('-')
            self.email_label.setText('Email: -')
            return

        self.admin_label.setText(username)
        try:
            admin = get_admin(username)
            if admin:
                _, email = admin
                self.email_label.setText(f'Email: {email}')
            else:
                self.email_label.setText('Email: -')
        except Exception:
            self.email_label.setText('Email: -')

    def _on_admin_changed(self, index):
        data = self.admin_combo.itemData(index)
        if data:
            username, email = data
            self.email_label.setText(f'Email: {email}')
        else:
            self.email_label.setText('Email: -')

    def _change_password(self):
        # Operate on the currently shown admin (the logged-in user)
        username = self.admin_label.text()
        if not username or username == '-':
            QMessageBox.warning(self, 'No Admin', 'No admin selected.')
            return
        pw = self.new_pw.text()
        pw2 = self.confirm_pw.text()
        if not pw or not pw2:
            QMessageBox.warning(self, 'Invalid', 'Please enter and confirm a new password.')
            return
        if pw != pw2:
            QMessageBox.warning(self, 'Mismatch', 'Passwords do not match.')
            return
        if len(pw) < 6:
            QMessageBox.warning(self, 'Weak Password', 'Password must be at least 6 characters.')
            return
        try:
            success = update_admin_password(username, pw)
            if success:
                QMessageBox.information(self, 'Success', 'Password updated successfully.')
                self.new_pw.clear()
                self.confirm_pw.clear()
            else:
                QMessageBox.critical(self, 'Failure', 'Unable to update password.')
        except Exception as exc:
            QMessageBox.critical(self, 'Error', f'Error updating password: {exc}')
