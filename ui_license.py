# -*- coding: utf-8 -*-
from __future__ import annotations
from PySide6 import QtCore, QtGui, QtWidgets
import requests

# dùng lại CloudClient + stable_device_uid từ ui_auth.py
from ui_auth import CloudClient, stable_device_uid, TokenData, AuthDialog

class ClickLabel(QtWidgets.QLabel):
    clicked = QtCore.Signal()
    def mousePressEvent(self, e: QtGui.QMouseEvent) -> None:
        if e.button() == QtCore.Qt.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(e)


# File: ui_license.py

class ActivateLicenseDialog(QtWidgets.QDialog):
    """Form hiển thị danh sách license và cho phép kích hoạt."""

    def __init__(self, cloud: CloudClient, parent=None):
        super().__init__(parent)
        self.cloud = cloud
        self.setWindowTitle("Kích hoạt License — BBTK Auto")
        self.setMinimumWidth(600)
        self._build()
        self._load_user_licenses()

    def _build(self):
        self.layout = QtWidgets.QVBoxLayout(self)

        # Phần hiển thị danh sách license
        group1 = QtWidgets.QGroupBox("License của bạn")
        v1 = QtWidgets.QVBoxLayout(group1)
        self.license_list_widget = QtWidgets.QWidget()
        self.license_list_layout = QtWidgets.QVBoxLayout(self.license_list_widget)
        self.license_list_layout.setContentsMargins(0, 0, 0, 0)
        v1.addWidget(self.license_list_widget)

        # Phần nhập key thủ công (vẫn giữ lại)
        group2 = QtWidgets.QGroupBox("Nhập mã license khác (nếu có)")
        f2 = QtWidgets.QFormLayout(group2)
        self.leKey = QtWidgets.QLineEdit()
        self.leKey.setPlaceholderText("Nhập mã license...")
        self.btnActivateManual = QtWidgets.QPushButton("Kích hoạt mã này")
        self.btnActivateManual.clicked.connect(self.on_activate_manual)
        f2.addRow("Mã license:", self.leKey)
        f2.addRow(self.btnActivateManual)

        # Phần thông tin thanh toán
        group3 = QtWidgets.QGroupBox("Mua license")
        self.payment_info_layout = QtWidgets.QVBoxLayout(group3)
        self.lblZalo = QtWidgets.QLabel("Đang tải...")
        self.lblBank = QtWidgets.QLabel("")
        self.payment_info_layout.addWidget(self.lblZalo)
        self.payment_info_layout.addWidget(self.lblBank)

        self.layout.addWidget(group1)
        self.layout.addWidget(group2)
        self.layout.addWidget(group3)

        self._load_support_info()  # Tải thông tin Zalo/Bank

    def _load_user_licenses(self):
        try:
            # Xóa các license cũ trước khi tải lại
            for i in reversed(range(self.license_list_layout.count())):
                self.license_list_layout.itemAt(i).widget().setParent(None)

            licenses = self.cloud.list_licenses()  # Gọi API mới
            if not licenses:
                self.license_list_layout.addWidget(QtWidgets.QLabel("Bạn chưa sở hữu license nào."))
                return

            for lic in licenses:
                line = QtWidgets.QHBoxLayout()
                key_short = f"{lic['license_key'][:8]}...{lic['license_key'][-4:]}"
                info_text = (f"<b>{key_short}</b> (Gói: {lic['plan']}) - "
                             f"Hết hạn: {lic['expires_at'].split(' ')[0]} - "
                             f"Thiết bị: {lic['active_devices']}/{lic['max_devices']}")

                label = QtWidgets.QLabel(info_text)
                btn = QtWidgets.QPushButton("Kích hoạt")

                if lic['active_devices'] >= lic['max_devices']:
                    btn.setEnabled(False)
                    btn.setText("Đã đủ thiết bị")

                # Dùng lambda để truyền key vào hàm xử lý
                btn.clicked.connect(lambda checked=False, key=lic['license_key']: self.on_activate_from_list(key))

                line.addWidget(label)
                line.addStretch()
                line.addWidget(btn)
                self.license_list_layout.addLayout(line)

        except Exception as e:
            self.license_list_layout.addWidget(QtWidgets.QLabel(f"Lỗi tải danh sách license: {e}"))

    def on_activate_from_list(self, key):
        self.activate_key(key)

    def on_activate_manual(self):
        key = self.leKey.text().strip()
        if not key:
            QtWidgets.QMessageBox.warning(self, "Lỗi", "Vui lòng nhập mã license.")
            return
        self.activate_key(key)

    def activate_key(self, key):
        try:
            self.cloud.license_activate(key, stable_device_uid(), "MyPC")
            QtWidgets.QMessageBox.information(self, "Thành công", "Kích hoạt license thành công!")
            self.accept()  # Đóng dialog và báo hiệu thành công
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Lỗi", f"Kích hoạt thất bại: {e}")

    def _load_support_info(self):
        # Hàm này giữ nguyên, nhưng sẽ hoạt động sau khi sửa server
        try:
            info = self.cloud.payment_info()
            zalo = info.get("zalo", {})
            bank = info.get("bank", {})
            self.lblZalo.setText(
                f"<b>Zalo:</b> {zalo.get('number', 'N/A')} - <a href='{zalo.get('link', '#')}'>Chat ngay</a>")
            self.lblBank.setText(
                f"<b>Ngân hàng:</b> {bank.get('name', 'N/A')} - {bank.get('account', 'N/A')} ({bank.get('holder', 'N/A')})")
        except Exception as e:
            self.lblZalo.setText(f"Lỗi tải thông tin hỗ trợ: {e}")

class AccountBanner(QtWidgets.QWidget):
    """Thanh trên cùng: email; trạng thái license; nút kích hoạt/gia hạn; menu tài khoản."""
    def __init__(self, cloud: CloudClient, parent=None):
        super().__init__(parent)
        self.cloud = cloud
        self._build()

    def _handle_action_button(self):
        # Kiểm tra trạng thái đăng nhập để quyết định hành động
        if not self.cloud.load_token():
            # Nếu chưa đăng nhập -> mở dialog đăng nhập
            dlg = AuthDialog(self)
            if dlg.exec() == QtWidgets.QDialog.Accepted:
                self.cloud = dlg.cloud
                self.parent().refresh_license()  # Sau khi đăng nhập thành công, refresh lại
        else:
            # Nếu đã đăng nhập (nhưng license chưa có) -> mở dialog kích hoạt
            self._activate_dialog()

    def _build(self):
        self.setObjectName("accountBanner")
        lay = QtWidgets.QHBoxLayout(self)
        lay.setContentsMargins(8, 6, 8, 6)

        self.lblEmail = ClickLabel("…")
        font = self.lblEmail.font();
        font.setBold(True);
        self.lblEmail.setFont(font)
        # BỎ DÒNG NÀY: self.lblEmail.setCursor(QtCore.Qt.PointingHandCursor)

        self.lblStatus = QtWidgets.QLabel("…")
        self.btnAction = QtWidgets.QPushButton("Kích hoạt auto ngay")
        self.btnAction.setCursor(QtCore.Qt.PointingHandCursor)

        lay.addWidget(self.lblEmail)
        lay.addSpacing(10)
        lay.addWidget(self.lblStatus, 1, QtCore.Qt.AlignLeft)
        lay.addStretch()
        lay.addWidget(self.btnAction)

        # menu tài khoản
        self.menu = QtWidgets.QMenu(self)
        actChange = self.menu.addAction("Đổi mật khẩu")
        actLogout = self.menu.addAction("Đăng xuất")

        # CHỈ KẾT NỐI SỰ KIỆN KHI ĐĂNG NHẬP
        # BỎ DÒNG NÀY: self.lblEmail.clicked.connect(self._open_menu)

        actChange.triggered.connect(self._change_pw)
        actLogout.triggered.connect(self._logout)

        self.btnAction.clicked.connect(self._activate_dialog)  # Sẽ sửa lại ở bước sau

        self.setStyleSheet("""...""")  # Giữ nguyên

    def set_status(self, text: str, action_text: str | None):
        self.lblStatus.setText(text)
        if action_text:
            self.btnAction.setText(action_text)
            self.btnAction.show()
        else:
            self.btnAction.hide()
    def _build(self):
        self.setObjectName("accountBanner")
        lay = QtWidgets.QHBoxLayout(self)
        lay.setContentsMargins(8, 6, 8, 6)

        self.lblEmail = ClickLabel("…")
        font = self.lblEmail.font(); font.setBold(True); self.lblEmail.setFont(font)
        self.lblEmail.setCursor(QtCore.Qt.PointingHandCursor)

        self.lblStatus = QtWidgets.QLabel("…")

        self.btnAction = QtWidgets.QPushButton("Kích hoạt auto ngay")
        self.btnAction.setCursor(QtCore.Qt.PointingHandCursor)

        lay.addWidget(self.lblEmail)
        lay.addSpacing(10)
        lay.addWidget(self.lblStatus, 1, QtCore.Qt.AlignLeft)
        lay.addStretch()
        lay.addWidget(self.btnAction)

        # menu tài khoản
        self.menu = QtWidgets.QMenu(self)
        actChange = self.menu.addAction("Đổi mật khẩu")
        actLogout = self.menu.addAction("Đăng xuất")
        self.lblEmail.clicked.connect(self._open_menu)

        actChange.triggered.connect(self._change_pw)
        actLogout.triggered.connect(self._logout)

        self.btnAction.clicked.connect(self._activate_dialog)

        self.setStyleSheet("""
        #accountBanner { background:#f5f5f7; border-bottom:1px solid #ddd; }
        """)

    def set_email(self, email: str):
        if email:
            self.lblEmail.setText(email)
            self.lblEmail.setCursor(QtCore.Qt.PointingHandCursor)
            # Chỉ kết nối sự kiện click để mở menu khi có email (đã đăng nhập)
            try:
                self.lblEmail.clicked.disconnect()
            except RuntimeError:
                pass  # Bỏ qua lỗi nếu chưa được kết nối, đây là cách xử lý đúng
            self.lblEmail.clicked.connect(self._open_menu)
        else:
            self.lblEmail.setText("(chưa đăng nhập)")
            self.lblEmail.setCursor(QtCore.Qt.ArrowCursor)  # Trả về con trỏ mặc định
            # Ngắt kết nối sự kiện click (nếu có)
            try:
                self.lblEmail.clicked.disconnect()
            except RuntimeError:
                # Bỏ qua lỗi/cảnh báo nếu nó chưa được kết nối.
                # Đây là cách xử lý an toàn và được khuyến khích.
                pass

    def set_status(self, text: str, action_text: str | None):
        self.lblStatus.setText(text)
        if action_text:
            self.btnAction.setText(action_text)
            self.btnAction.setEnabled(True)
            self.btnAction.show()
        else:
            self.btnAction.hide()

    def _open_menu(self):
        self.menu.exec(self.mapToGlobal(QtCore.QPoint(0, self.height())))

    def _change_pw(self):
        # TODO: cần backend /api/account/change_password
        QtWidgets.QMessageBox.information(self, "Đổi mật khẩu",
            "Tính năng đổi mật khẩu sẽ khả dụng khi server có endpoint phù hợp.")

    # File: ui_license.py, class AccountBanner
    def _logout(self):
        # 1. Xóa token và thông tin session
        self.cloud.logout()

        # 2. Thông báo cho người dùng
        QtWidgets.QMessageBox.information(self, "Đăng xuất", "Bạn đã đăng xuất thành công.")

        # 3. Yêu cầu UI chính cập nhật ngay lập tức
        par = self.parent()
        if hasattr(par, "refresh_license"):
            # Lệnh refresh này sẽ cập nhật banner và khóa các tính năng
            par.refresh_license()
    def _activate_dialog(self):
        dlg = ActivateLicenseDialog(self.cloud, self)
        if dlg.exec() == QtWidgets.QDialog.Accepted:
            # controller bên ngoài sẽ gọi refresh
            self.parent().refresh_license()  # parent sẽ là LicenseController._container

class _Container(QtWidgets.QWidget):
    """Bọc centralWidget: Banner ở trên + nội dung bên dưới."""
    def __init__(self, banner: AccountBanner, content: QtWidgets.QWidget):
        super().__init__()
        v = QtWidgets.QVBoxLayout(self)
        v.setContentsMargins(0,0,0,0); v.setSpacing(0)
        v.addWidget(banner)
        v.addWidget(content, 1)
        self.banner = banner
        self.content = content

class LicenseController(QtCore.QObject):
    """Quản lý bật/tắt UI theo license và cập nhật banner."""
    def __init__(self, cloud: CloudClient, main_window: QtWidgets.QMainWindow,
                 protected_root: QtWidgets.QWidget):
        super().__init__(main_window)
        self.cloud = cloud
        self.main = main_window
        self.protected_root = protected_root

        self.banner = AccountBanner(cloud, main_window)
        # wrap central widget
        self.container = _Container(self.banner, protected_root)

        # thay centralWidget bằng container
        if isinstance(main_window, QtWidgets.QMainWindow):
            main_window.setCentralWidget(self.container)

        # lộ “API” nhỏ cho banner gọi refresh()
        self.container.refresh_license = self.refresh

        # hiển thị email hiện có
        td = self.cloud.load_token()
        self.banner.set_email(td.email if td else "")

        self.refresh()

    def set_enabled_by_license(self, enabled: bool):
        self.protected_root.setEnabled(enabled)

    # File: ui_license.py, class LicenseController
    def _handle_action_click(self):
        # Kiểm tra token để quyết định hành động
        if not self.cloud.load_token():
            # CHƯA ĐĂNG NHẬP -> Mở AuthDialog
            dlg = AuthDialog(self.main)
            if dlg.exec() == QtWidgets.QDialog.Accepted:
                self.cloud = dlg.cloud
                self.refresh()  # Tải lại trạng thái sau khi đăng nhập thành công
        else:
            # ĐÃ ĐĂNG NHẬP -> Mở ActivateLicenseDialog
            dlg_activate = ActivateLicenseDialog(self.cloud, self.main)
            if dlg_activate.exec() == QtWidgets.QDialog.Accepted:
                self.refresh()  # Tải lại trạng thái sau khi kích hoạt

    def refresh(self):
        try:
            st = self.cloud.license_status()
        except Exception as e:
            self.banner.set_status(f"Lỗi mạng: {e}", "Đăng nhập")
            self.set_enabled_by_license(False)
            # Kết nối lại nút action để thử đăng nhập
            try:
                self.banner.btnAction.clicked.disconnect()
            except RuntimeError:
                pass
            self.banner.btnAction.clicked.connect(self._handle_action_click)
            return

        td = self.cloud.load_token()
        self.banner.set_email(td.email if td else None)

        is_logged_in = st.get("logged_in")
        is_license_valid = bool(st.get("valid"))

        # Ngắt kết nối cũ của nút action để gắn lại chức năng mới
        try:
            self.banner.btnAction.clicked.disconnect()
        except RuntimeError:
            pass  # Bỏ qua lỗi nếu chưa được kết nối

        if is_logged_in and is_license_valid:
            days = st.get("days_left")
            plan = st.get("plan") or ""
            txt = f"Đã kích hoạt ({plan}) — còn {days} ngày"
            self.banner.set_status(txt, None)  # Ẩn nút
            self.set_enabled_by_license(True)
        elif is_logged_in and not is_license_valid:
            self.banner.set_status("Chưa kích hoạt license", "Kích hoạt ngay")
            self.banner.btnAction.clicked.connect(self._handle_action_click)
            self.set_enabled_by_license(False)
        else:  # Không đăng nhập
            self.banner.set_status("Bạn chưa đăng nhập", "Đăng nhập")
            self.banner.btnAction.clicked.connect(self._handle_action_click)
            self.set_enabled_by_license(False)

def attach_license_banner(main_window: QtWidgets.QMainWindow,
                          protected_root: QtWidgets.QWidget,
                          cloud: CloudClient) -> LicenseController:
    """
    Gắn banner + cơ chế khóa/mở UI theo license.
    - main_window: QMainWindow hiện tại
    - protected_root: widget chứa toàn bộ phần tính năng (centralWidget hiện tại)
    - cloud: CloudClient đã có token
    Trả về LicenseController để bạn có thể gọi .refresh() khi cần.
    """
    return LicenseController(cloud, main_window, protected_root)
