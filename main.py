# main.py — sync danh sách/ trạng thái mỗi giây + worker ADB (KHÔNG tự xóa dòng)

import sys
import subprocess
import socket
from pathlib import Path
from typing import Optional, List, Set
import re
import os
import requests
from PySide6.QtCore import QObject, QThread, QTimer, Signal, Qt
from PySide6.QtWidgets import QApplication, QCheckBox, QTableWidgetItem,QDialog,QMessageBox,QProgressDialog

from ui_main import MainWindow, ADB_PATH, list_adb_ports_with_status, list_known_ports_from_data
from ui_auth import CloudClient, AuthDialog

CURRENT_VERSION = "1.0" # Đặt phiên bản hiện tại của ứng dụng ở đây


def check_for_updates(cloud_client):
    """Kiểm tra và xử lý cập nhật."""
    try:
        print("Đang kiểm tra phiên bản mới...")
        # Giả định bạn đã thêm API /api/app/version
        response = requests.get(f"{cloud_client.base_url}/api/app/version", timeout=10)
        response.raise_for_status()
        latest_info = response.json()

        latest_version = latest_info.get("version")

        if latest_version and latest_version > CURRENT_VERSION:
            notes = latest_info.get("notes", "Không có mô tả.")
            update_url = latest_info.get("url")

            reply = QMessageBox.information(
                None,
                "Có phiên bản mới!",
                f"Đã có phiên bản {latest_version} (bạn đang dùng {CURRENT_VERSION}).\n\n"
                f"Nội dung cập nhật:\n{notes}\n\n"
                "Bạn có muốn tải về và cài đặt ngay bây giờ không?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )

            if reply == QMessageBox.Yes and update_url:
                download_and_launch_updater(update_url)
                return True  # Báo hiệu cần thoát ứng dụng để cập nhật

    except Exception as e:
        print(f"Lỗi khi kiểm tra cập nhật: {e}")

    return False  # Không có cập nhật hoặc người dùng từ chối


def download_and_launch_updater(url):
    """Tải file zip và khởi chạy updater.py."""
    try:
        # Tải file
        response = requests.get(url, stream=True, timeout=300)
        response.raise_for_status()
        total_size = int(response.headers.get('content-length', 0))

        zip_path = Path("update.zip")

        progress = QProgressDialog("Đang tải bản cập nhật...", "Hủy", 0, total_size)
        progress.setWindowModality(Qt.WindowModal)
        progress.show()

        downloaded = 0
        with open(zip_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                if progress.wasCanceled():
                    raise Exception("Người dùng đã hủy tải.")
                f.write(chunk)
                downloaded += len(chunk)
                progress.setValue(downloaded)

        progress.setValue(total_size)

        # Khởi chạy updater
        main_app_executable = os.path.abspath(sys.argv[0])  # Đường dẫn đến main.py
        main_app_pid = os.getpid()

        # Chạy updater.py bằng chính trình thông dịch python hiện tại
        subprocess.Popen([
            sys.executable,
            "updater.py",
            str(zip_path.resolve()),
            str(main_app_pid),
            main_app_executable
        ])

    except Exception as e:
        QMessageBox.critical(None, "Lỗi", f"Quá trình tải cập nhật thất bại:\n{e}")
        raise  # Ném lại lỗi để ngăn ứng dụng chính tiếp tục


def run_cmd(cmd: list[str], timeout=6) -> tuple[int, str, str]:
    try:
        startupinfo = None
        if os.name == 'nt':
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, startupinfo=startupinfo)
        return p.returncode, p.stdout.strip(), p.stderr.strip()
    except Exception as e: return -1, "", f"ERR:{e}"

def resolve_adb_path() -> Optional[str]:
    p = Path(str(ADB_PATH)) if ADB_PATH else Path("")
    if p.exists(): return str(p)
    code, _, _ = run_cmd(["adb", "version"], timeout=3)
    return "adb" if code == 0 else None

def probe_nox_port(port: int, timeout=0.5) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=timeout): return True
    except Exception: return False

class NoxWorker(QObject):
    statusChanged = Signal(int, str)
    def __init__(self, port: int):
        super().__init__()
        self.port = port; self._running = False; self._serial = f"127.0.0.1:{self.port}"; self._adb = resolve_adb_path()
        self.runRequested = False; self.game_package = "com.phsgdbz.vn"; self.game_activity = "com.phsgdbz.vn/org.cocos2dx.javascript.GameTwActivity"
        self.accounts = []; self.features = {}; self._last_status = None; self._last_game_state = None; self._last_top_pkg = None
    def emit_status(self, text: str):
        if text != self._last_status: self._last_status = text; self.statusChanged.emit(self.port, text)
    def start(self): self._running = True
    def stop(self): self._running = False
    def isRunning(self): return self._running
    def adb(self, *args, timeout=6):
        if not self._adb: return -1, "", "adb not found"
        return run_cmd([self._adb, "-s", self._serial, *args], timeout)
    def adb_no_serial(self, *args, timeout=6):
        if not self._adb: return -1, "", "adb not found"
        return run_cmd([self._adb, *args], timeout)
    def ensure_connected(self) -> bool:
        if not self._adb: self.emit_status("adb not found"); return False
        code, out, _ = self.adb("get-state", timeout=2)
        if code == 0 and out.strip() == "device": return True
        self.adb_no_serial("start-server", timeout=3); self.adb_no_serial("connect", self._serial, timeout=3)
        code, out, _ = self.adb("get-state", timeout=2)
        return code == 0 and out.strip() == "device"
    def boot_completed(self) -> bool:
        code, out, _ = self.adb("shell", "getprop", "sys.boot_completed", timeout=3)
        return code == 0 and out.strip() == "1"
    def _top_component_precise(self) -> str | None:
        code, out, _ = self.adb("shell", "dumpsys", "activity", "activities", timeout=8)
        if code == 0 and out:
            for line in out.splitlines():
                if "topResumedActivity" in line or "mResumedActivity" in line:
                    if m := re.search(r"([a-zA-Z0-9_.]+/[a-zA-Z0-9_.$]+)", line): return m.group(1)
        code, out, _ = self.adb("shell", "dumpsys", "window", "windows", timeout=8)
        if code == 0 and out:
            for line in out.splitlines():
                if "mCurrentFocus" in line or "mFocusedApp" in line:
                    if m := re.search(r"([a-zA-Z0-9_.]+/[a-zA-Z0-9_.$]+)", line): return m.group(1)
        return None
    def _top_package(self) -> str | None:
        comp = self._top_component_precise()
        return comp.split("/", 1)[0] if comp and "/" in comp else None
    def app_in_foreground(self, pkg: str) -> bool:
        top_pkg = self._top_package()
        if top_pkg != self._last_top_pkg: self._last_top_pkg = top_pkg
        return (top_pkg == pkg)
    def start_app(self, package: str, activity: str | None = None) -> bool:
        if activity:
            code, _, _ = self.adb("shell", "am", "start", "-n", activity, "-a", "android.intent.action.MAIN", "-c", "android.intent.category.LAUNCHER", timeout=10)
            if code == 0: return True
        code, _, _ = self.adb("shell", "monkey", "-p", package, "-c", "android.intent.category.LAUNCHER", "1", timeout=10)
        return code == 0
    def wait_app_ready(self, package: str, timeout_sec: int = 45) -> bool:
        import time
        end = time.time() + timeout_sec
        while time.time() < end:
            if self.app_in_foreground(package): return True
            time.sleep(1.0)
        return False
    def detect_game_state(self) -> str:
        comp = self._top_component_precise() or ""
        if "com.bbt.android.sdk.login.HWLoginActivity" in comp: return "need_login"
        if "org.cocos2dx.javascript.GameTwActivity" in comp: return "logged_in"
        return "unknown"
    def doTask(self):
        if not self._running: return
        if not probe_nox_port(self.port): self.emit_status("offline"); return
        if not self.ensure_connected(): self.emit_status("offline"); return
        if not self.boot_completed(): self.emit_status("booting…"); return
        if not getattr(self, "runRequested", False): self.emit_status("online"); return
        pkg = getattr(self, "game_package", None); act = getattr(self, "game_activity", None)
        if not pkg: self.emit_status("online"); return
        code, out, _ = self.adb("shell", "pidof", pkg, timeout=3)
        is_running = (code == 0 and bool(out.strip()))
        if not is_running:
            self.emit_status("Mở game…");
            if self.start_app(pkg, act): self.wait_app_ready(pkg, 90)
        elif not self.app_in_foreground(pkg):
            self.emit_status("Đưa game ra màn hình…"); self.start_app(pkg, act); self.wait_app_ready(pkg, 30)
        else: self.emit_status("Game foreground")
        state = self.detect_game_state()
        if state != self._last_game_state:
            self._last_game_state = state
            if state == "need_login": self.emit_status("Cần đăng nhập")
            elif state == "logged_in": self.emit_status("Đang trong game")
            else: self.emit_status("Không xác định trạng thái")

class AppController(QObject):
    def __init__(self, window: MainWindow):
        super().__init__(window)
        self.w = window; self.threads: dict[int, QThread] = {}; self.workers: dict[int, NoxWorker] = {}
        self.hook_checkboxes()
        self.statusTimer = QTimer(self.w); self.statusTimer.timeout.connect(self.on_tick); self.statusTimer.start(5000)
        self.w.destroyed.connect(self.stop_all)
    def hook_checkboxes(self):
        for row in range(self.w.tbl_nox.rowCount()): self._hook_row_checkbox(row)
    def _hook_row_checkbox(self, row: int):
        chk: QCheckBox = self.w.tbl_nox.cellWidget(row, 0)
        if chk is None or getattr(chk, "_connected", False): return
        port = int(self.w.tbl_nox.item(row, 2).text())
        import checkbox_actions
        chk.toggled.connect(lambda checked, p=port: checkbox_actions.on_checkbox_toggled(self, p, checked))
        chk._connected = True
    def on_toggle(self, port: int, state: bool):
        if port in self.workers: self.workers[port].runRequested = state
    def start_worker(self, port: int):
        if port in self.workers and self.workers[port].isRunning(): return
        th = QThread(self.w); wk = NoxWorker(port); wk.moveToThread(th)
        th.started.connect(wk.start); wk.statusChanged.connect(self.on_worker_status)
        self.threads[port] = th; self.workers[port] = wk; th.start()
    def stop_worker(self, port: int):
        wk = self.workers.get(port); th = self.threads.get(port)
        if wk: wk.stop()
        if th: th.quit(); th.wait()
        self.workers.pop(port, None); self.threads.pop(port, None)
        self.update_status_cell(port, "Stopped")
    def stop_all(self):
        if self.statusTimer: self.statusTimer.stop()
        for p in list(self.workers.keys()): self.stop_worker(p)
    def get_ui_ports(self) -> List[int]:
        if self.w.tbl_nox is None or self.w.tbl_nox.parent() is None: return []
        return [int(self.w.tbl_nox.item(r, 2).text()) for r in range(self.w.tbl_nox.rowCount()) if self.w.tbl_nox.item(r, 2)]
    def add_row_for_port(self, port: int, online: bool):
        r = self.w.tbl_nox.rowCount(); self.w.tbl_nox.insertRow(r)
        chk = QCheckBox(); self.w.tbl_nox.setCellWidget(r, 0, chk)
        def mk_item(text: str, center=False):
            it = QTableWidgetItem(text); it.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
            if center: it.setTextAlignment(Qt.AlignCenter)
            return it
        self.w.tbl_nox.setItem(r, 1, mk_item(f"Nox({port})")); self.w.tbl_nox.setItem(r, 2, mk_item(str(port), center=True))
        self.w.tbl_nox.setItem(r, 3, mk_item("online" if online else "offline", center=True)); self.w.tbl_nox.setItem(r, 4, mk_item("IDLE"))
        self._hook_row_checkbox(r)
    def sync_nox_table(self):
        try:
            adb_map = list_adb_ports_with_status(); known = set(list_known_ports_from_data())
            target_ports = sorted(set(adb_map.keys()) | known); current_ports = set(self.get_ui_ports())
            for p in target_ports:
                if p not in current_ports: self.add_row_for_port(p, online=(adb_map.get(p) == "device"))
            for row in range(self.w.tbl_nox.rowCount()):
                port_item = self.w.tbl_nox.item(row, 2);
                if not port_item: continue
                port = int(port_item.text()); is_online = probe_nox_port(port)
                self.w.tbl_nox.item(row, 3).setText("online" if is_online else "offline")
                if is_online and port not in self.workers: self.start_worker(port)
                elif not is_online and port in self.workers: self.stop_worker(port)
            self.hook_checkboxes()
        except RuntimeError: pass
    def on_tick(self):
        self.sync_nox_table()
        for wk in self.workers.values(): wk.doTask()
    def on_worker_status(self, port: int, text: str): self.update_status_cell(port, text)
    def update_status_cell(self, port: int, text: str):
        try:
            for row in range(self.w.tbl_nox.rowCount()):
                port_item = self.w.tbl_nox.item(row, 2)
                if port_item and port_item.text().isdigit() and int(port_item.text()) == port:
                    self.w.tbl_nox.item(row, 4).setText(text); break
        except RuntimeError: pass

if __name__ == "__main__":
    os.environ.setdefault("QT_QPA_PLATFORM", "windows")
    app = QApplication(sys.argv)
    cloud = CloudClient()
    # (MỚI) Kiểm tra cập nhật ngay sau khi có cloud client
    if check_for_updates(cloud):
        sys.exit(0)  # Thoát để updater hoạt động
    td = cloud.load_token()
    if not td or not td.token:
        dlg = AuthDialog()
        if dlg.exec() != QDialog.Accepted: sys.exit(0)
        cloud = dlg.cloud
    import checkbox_actions
    win = MainWindow(cloud=cloud)
    ctrl = AppController(win)
    try:
        from ui_license import attach_license_system
        lic_ctrl = attach_license_system(win, cloud)
        win._license_controller = lic_ctrl
    except Exception as e:
        print(f"attach_license_system failed: {e}")
        try:
            st = cloud.license_status()
            if not st.get("valid"): win.tabs.setEnabled(False)
        except Exception as e2: print(f"license_status fallback failed: {e2}")
    win.show()
    sys.exit(app.exec())