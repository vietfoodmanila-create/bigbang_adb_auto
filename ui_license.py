# ui_license.py - Phiên bản nâng cấp hoàn chỉnh

from __future__ import annotations
from PySide6 import QtCore, QtGui, QtWidgets
import requests

# Dùng lại CloudClient và các hàm tiện ích từ ui_auth
from ui_auth import CloudClient, stable_device_uid, TokenData, AuthDialog, ChangePasswordDialog


class ClickLabel(QtWidgets.QLabel):
    clicked = QtCore.Signal()

    def mousePressEvent(self, e: QtGui.QMouseEvent) -> None:
        if e.button() == QtCore.Qt.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(e)


class LicenseManagerDialog(QtWidgets.QDialog):
    """
    Hộp thoại quản lý license toàn diện:
    - Hiển thị trạng thái license hiện tại.
    - Cho phép gia hạn bằng key mới.
    - Hiển thị thông tin mua license (Zalo, Bank) kèm QR Code.
    """

    def __init__(self, cloud: CloudClient, parent=None):
        super().__init__(parent)
        self.cloud = cloud
        self.setWindowTitle("Quản lý License — BBTK Auto")
        self.setMinimumWidth(650)
        self.setMinimumHeight(500)
        self._build()
        self.refresh_all_info()

    def _build(self):
        self.layout = QtWidgets.QVBoxLayout(self)
        self.tabs = QtWidgets.QTabWidget()

        # Tab 1: Trạng thái và Gia hạn
        tab_status = QtWidgets.QWidget()
        layout_status = QtWidgets.QVBoxLayout(tab_status)

        group_current = QtWidgets.QGroupBox("Trạng thái License hiện tại")
        form_current = QtWidgets.QFormLayout(group_current)
        self.lbl_status = QtWidgets.QLabel("Đang tải...")
        self.lbl_plan = QtWidgets.QLabel("...")
        self.lbl_expires = QtWidgets.QLabel("...")
        self.lbl_days_left = QtWidgets.QLabel("...")
        form_current.addRow("Trạng thái:", self.lbl_status)
        form_current.addRow("Gói:", self.lbl_plan)
        form_current.addRow("Ngày hết hạn:", self.lbl_expires)
        form_current.addRow("Số ngày còn lại:", self.lbl_days_left)

        group_renew = QtWidgets.QGroupBox("Nhập mã license mới để gia hạn / kích hoạt")
        form_renew = QtWidgets.QFormLayout(group_renew)
        self.le_key_renew = QtWidgets.QLineEdit()
        self.le_key_renew.setPlaceholderText("Nhập mã license mới...")
        self.btn_renew = QtWidgets.QPushButton("Gia hạn / Kích hoạt")
        self.btn_renew.clicked.connect(self.on_activate_renew)
        form_renew.addRow("Mã license:", self.le_key_renew)
        form_renew.addRow(self.btn_renew)

        layout_status.addWidget(group_current)
        layout_status.addWidget(group_renew)
        layout_status.addStretch()

        # Tab 2: Mua License
        tab_buy = QtWidgets.QWidget()
        layout_buy = QtWidgets.QVBoxLayout(tab_buy)

        group_payment = QtWidgets.QGroupBox("Thông tin mua License")
        grid_payment = QtWidgets.QGridLayout(group_payment)

        self.lbl_zalo_info = QtWidgets.QLabel("Đang tải...")
        self.lbl_zalo_qr = QtWidgets.QLabel()
        self.lbl_zalo_qr.setFixedSize(150, 150)
        self.lbl_zalo_qr.setScaledContents(True)
        self.lbl_zalo_qr.setStyleSheet("border: 1px solid #ccc; background-color: #f0f0f0;")

        self.lbl_bank_info = QtWidgets.QLabel("...")
        self.lbl_bank_qr = QtWidgets.QLabel()
        self.lbl_bank_qr.setFixedSize(150, 150)
        self.lbl_bank_qr.setScaledContents(True)
        self.lbl_bank_qr.setStyleSheet("border: 1px solid #ccc; background-color: #f0f0f0;")

        grid_payment.addWidget(QtWidgets.QLabel("<b>Zalo:</b>"), 0, 0, QtCore.Qt.AlignTop)
        grid_payment.addWidget(self.lbl_zalo_info, 0, 1)
        grid_payment.addWidget(self.lbl_zalo_qr, 0, 2)
        grid_payment.addWidget(QtWidgets.QLabel("<b>Ngân hàng:</b>"), 1, 0, QtCore.Qt.AlignTop)
        grid_payment.addWidget(self.lbl_bank_info, 1, 1)
        grid_payment.addWidget(self.lbl_bank_qr, 1, 2)
        grid_payment.setColumnStretch(1, 1)

        layout_buy.addWidget(group_payment)
        layout_buy.addStretch()

        self.tabs.addTab(tab_status, "Trạng thái & Gia hạn")
        self.tabs.addTab(tab_buy, "Mua License")
        self.layout.addWidget(self.tabs)

    def refresh_all_info(self):
        self.load_license_status()
        self.load_payment_info()

    def load_license_status(self):
        try:
            st = self.cloud.license_status()
            if st.get("valid"):
                self.lbl_status.setText("<b style='color: green;'>ĐÃ KÍCH HOẠT</b>")
                self.lbl_plan.setText(st.get("plan", "..."))
                self.lbl_expires.setText(st.get("expires_at", "..."))
                self.lbl_days_left.setText(str(st.get("days_left", "...")))
            else:
                reason = st.get("reason", "")
                if reason == 'no_license_owned':
                    status_text = "BẠN CHƯA SỞ HỮU LICENSE"
                else:
                    status_text = "CHƯA KÍCH HOẠT TRÊN THIẾT BỊ NÀY"
                self.lbl_status.setText(f"<b style='color: red;'>{status_text}</b>")
                self.lbl_plan.setText("N/A")
                self.lbl_expires.setText("N/A")
                self.lbl_days_left.setText("N/A")
        except Exception as e:
            self.lbl_status.setText(f"<b style='color: red;'>Lỗi: {e}</b>")

    def on_activate_renew(self):
        key = self.le_key_renew.text().strip()
        if not key:
            QtWidgets.QMessageBox.warning(self, "Lỗi", "Vui lòng nhập mã license mới.")
            return
        try:
            # Luôn dùng device_uid của máy hiện tại
            self.cloud.license_activate(key, stable_device_uid(), "MyPC")
            QtWidgets.QMessageBox.information(self, "Thành công", "Gia hạn / Kích hoạt thành công!")
            self.load_license_status()
            self.le_key_renew.clear()
            self.parent()._license_controller.refresh()  # Yêu cầu banner chính refresh
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Lỗi", f"Thao tác thất bại: {e}")

    def load_payment_info(self):
        try:
            info = self.cloud.payment_info().get('data', {})
            zalo = info.get("zalo", {})
            bank = info.get("bank", {})

            zalo_html = f"Số điện thoại: {zalo.get('number', 'N/A')}<br>"
            zalo_html += f"Link: <a href='{zalo.get('link', '#')}'>Chat ngay</a>"
            self.lbl_zalo_info.setText(zalo_html)

            bank_html = f"Ngân hàng: {bank.get('name', 'N/A')}<br>"
            bank_html += f"Số tài khoản: {bank.get('account', 'N/A')}<br>"
            bank_html += f"Chủ tài khoản: {bank.get('holder', 'N/A')}"
            self.lbl_bank_info.setText(bank_html)

            self.download_image(zalo.get('qr_url'), self.lbl_zalo_qr)
            self.download_image(bank.get('qr_url'), self.lbl_bank_qr)

        except Exception as e:
            self.lbl_zalo_info.setText(f"Lỗi tải thông tin: {e}")

    def download_image(self, url, label_widget):
        if not url:
            label_widget.setText("Không có ảnh QR")
            return
        # Chạy việc tải ảnh trong một thread riêng để không làm treo UI
        thread = DownloadThread(url, self)
        thread.finished.connect(
            lambda pixmap: label_widget.setPixmap(pixmap) if pixmap else label_widget.setText("Lỗi tải ảnh"))
        thread.start()


class DownloadThread(QtCore.QThread):
    finished = QtCore.Signal(QtGui.QPixmap)

    def __init__(self, url, parent=None):
        super().__init__(parent)
        self.url = url

    def run(self):
        try:
            response = requests.get(self.url, timeout=10)
            response.raise_for_status()
            pixmap = QtGui.QPixmap()
            pixmap.loadFromData(response.content)
            self.finished.emit(pixmap)
        except Exception:
            self.finished.emit(None)


class AccountBanner(QtWidgets.QWidget):
    def __init__(self, cloud: CloudClient, parent=None):
        super().__init__(parent)
        self.cloud = cloud
        self._build()

    def _build(self):
        self.setObjectName("accountBanner")
        lay = QtWidgets.QHBoxLayout(self)
        lay.setContentsMargins(8, 6, 8, 6)

        self.lblEmail = ClickLabel("…")
        font = self.lblEmail.font();
        font.setBold(True);
        self.lblEmail.setFont(font)

        self.lblStatus = QtWidgets.QLabel("…")

        # Sửa nút action thành nút "Quản lý License"
        self.btnManageLicense = QtWidgets.QPushButton("...")
        self.btnManageLicense.setCursor(QtCore.Qt.PointingHandCursor)
        self.btnManageLicense.clicked.connect(self._handle_action_click)

        lay.addWidget(self.lblEmail)
        lay.addSpacing(10)
        lay.addWidget(self.lblStatus, 1, QtCore.Qt.AlignLeft)
        lay.addStretch()
        lay.addWidget(self.btnManageLicense)

        self.menu = QtWidgets.QMenu(self)
        actChange = self.menu.addAction("Đổi mật khẩu")
        actLogout = self.menu.addAction("Đăng xuất")

        actChange.triggered.connect(self._change_pw)
        actLogout.triggered.connect(self._logout)

        self.setStyleSheet("""
        #accountBanner { background:#f5f5f7; border-bottom:1px solid #ddd; }
        """)

    def set_user_state(self, email: str | None, license_text: str, is_logged_in: bool):
        if is_logged_in:
            self.lblEmail.setText(email)
            self.lblEmail.setCursor(QtCore.Qt.PointingHandCursor)
            try:
                self.lblEmail.clicked.disconnect()
            except RuntimeError:
                pass
            self.lblEmail.clicked.connect(self._open_menu)

            self.lblStatus.setText(license_text)
            self.btnManageLicense.setText("Quản lý License")
            self.btnManageLicense.show()
        else:
            self.lblEmail.setText("(chưa đăng nhập)")
            self.lblEmail.setCursor(QtCore.Qt.ArrowCursor)
            try:
                self.lblEmail.clicked.disconnect()
            except RuntimeError:
                pass

            self.lblStatus.setText("Vui lòng đăng nhập để sử dụng")
            self.btnManageLicense.setText("Đăng nhập")
            self.btnManageLicense.show()

    def _open_menu(self):
        self.menu.exec(self.mapToGlobal(QtCore.QPoint(0, self.height())))

    def _change_pw(self):
        dlg = ChangePasswordDialog(self.cloud, self)
        dlg.exec()

    def _logout(self):
        self.cloud.logout()
        QtWidgets.QMessageBox.information(self, "Đăng xuất", "Bạn đã đăng xuất thành công.")
        self.parent().refresh_license()

    def _handle_action_click(self):
        if self.cloud.is_logged_in():
            # Đã đăng nhập -> Mở dialog quản lý
            dlg = LicenseManagerDialog(self.cloud, self)
            dlg.exec()
            # Sau khi dialog đóng, luôn refresh lại banner
            self.parent().refresh_license()
        else:
            # Chưa đăng nhập -> Mở dialog đăng nhập
            dlg = AuthDialog(self)
            if dlg.exec() == QtWidgets.QDialog.Accepted:
                self.cloud = dlg.cloud
                self.parent().refresh_license()


class _Container(QtWidgets.QWidget):
    def __init__(self, banner: AccountBanner, content: QtWidgets.QWidget):
        super().__init__()
        v = QtWidgets.QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0);
        v.setSpacing(0)
        v.addWidget(banner)
        v.addWidget(content, 1)
        self.banner = banner
        self.content = content


class LicenseController(QtCore.QObject):
    def __init__(self, cloud: CloudClient, main_window: QtWidgets.QMainWindow,
                 protected_root: QtWidgets.QWidget):
        super().__init__(main_window)
        self.cloud = cloud
        self.main = main_window
        self.protected_root = protected_root

        self.banner = AccountBanner(cloud, main_window)
        self.container = _Container(self.banner, protected_root)

        if isinstance(main_window, QtWidgets.QMainWindow):
            main_window.setCentralWidget(self.container)

        self.container.refresh_license = self.refresh
        # Gán controller vào main window để dialog có thể gọi lại
        main_window._license_controller = self

        self.refresh()

    def set_enabled_by_license(self, enabled: bool):
        self.protected_root.setEnabled(enabled)

    def refresh(self):
        try:
            st = self.cloud.license_status()
            is_logged_in = st.get("logged_in", False)
            is_valid = st.get("valid", False)

            td = self.cloud.load_token()
            email = td.email if td else None

            if is_logged_in:
                if is_valid:
                    days = st.get("days_left")
                    plan = st.get("plan") or ""
                    status_text = f"Đã kích hoạt ({plan}) — còn {days} ngày"
                    self.set_enabled_by_license(True)
                else:
                    status_text = "Chưa kích hoạt trên thiết bị này"
                    self.set_enabled_by_license(False)
                self.banner.set_user_state(email, status_text, is_logged_in=True)
            else:
                self.banner.set_user_state(None, "", is_logged_in=False)
                self.set_enabled_by_license(False)

        except Exception as e:
            self.banner.set_user_state(None, f"Lỗi: {e}", is_logged_in=False)
            self.set_enabled_by_license(False)


def attach_license_banner(main_window: QtWidgets.QMainWindow,
                          protected_root: QtWidgets.QWidget,
                          cloud: CloudClient) -> LicenseController:
    return LicenseController(cloud, main_window, protected_root)
