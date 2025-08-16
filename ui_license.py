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

class ActivateLicenseDialog(QtWidgets.QDialog):
    """Form kích hoạt/gia hạn license + thông tin mua (Zalo/Ngân hàng)."""
    def __init__(self, cloud: CloudClient, parent=None):
        super().__init__(parent)
        self.cloud = cloud
        self.setWindowTitle("Kích hoạt / Gia hạn License — BBTK Auto")
        self.setMinimumWidth(520)
        self._build()

    def _build(self):
        lay = QtWidgets.QVBoxLayout(self)

        group1 = QtWidgets.QGroupBox("Nhập mã license để kích hoạt / gia hạn")
        f1 = QtWidgets.QFormLayout(group1)
        self.leKey = QtWidgets.QLineEdit()
        self.leKey.setPlaceholderText("Nhập mã license…")
        self.leDevice = QtWidgets.QLineEdit(stable_device_uid())
        self.leDevice.setReadOnly(True)
        self.leName = QtWidgets.QLineEdit(QtWidgets.QApplication.instance().applicationName() or "PC")
        self.btnActivate = QtWidgets.QPushButton("Kích hoạt / Gia hạn")
        self.btnActivate.clicked.connect(self.on_activate)
        f1.addRow("Mã license", self.leKey)
        f1.addRow("Thiết bị UID", self.leDevice)
        f1.addRow("Tên thiết bị", self.leName)
        f1.addRow(self.btnActivate)

        group2 = QtWidgets.QGroupBox("Mua license")
        v2 = QtWidgets.QVBoxLayout(group2)

        self.lblZalo = QtWidgets.QLabel("-")
        self.imgZalo = QtWidgets.QLabel()
        self.imgZalo.setFixedSize(120, 120)
        self.imgZalo.setScaledContents(True)

        self.lblBank = QtWidgets.QLabel("-")
        self.imgBank = QtWidgets.QLabel()
        self.imgBank.setFixedSize(160, 160)
        self.imgBank.setScaledContents(True)

        self.lblNote = QtWidgets.QLabel("")
        self.lblNote.setWordWrap(True)
        self.lblZalo.setTextInteractionFlags(QtCore.Qt.TextBrowserInteraction)
        self.lblBank.setTextInteractionFlags(QtCore.Qt.TextBrowserInteraction)

        grid = QtWidgets.QGridLayout()
        grid.addWidget(QtWidgets.QLabel("Zalo hỗ trợ:"), 0, 0)
        grid.addWidget(self.lblZalo, 0, 1)
        grid.addWidget(self.imgZalo, 0, 2)

        grid.addWidget(QtWidgets.QLabel("Ngân hàng:"), 1, 0)
        grid.addWidget(self.lblBank, 1, 1)
        grid.addWidget(self.imgBank, 1, 2)

        grid.addWidget(QtWidgets.QLabel("Nội dung chuyển tiền:"), 2, 0)
        grid.addWidget(self.lblNote, 2, 1, 1, 2)

        v2.addLayout(grid)

        btnClose = QtWidgets.QPushButton("Đóng")
        btnClose.clicked.connect(self.reject)

        lay.addWidget(group1)
        lay.addWidget(group2)
        lay.addStretch()
        row = QtWidgets.QHBoxLayout()
        row.addStretch()
        row.addWidget(btnClose)
        lay.addLayout(row)

        self._load_support_info()

    def _load_support_info(self):
        try:
            j = self.cloud.session.get(self.cloud._url("/api/app/support"), timeout=15).json()
            d = j.get("data", {})
            zalo = d.get("zalo", {})
            bank = d.get("bank", {})
            note_tpl = d.get("note_template") or ""
            # gợi ý note thay bằng email (nếu có)
            email = (self.cloud.load_token() or TokenData("", None)).email or ""
            note = (d.get("note_example") or note_tpl).replace("{email}", email)

            zalo_txt = f"{zalo.get('number','')}"
            link = zalo.get("link")
            if link:
                zalo_txt += f" — <a href='{link}'>Zalo link</a>"
            self.lblZalo.setText(zalo_txt)

            bank_txt = f"{bank.get('name','')} — {bank.get('account','')} ({bank.get('holder','')})"
            self.lblBank.setText(bank_txt)
            self.lblNote.setText(note)

            self._set_img(self.imgZalo, zalo.get("qr_url"))
            self._set_img(self.imgBank, bank.get("qr_url"))
        except Exception as e:
            self.lblZalo.setText(f"Lỗi tải thông tin: {e}")

    def _set_img(self, lbl: QtWidgets.QLabel, url: str | None):
        if not url:
            lbl.clear(); return
        try:
            r = self.cloud.session.get(url, timeout=15)
            if r.ok:
                pm = QtGui.QPixmap()
                pm.loadFromData(r.content)
                lbl.setPixmap(pm)
        except Exception:
            pass

    def on_activate(self):
        key = self.leKey.text().strip()
        if not key:
            QtWidgets.QMessageBox.warning(self, "Thiếu thông tin", "Nhập mã license.")
            return
        try:
            payload = {
                "license_key": key,
                "device_uid": self.leDevice.text().strip(),
                "device_name": self.leName.text().strip()
            }
            r = self.cloud.session.post(self.cloud._url("/api/license/activate"),
                                        headers=self.cloud._auth_headers(),
                                        json=payload, timeout=20)
            if r.status_code >= 400:
                try:
                    msg = r.json().get("error","activate_failed")
                except Exception:
                    msg = r.text
                raise RuntimeError(msg)
            QtWidgets.QMessageBox.information(self, "Thành công", "Kích hoạt / Gia hạn thành công.")
            self.accept()
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Lỗi", f"Kích hoạt thất bại: {e}")

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
