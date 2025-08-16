# main.py — sync danh sách/ trạng thái mỗi giây + worker ADB (KHÔNG tự xóa dòng)

import sys
import subprocess
import socket
# import checkbox_actions   # (DỜI XUỐNG DƯỚI SAU KHI VƯỢT CỔNG ĐĂNG NHẬP)
from pathlib import Path
from typing import Optional, List, Set
import re
import os  # NEW: để set QT_QPA_PLATFORM
import requests
from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QApplication, QCheckBox, QTableWidgetItem,QDialog
from PySide6.QtCore import QObject, QThread, QTimer, Signal, Qt

from ui_main import (
    MainWindow,
    ADB_PATH,
    list_adb_ports_with_status,
    list_known_ports_from_data,

)
from ui_auth import CloudClient, AuthDialog
from ui_license import attach_license_banner  # << Gắn banner + khóa/mở UI theo license

# ===== Utils =====
def run_cmd(cmd: list[str], timeout=6) -> tuple[int, str, str]:
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)

        return p.returncode, p.stdout.strip(), p.stderr.strip()
    except Exception as e:
        return -1, "", f"ERR:{e}"


def resolve_adb_path() -> Optional[str]:
    p = Path(str(ADB_PATH)) if ADB_PATH else Path("")
    if p.exists():
        return str(p)
    code, _, _ = run_cmd(["adb", "version"], timeout=3)
    return "adb" if code == 0 else None


def probe_nox_port(port: int, timeout=0.5) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=timeout):
            return True
    except Exception:
        return False

def set_logged_out_ui(self):
    # Ẩn/hiện các nút
    self.btnLogin.setVisible(True)
    if hasattr(self, "btnActivate"):
        self.btnActivate.setEnabled(False)
    self.btnLogout.setVisible(False)
    self.btnChangePass.setVisible(False)

    # Clear banner
    self.lblEmail.setText("Chưa đăng nhập")
    self.lblLicense.setText("—")

    # Tắt toàn bộ tính năng
    self.enable_features(False)


def set_logged_in_ui(self, email: str, lic: dict | None):
    self.btnLogin.setVisible(False)
    self.btnLogout.setVisible(True)
    self.btnChangePass.setVisible(True)

    self.lblEmail.setText(email if email else "(không rõ)")
    if lic and lic.get("valid"):
        days = lic.get("days_left", 0)
        self.lblLicense.setText(f"Đã kích hoạt — còn {days} ngày")
        self.enable_features(True)
        if hasattr(self, "btnActivate"):
            self.btnActivate.setEnabled(True)
    else:
        self.lblLicense.setText("Chưa kích hoạt")
        self.enable_features(False)
        if hasattr(self, "btnActivate"):
            self.btnActivate.setEnabled(True)  # bật để người dùng kích hoạt

def refresh_auth_and_license(self):
    td = self.cloud.load_token()
    if not td or not td.token:
        self.set_logged_out_ui()
        return

    try:
        st = self.cloud.license_status()  # sẽ raise nếu token hết hạn
        # Nếu server trả về JSON kiểu {ok, valid, days_left,...}
        self.set_logged_in_ui(td.email, st)
    except requests.HTTPError as e:
        msg = str(e)
        # Token hỏng/hết hạn → coi như đăng xuất
        if "no_token" in msg or "bad_token" in msg or "device_mismatch" in msg:
            self.cloud.clear_token()
            self.set_logged_out_ui()
        else:
            # Không xác định → vẫn coi như chưa kích hoạt
            self.set_logged_in_ui(td.email if td else "", {"valid": False})

def on_logout_clicked(self):
    try:
        # Nếu bạn có /api/logout server thì giữ nguyên; nếu không cũng OK
        self.cloud.logout()
    finally:
        # BẮT BUỘC: reset UI + gỡ token+header
        self.cloud.clear_token()
        self.set_logged_out_ui()


def on_login_clicked(self):
    # Mở hộp thoại đăng nhập
    dlg = AuthDialog()
    if dlg.exec() != 1:  # QDialog.Rejected
        return
    # Đăng nhập thành công: đồng bộ token và license
    td = self.cloud.load_token()
    if not td or not td.token:
        self.set_logged_out_ui()
        return
    try:
        st = self.cloud.license_status()
        self.set_logged_in_ui(td.email, st)
    except requests.HTTPError as e:
        msg = str(e)
        if "no_token" in msg or "bad_token" in msg or "device_mismatch" in msg:
            self.cloud.clear_token()
            self.set_logged_out_ui()
        else:
            self.set_logged_in_ui(td.email if td else "", {"valid": False})

# ===== Worker =====
class NoxWorker(QObject):
    statusChanged = Signal(int, str)

    def __init__(self, port: int):
        super().__init__()
        self.port = port
        self._running = False
        self._serial = f"127.0.0.1:{self.port}"
        self._adb = resolve_adb_path()

        # các field do checkbox_actions gán
        self.runRequested = False
        self.game_package = "com.phsgdbz.vn"
        self.game_activity = "com.phsgdbz.vn/org.cocos2dx.javascript.GameTwActivity"
        self.accounts = []
        self.features = {}

        # chống nháy log
        self._last_status = None
        self._last_game_state = None
        self._last_top_pkg = None

    # ===== tiện ích status (chỉ emit khi thay đổi) =====
    def emit_status(self, text: str):
        if text != self._last_status:
            self._last_status = text
            self.statusChanged.emit(self.port, text)

    # ===== vòng đời =====
    def start(self): self._running = True
    def stop(self):  self._running = False
    def isRunning(self): return self._running

    # ===== ADB =====
    def adb(self, *args, timeout=6):
        if not self._adb:
            return -1, "", "adb not found"
        return run_cmd([self._adb, "-s", self._serial, *args], timeout)

    def adb_no_serial(self, *args, timeout=6):
        if not self._adb:
            return -1, "", "adb not found"
        return run_cmd([self._adb, *args], timeout)

    # ===== probe cơ bản =====
    def ensure_connected(self) -> bool:
        if not self._adb:
            self.emit_status("adb not found")
            return False
        code, out, _ = self.adb("get-state", timeout=2)
        if code == 0 and out.strip() == "device":
            return True
        # thử connect
        self.adb_no_serial("start-server", timeout=3)
        self.adb_no_serial("connect", self._serial, timeout=3)
        code, out, _ = self.adb("get-state", timeout=2)
        return code == 0 and out.strip() == "device"

    def boot_completed(self) -> bool:
        code, out, _ = self.adb("shell", "getprop", "sys.boot_completed", timeout=3)
        return code == 0 and out.strip() == "1"

    def current_focus(self) -> str:
        code, out, err = self.adb("shell", "dumpsys", "window", "windows", timeout=4)
        if code != 0:
            return f"err:{err or 'focus'}"
        for line in out.splitlines():
            if "mCurrentFocus" in line or "mFocusedApp" in line:
                return line.strip()
        return "unknown"

    # ===== lấy app đang top (chính xác) =====
    def _top_component_precise(self) -> str | None:
        # 1) dumpsys activity
        code, out, _ = self.adb("shell", "dumpsys", "activity", "activities", timeout=8)
        if code == 0 and out:
            for line in out.splitlines():
                if "topResumedActivity" in line or "mResumedActivity" in line:
                    m = re.search(r"([a-zA-Z0-9_.]+/[a-zA-Z0-9_.$]+)", line)
                    if m:
                        return m.group(1)
        # 2) dumpsys window
        code, out, _ = self.adb("shell", "dumpsys", "window", "windows", timeout=8)
        if code == 0 and out:
            for line in out.splitlines():
                if "mCurrentFocus" in line or "mFocusedApp" in line:
                    m = re.search(r"([a-zA-Z0-9_.]+/[a-zA-Z0-9_.$]+)", line)
                    if m:
                        return m.group(1)
        return None

    def _top_package(self) -> str | None:
        comp = self._top_component_precise()
        return comp.split("/", 1)[0] if comp and "/" in comp else None

    def app_in_foreground(self, pkg: str) -> bool:
        top_pkg = self._top_package()
        if top_pkg != self._last_top_pkg:
            self._last_top_pkg = top_pkg
        return (top_pkg == pkg)

    # ===== mở app / đợi foreground =====
    def start_app(self, package: str, activity: str | None = None) -> bool:
        if activity:
            code, _, _ = self.adb("shell", "am", "start", "-n", activity,
                                  "-a", "android.intent.action.MAIN",
                                  "-c", "android.intent.category.LAUNCHER",
                                  timeout=10)
            if code == 0:
                return True
        code, _, _ = self.adb("shell", "monkey", "-p", package,
                              "-c", "android.intent.category.LAUNCHER", "1", timeout=10)
        return code == 0

    def wait_app_ready(self, package: str, timeout_sec: int = 45) -> bool:
        import time
        end = time.time() + timeout_sec
        while time.time() < end:
            if self.app_in_foreground(package):
                return True
            time.sleep(1.0)
        return False

    # ===== nhận diện trạng thái game (đÃ SỬA mapping) =====
    def detect_game_state(self) -> str:
        comp = self._top_component_precise() or ""
        if "com.bbt.android.sdk.login.HWLoginActivity" in comp:
            return "need_login"   # đang ở màn hình đăng nhập
        if "org.cocos2dx.javascript.GameTwActivity" in comp:
            return "logged_in"    # đã vào game
        return "unknown"

    # ===== vòng làm việc chính =====
    def doTask(self):
        if not self._running:
            return

        # 1) Port
        if not probe_nox_port(self.port):
            self.emit_status("offline")
            return

        # 2) ADB
        if not self.ensure_connected():
            self.emit_status("offline")
            return

        # 3) Boot
        if not self.boot_completed():
            self.emit_status("booting…")
            return

        # 4) Chưa bật auto → chỉ báo online (ít log)
        if not getattr(self, "runRequested", False):
            self.emit_status("online")
            return

        # 5) Giữ game foreground
        pkg = getattr(self, "game_package", None)
        act = getattr(self, "game_activity", None)
        if not pkg:
            self.emit_status("online")
            return

        # a) tiến trình có chạy?
        code, out, _ = self.adb("shell", "pidof", pkg, timeout=3)
        is_running = (code == 0 and bool(out.strip()))
        if not is_running:
            self.emit_status("Mở game…")
            if self.start_app(pkg, act):
                self.wait_app_ready(pkg, 90)
        # b) đang chạy nhưng bị ẩn → đưa ra trước
        elif not self.app_in_foreground(pkg):
            self.emit_status("Đưa game ra màn hình…")
            self.start_app(pkg, act)
            self.wait_app_ready(pkg, 30)
        else:
            self.emit_status("Game foreground")

        # c) trạng thái trong game (log khi đổi)
        state = self.detect_game_state()
        if state != self._last_game_state:
            self._last_game_state = state
            if state == "need_login":
                self.emit_status("Cần đăng nhập")
            elif state == "logged_in":
                self.emit_status("Đang trong game")
            else:
                self.emit_status("Không xác định trạng thái")


# ===== Controller =====
class AppController(QObject):
    def __init__(self, window: MainWindow):
        super().__init__(window)
        self.w = window
        self.threads: dict[int, QThread] = {}
        self.workers: dict[int, NoxWorker] = {}

        self.hook_checkboxes()  # lần đầu

        self.statusTimer = QTimer(self.w)
        self.statusTimer.timeout.connect(self.on_tick)
        self.statusTimer.start(5000)

        self.w.destroyed.connect(self.stop_all)

    # --- checkbox wiring ---
    def hook_checkboxes(self):
        for row in range(self.w.tbl_nox.rowCount()):
            self._hook_row_checkbox(row)

    def _hook_row_checkbox(self, row: int):
        chk: QCheckBox = self.w.tbl_nox.cellWidget(row, 0)
        if chk is None:
            return
        if getattr(chk, "_connected", False):
            return  # đã gắn rồi

        port = int(self.w.tbl_nox.item(row, 2).text())
        import checkbox_actions  # gắn SAU auth gate
        chk.toggled.connect(lambda checked, p=port: checkbox_actions.on_checkbox_toggled(self, p, checked))
        chk._connected = True

    def on_toggle(self, port: int, state: int):
        if state:
            self.start_worker(port)
        else:
            self.stop_worker(port)

    # --- worker lifecycle ---
    def start_worker(self, port: int):
        if port in self.workers and self.workers[port].isRunning():
            return
        th = QThread(self.w)
        wk = NoxWorker(port)
        wk.moveToThread(th)
        th.started.connect(wk.start)
        wk.statusChanged.connect(self.on_worker_status)
        self.threads[port] = th
        self.workers[port] = wk
        th.start()

    def stop_worker(self, port: int):
        wk = self.workers.get(port); th = self.threads.get(port)
        if wk: wk.stop()
        if th: th.quit(); th.wait()
        self.workers.pop(port, None); self.threads.pop(port, None)
        self.update_status_cell(port, "Stopped")

    def stop_all(self):
        for p in list(self.workers.keys()):
            self.stop_worker(p)

    # --- table helpers ---
    def get_ui_ports(self) -> List[int]:
        ports = []
        for row in range(self.w.tbl_nox.rowCount()):
            it = self.w.tbl_nox.item(row, 2)
            if it:
                try:
                    ports.append(int(it.text()))
                except:
                    pass
        return ports

    def add_row_for_port(self, port: int, online: bool):
        r = self.w.tbl_nox.rowCount()
        self.w.tbl_nox.insertRow(r)

        chk = QCheckBox()
        chk.setChecked(False)
        self.w.tbl_nox.setCellWidget(r, 0, chk)

        def mk_item(text: str, center=False):
            it = QTableWidgetItem(text)
            it.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
            if center:
                it.setTextAlignment(Qt.AlignCenter)
            return it

        self.w.tbl_nox.setItem(r, 1, mk_item(f"Nox({port})"))
        self.w.tbl_nox.setItem(r, 2, mk_item(str(port), center=True))
        self.w.tbl_nox.setItem(r, 3, mk_item("online" if online else "offline", center=True))
        self.w.tbl_nox.setItem(r, 4, mk_item("IDLE"))

        self._hook_row_checkbox(r)

    # --- sync mỗi giây ---
    def sync_nox_table(self):
        adb_map = list_adb_ports_with_status()     # {port: status}
        known: Set[int] = set(list_known_ports_from_data())
        target_ports = sorted(set(adb_map.keys()) | known)
        current_ports = set(self.get_ui_ports())

        # Thêm port mới; KHÔNG tự xóa port cũ
        for p in target_ports:
            if p not in current_ports:
                self.add_row_for_port(p, online=(adb_map.get(p) == "device"))

        # Cập nhật trạng thái online/offline bằng socket probe
        for row in range(self.w.tbl_nox.rowCount()):
            port = int(self.w.tbl_nox.item(row, 2).text())
            state_text = "online" if probe_nox_port(port) else "offline"
            self.w.tbl_nox.item(row, 3).setText(state_text)

        # đảm bảo checkbox mới được hook
        self.hook_checkboxes()

    # --- tick ---
    def on_tick(self):
        self.sync_nox_table()
        for wk in self.workers.values():
            wk.doTask()

    # --- UI update ---
    def on_worker_status(self, port: int, text: str):
        self.update_status_cell(port, text)

    def update_status_cell(self, port: int, text: str):
        for row in range(self.w.tbl_nox.rowCount()):
            if int(self.w.tbl_nox.item(row, 2).text()) == port:
                self.w.tbl_nox.item(row, 4).setText(text)
                break


# ===== Entry =====
if __name__ == "__main__":
    # Giữ ổn định Qt trên Windows (nếu bạn đang chạy trên Windows)
    os.environ.setdefault("QT_QPA_PLATFORM", "windows")

    app = QApplication(sys.argv)

    # === AUTH-GATE: chỉ mở hộp thoại đăng nhập nếu chưa có token ===
    from ui_auth import AuthDialog, CloudClient
    cloud = CloudClient()
    td = cloud.load_token()
    if not td or not td.token:
        dlg = AuthDialog()
        if dlg.exec() != QDialog.Accepted:
            sys.exit(0)  # người dùng hủy

    # Import các phần còn lại SAU khi đã đăng nhập
    import checkbox_actions

    # Tạo cửa sổ chính + controller như logic gốc của bạn
    win = MainWindow()
    ctrl = AppController(win)

    # === GẮN THANH THÔNG TIN LICENSE + KHOÁ GIAO DIỆN KHI CHƯA ACTIVE ===
    try:
        from ui_license import attach_license_banner

        lic_ctrl = attach_license_banner(win, win.centralWidget(), cloud)
        lic_ctrl.refresh()  # cập nhật ngay theo trạng thái license

        from PySide6 import QtCore
        _lic_timer = QtCore.QTimer(win)
        _lic_timer.setInterval(60000)           # 60 giây/lần
        _lic_timer.timeout.connect(lic_ctrl.refresh)
        _lic_timer.start()

        # giữ tham chiếu để tránh bị GC
        win._license_controller = lic_ctrl
        win._license_timer = _lic_timer

    except Exception as e:
        print("attach_license_banner failed:", e)
        # Fallback: nếu không gắn được banner thì vẫn kiểm tra license 1 lần
        try:
            st = cloud.license_status()
            valid = bool(st.get("valid", True))
            if not valid:
                from PySide6 import QtWidgets
                root = win.centralWidget() or win
                for w in root.findChildren(QtWidgets.QWidget):
                    w.setEnabled(False)
        except Exception as e2:
            print("license_status fallback failed:", e2)

    win.show()
    sys.exit(app.exec())
