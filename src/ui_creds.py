"""Login/password dialog shown when a camera rejects the default credentials."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QHBoxLayout, QLabel, QLineEdit, QPushButton, QVBoxLayout,
)


class CredentialsDialog(QDialog):
    def __init__(self, parent=None, ip: str = "", user: str = "admin",
                 error: str = ""):
        super().__init__(parent)
        self.setWindowTitle("Camera login")
        self.setMinimumWidth(460)

        v = QVBoxLayout(self)
        v.setContentsMargins(16, 14, 16, 12)
        v.setSpacing(10)

        title = QLabel(f"Login required: {ip}")
        f = title.font()
        f.setPointSize(11)
        f.setBold(True)
        title.setFont(f)
        v.addWidget(title)

        msg = QLabel(error or "The default login was not accepted by this camera.")
        msg.setWordWrap(True)
        v.addWidget(msg)

        hint = QLabel("Defaults: SRG-X400  admin / admin123    BRC-AM7  admin / Admin123")
        hint.setStyleSheet("color:#8b9198; font-size:11px;")
        hint.setWordWrap(True)
        v.addWidget(hint)

        row1 = QHBoxLayout()
        row1.setSpacing(8)
        lb1 = QLabel("Login:")
        lb1.setFixedWidth(70)
        row1.addWidget(lb1)
        self.e_user = QLineEdit(user)
        row1.addWidget(self.e_user, 1)
        v.addLayout(row1)

        row2 = QHBoxLayout()
        row2.setSpacing(8)
        lb2 = QLabel("Password:")
        lb2.setFixedWidth(70)
        row2.addWidget(lb2)
        self.e_pass = QLineEdit()
        self.e_pass.setEchoMode(QLineEdit.Password)
        row2.addWidget(self.e_pass, 1)
        v.addLayout(row2)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        b_skip = QPushButton("Skip")
        b_skip.clicked.connect(self.reject)
        buttons.addWidget(b_skip)
        b_ok = QPushButton("Connect")
        b_ok.setDefault(True)
        b_ok.clicked.connect(self.accept)
        buttons.addWidget(b_ok)
        v.addLayout(buttons)

        self.e_pass.returnPressed.connect(self.accept)
        self.e_pass.setFocus(Qt.OtherFocusReason)

    def values(self) -> tuple[str, str]:
        return self.e_user.text().strip(), self.e_pass.text()
