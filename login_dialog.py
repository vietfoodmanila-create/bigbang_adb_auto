# login_dialog.py
from PySide6.QtWidgets import QDialog, QVBoxLayout, QLineEdit, QPushButton, QLabel, QHBoxLayout, QMessageBox
from cloud import Cloud
from register_dialog import RegisterDialog

class LoginDialog(QDialog):
    def __init__(self, cloud: Cloud, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Đăng nhập")
        self.cloud = cloud

        self.email = QLineEdit(); self.email.setPlaceholderText("Email")
        self.password = QLineEdit(); self.password.setEchoMode(QLineEdit.Password); self.password.setPlaceholderText("Mật khẩu")
        self.license = QLineEdit(); self.license.setPlaceholderText("License key")
        self.btnLogin = QPushButton("Đăng nhập")
        self.btnReg   = QPushButton("Đăng ký")
        h = QHBoxLayout(); h.addWidget(self.btnLogin); h.addWidget(self.btnReg)

        lay = QVBoxLayout(self)
        for w in (self.email, self.password, self.license):
            lay.addWidget(w)
        lay.addLayout(h)

        self.btnLogin.clicked.connect(self._login)
        self.btnReg.clicked.connect(self._open_register)

    def _open_register(self):
        dlg = RegisterDialog(self.cloud, self)
        dlg.exec()

    def _login(self):
        try:
            token = self.cloud.login(self.email.text().strip(), self.password.text())
            # kích hoạt license lần đầu
            from cloud import make_device_uid
            self.cloud.license_activate(self.license.text().strip(), make_device_uid())
            self.accept()
        except Exception as e:
            QMessageBox.critical(self, "Đăng nhập thất bại", str(e))
