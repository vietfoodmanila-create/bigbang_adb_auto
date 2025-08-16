# register_dialog.py
from PySide6.QtWidgets import QDialog, QVBoxLayout, QLineEdit, QPushButton, QLabel, QMessageBox, QHBoxLayout
from PySide6.QtCore import QTimer
from cloud import Cloud

class RegisterDialog(QDialog):
    def __init__(self, cloud: Cloud, parent=None):
        super().__init__(parent)
        self.refresh_auth_and_license()
        self.setWindowTitle("Đăng ký tài khoản")
        self.cloud = cloud
        self.cooldown = 0
        self.sends_today = 0

        self.email = QLineEdit(); self.email.setPlaceholderText("Email")
        self.pass1 = QLineEdit(); self.pass1.setEchoMode(QLineEdit.Password); self.pass1.setPlaceholderText("Mật khẩu (>=8)")
        self.pass2 = QLineEdit(); self.pass2.setEchoMode(QLineEdit.Password); self.pass2.setPlaceholderText("Nhập lại mật khẩu")
        self.code  = QLineEdit(); self.code.setPlaceholderText("Mã OTP (4 số)")
        self.lbl   = QLabel("")

        self.btnSend   = QPushButton("Gửi mã")
        self.btnResend = QPushButton("Gửi lại (60s)")
        self.btnResend.setEnabled(False)
        self.btnVerify = QPushButton("Xác minh & tạo tài khoản")

        lay = QVBoxLayout(self)
        for w in (self.email, self.pass1, self.pass2, self.code):
            lay.addWidget(w)
        h = QHBoxLayout(); h.addWidget(self.btnSend); h.addWidget(self.btnResend)
        lay.addLayout(h); lay.addWidget(self.btnVerify); lay.addWidget(self.lbl)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)

        self.btnSend.clicked.connect(self._send)
        self.btnResend.clicked.connect(self._resend)
        self.btnVerify.clicked.connect(self._verify)

    def _tick(self):
        if self.cooldown > 0:
            self.cooldown -= 1
            self.btnResend.setText(f"Gửi lại ({self.cooldown}s)")
            self.btnResend.setEnabled(False)
        else:
            self.timer.stop()
            self.btnResend.setText("Gửi lại")
            self.btnResend.setEnabled(self.sends_today < 3)

    def _start_cooldown(self, sec=60):
        self.cooldown = sec
        self.sends_today += 1
        self.btnResend.setEnabled(False)
        self.timer.start(1000)
        self._tick()

    def _send(self):
        if self.pass1.text() != self.pass2.text():
            QMessageBox.warning(self, "Lỗi", "Mật khẩu nhập lại không khớp.")
            return
        try:
            r = self.cloud.register_start(self.email.text().strip(), self.pass1.text())
            if not r.get("ok"):
                raise RuntimeError(r)
            self._start_cooldown(r.get("retry_after", 60))
            self.lbl.setText(f"Đã gửi mã OTP. Còn {r.get('remaining_today', 'n/a')} lần hôm nay.")
        except Exception as e:
            QMessageBox.critical(self, "Lỗi", str(e))

    def _resend(self):
        try:
            r = self.cloud.register_resend(self.email.text().strip())
            if not r.get("ok"):
                raise RuntimeError(r)
            self._start_cooldown(r.get("retry_after", 60))
            self.lbl.setText(f"Đã gửi lại OTP. Còn {r.get('remaining_today', 'n/a')} lần hôm nay.")
        except Exception as e:
            QMessageBox.critical(self, "Lỗi", str(e))

    def _verify(self):
        try:
            r = self.cloud.register_verify(self.email.text().strip(), self.code.text().strip())
            if not r.get("ok"):
                raise RuntimeError(r)
            QMessageBox.information(self, "Thành công", "Tài khoản đã xác minh. Bạn có thể đăng nhập.")
            self.accept()
        except Exception as e:
            QMessageBox.critical(self, "Lỗi", str(e))
