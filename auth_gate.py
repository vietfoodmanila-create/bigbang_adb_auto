# auth_gate.py
from __future__ import annotations
import sys
from PySide6 import QtWidgets
from typing import Optional
from ui_auth import AuthDialog, CloudClient

def ensure_logged_in(parent: Optional[QtWidgets.QWidget] = None) -> bool:
    """
    Mở dialog Đăng nhập/Đăng ký/Trạng thái nếu chưa có token hợp lệ.
    Trả True nếu đã đăng nhập hợp lệ (license_status logged_in), False nếu không.
    YÊU CẦU: Gọi sau khi đã có QApplication (QtWidgets.QApplication.instance() != None).
    """
    app = QtWidgets.QApplication.instance()
    if app is None:
        # Cho phép dùng tạm trong trường hợp gọi sớm (ít gặp)
        _tmp_app = QtWidgets.QApplication(sys.argv)

    cloud = CloudClient()
    st = cloud.license_status()  # KHÔNG raise, chỉ trả dict {'logged_in': ...}
    if st.get("logged_in"):
        return True

    dlg = AuthDialog(parent)
    dlg.exec()

    st2 = cloud.license_status()
    return bool(st2.get("logged_in"))
