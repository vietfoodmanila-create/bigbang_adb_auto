# checkbox_actions.py
# (NÂNG CẤP LỚN) Sửa lỗi TypeError và tối ưu hóa vòng lặp auto.

from __future__ import annotations
import os
import time
import threading
from pathlib import Path
from typing import Dict, List, Optional
from datetime import datetime, timedelta

from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QCheckBox, QMessageBox
from ui_main import MainWindow, ADB_PATH
from flows_logout import logout_once
from flows_login import login_once
from flows_lien_minh import join_guild_once, ensure_guild_inside
from flows_thoat_lien_minh import run_guild_leave_flow
from flows_xay_dung_lien_minh import run_guild_build_flow
from flows_vien_chinh import run_guild_expedition_flow
from flows_chuc_phuc import run_bless_flow
from ui_auth import CloudClient
from utils_crypto import decrypt

GAME_PKG = "com.phsgdbz.vn"
GAME_ACT = "com.phsgdbz.vn/org.cocos2dx.javascript.GameTwActivity"
_RUNNERS: Dict[int, "AccountRunner"] = {}


# ====== Tiện ích UI (Giữ nguyên) ======
def _table_row_for_port(ctrl, port: int) -> int:
    tv = ctrl.w.tbl_nox
    for r in range(tv.rowCount()):
        it = tv.item(r, 2)
        if it and it.text().strip().isdigit() and int(it.text().strip()) == port:
            return r
    return -1


def _get_ui_state(ctrl, row: int) -> str:
    it = ctrl.w.tbl_nox.item(row, 3)
    return it.text().strip().lower() if it else ""


def _set_checkbox_state_silent(ctrl, row: int, checked: bool):
    chk_container = ctrl.w.tbl_nox.cellWidget(row, 0)
    if chk_container and (chk := chk_container.findChild(QCheckBox)):
        try:
            chk.blockSignals(True)
            chk.setChecked(checked)
        finally:
            chk.blockSignals(False)


def _ui_log(ctrl, port: int, msg: str):
    try:
        ctrl.w.log_msg(f"[{port}] {msg}")
    except Exception:
        print(f"[{port}] {msg}")


# ====== Helpers: ngày/giờ & điều kiện (Giữ nguyên) ======
def _today_str_for_build() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def _now_dt_str_for_api() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _parse_datetime_str(s: str | None) -> Optional[datetime]:
    if not s: return None
    try:
        return datetime.fromisoformat(s)
    except (ValueError, TypeError):
        for fmt in ("%Y%m%d:%H%M", "%Y-%m-%d"):
            try:
                return datetime.strptime(s, fmt)
            except (ValueError, TypeError):
                continue
    return None


def _leave_cooldown_passed(last_leave_str: str | None, minutes: int = 61) -> bool:
    if not last_leave_str: return True
    last_leave_dt = _parse_datetime_str(last_leave_str)
    if not last_leave_dt: return True
    return (datetime.now() - last_leave_dt) >= timedelta(minutes=minutes)


def _expe_cooldown_passed(last_expe_str: str | None, hours: int = 12) -> bool:
    if not last_expe_str: return True
    last_expe_dt = _parse_datetime_str(last_expe_str)
    if not last_expe_dt: return True
    return (datetime.now() - last_expe_dt) >= timedelta(hours=hours)


def _scan_eligible_accounts(accounts_selected: List[Dict], features: dict) -> List[Dict]:
    eligible = []
    today = _today_str_for_build()
    for rec in accounts_selected:
        build_date = rec.get('last_build_date', '')
        last_leave = rec.get('last_leave_time', '')
        last_expe = rec.get('last_expedition_time', '')
        want_build = features.get("build", False)
        want_expe = features.get("expedition", False)
        cool_ok = _leave_cooldown_passed(last_leave)
        build_due = want_build and (build_date != today)
        expe_due = want_expe and _expe_cooldown_passed(last_expe)
        if (build_due and cool_ok) or (expe_due and cool_ok):
            eligible.append(rec)
    return eligible


# ====== Wrapper ADB cho flows_* (Đã sửa lỗi) ======
class SimpleNoxWorker:
    def __init__(self, adb_path: str, port: int, log_cb):
        self.port = port;
        self._adb = adb_path;
        self._serial = f"127.0.0.1:{port}"
        self.game_package = GAME_PKG;
        self.game_activity = GAME_ACT;
        self._log_cb = log_cb

    def _log(self, s: str):
        self._log_cb(f"{s}")

    def _run(self, args: List[str], timeout=8, text=True):
        import subprocess
        try:
            startupinfo = None
            if os.name == 'nt':
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            p = subprocess.run([self._adb, "-s", self._serial, *args], capture_output=True, text=text, timeout=timeout,
                               startupinfo=startupinfo)
            return p.returncode, p.stdout or "", p.stderr or ""
        except subprocess.TimeoutExpired:
            return 124, "", "timeout"
        except Exception as e:
            return 125, "", str(e)

    def _run_raw(self, args: List[str], timeout=8):
        import subprocess
        try:
            startupinfo = None
            if os.name == 'nt':
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            p = subprocess.run([self._adb, "-s", self._serial, *args], capture_output=True, timeout=timeout,
                               startupinfo=startupinfo)
            return p.returncode, p.stdout, p.stderr
        except subprocess.TimeoutExpired:
            return 124, b"", b"timeout"
        except Exception as e:
            return 125, b"", str(e).encode()

    def adb(self, *args, timeout=8):
        return self._run(list(args), timeout=timeout, text=True)

    def adb_bin(self, *args, timeout=8):
        return self._run_raw(list(args), timeout=timeout)

    def app_in_foreground(self, pkg: str) -> bool:
        code, out, _ = self.adb("shell", "cmd", "activity", "get-foreground-activity", timeout=6)
        if code == 0 and out and "ComponentInfo{" in out:
            comp = out.split("ComponentInfo{", 1)[1].split("}", 1)[0]
            return pkg in comp
        return False

    def start_app(self, package: str, activity: Optional[str] = None) -> bool:
        if activity:
            code, _, _ = self.adb("shell", "am", "start", "-n", activity, "-a", "android.intent.action.MAIN", "-c",
                                  "android.intent.category.LAUNCHER", timeout=10)
            if code == 0: return True
        code, _, _ = self.adb("shell", "monkey", "-p", package, "-c", "android.intent.category.LAUNCHER", "1",
                              timeout=10)
        return code == 0

    def wait_app_ready(self, pkg: str, timeout_sec: int = 35) -> bool:
        end = time.time() + timeout_sec
        while time.time() < end:
            if self.app_in_foreground(pkg): return True
            time.sleep(1.0)
        return False


# ====== Runner theo port (Cập nhật logic vòng lặp) ======
class AccountRunner(QObject, threading.Thread):
    finished_run = Signal()

    def __init__(self, ctrl, port: int, adb_path: str, cloud: CloudClient, accounts_selected: List[Dict],
                 user_login_email: str):
        QObject.__init__(self)
        threading.Thread.__init__(self, name=f"AccountRunner-{port}", daemon=True)
        self.ctrl = ctrl;
        self.port = port;
        self.adb_path = adb_path
        self.cloud = cloud;
        self.user_login_email = user_login_email
        self.master_account_list = list(accounts_selected)
        self._stop = threading.Event();
        self._last_log = None
        self.wk = SimpleNoxWorker(adb_path, port, log_cb=lambda s: _ui_log(ctrl, port, s))
        self.stop_evt = threading.Event()
        setattr(self.wk, "_abort", False)

    def request_stop(self):
        self.stop_evt.set();
        self._stop.set();
        setattr(self.wk, "_abort", True)

    def _sleep_coop(self, secs: float):
        end_time = time.time() + secs
        while time.time() < end_time:
            if self.stop_evt.is_set() or self._stop.is_set(): return False
            time.sleep(min(1.0, end_time - time.time()))
        return True

    def log(self, s: str):
        if s != self._last_log: self._last_log = s; _ui_log(self.ctrl, self.port, s)

    def _get_features(self) -> Dict[str, bool]:
        return dict(
            build=self.ctrl.w.chk_build.isChecked(),
            expedition=self.ctrl.w.chk_expedition.isChecked(),
            bless=self.ctrl.w.chk_bless.isChecked(),
            autoleave=self.ctrl.w.chk_auto_leave.isChecked(),
        )

    def run(self):
        self.log(f"Bắt đầu vòng lặp auto với {len(self.master_account_list)} tài khoản đã chọn.")

        while not self._stop.is_set():
            try:
                features = self._get_features()
                eligible_accounts = _scan_eligible_accounts(self.master_account_list, features)

                if not eligible_accounts:
                    self.log("Không có tài khoản nào đủ điều kiện chạy. Tạm nghỉ 1 giờ...")
                    if not self._sleep_coop(3600): break
                    try:
                        self.log("Đang làm mới danh sách tài khoản sau khi nghỉ...")
                        self.master_account_list = self.cloud.get_game_accounts()
                    except Exception as e:
                        self.log(f"Lỗi làm mới danh sách: {e}. Sẽ thử lại sau.")
                    continue

                rec = eligible_accounts[0]
                self.log(
                    f"Lọc tự động: {len(eligible_accounts)} tài khoản đủ điều kiện. Bắt đầu xử lý: {rec.get('game_email')}")

                account_id = rec.get('id')
                email = rec.get('game_email', '')
                encrypted_password = rec.get('game_password', '')
                server = str(rec.get('server', ''))

                try:
                    password = decrypt(encrypted_password, self.user_login_email)
                except Exception as e:
                    self.log(f"⚠️ Lỗi giải mã mật khẩu cho {email}. Bỏ qua. Lỗi: {e}")
                    if not self._sleep_coop(10): break
                    continue

                if not logout_once(self.wk, max_rounds=7):
                    self.log(f"Logout thất bại, sẽ thử lại ở vòng lặp sau.");
                    continue

                ok_login = login_once(self.wk, email, password, server, "")
                if not ok_login:
                    self.log(f"Login thất bại cho {email}.");
                    continue

                did_build = False;
                did_expe = False

                if (features.get("build") or features.get("expedition")) and _leave_cooldown_passed(
                        rec.get('last_leave_time')):
                    join_guild_once(self.wk, log=self.log)

                if features.get("build") and rec.get('last_build_date') != _today_str_for_build():
                    if ensure_guild_inside(self.wk, log=self.log) and run_guild_build_flow(self.wk, log=self.log):
                        did_build = True
                        self.cloud.update_game_account(account_id, {'last_build_date': _today_str_for_build()})
                        self.log(f"📝 [API] Cập nhật ngày xây dựng.")

                if features.get("expedition") and _expe_cooldown_passed(rec.get('last_expedition_time')):
                    if ensure_guild_inside(self.wk, log=self.log) and run_guild_expedition_flow(self.wk, log=self.log):
                        did_expe = True
                        self.cloud.update_game_account(account_id, {'last_expedition_time': _now_dt_str_for_api()})
                        self.log(f"📝 [API] Cập nhật mốc viễn chinh.")

                if features.get("autoleave") and (did_build or did_expe):
                    if run_guild_leave_flow(self.wk, log=self.log):
                        self.cloud.update_game_account(account_id, {'last_leave_time': _now_dt_str_for_api()})
                        self.log(f"📝 [API] Cập nhật mốc rời liên minh.")

                logout_once(self.wk, max_rounds=7)

                try:
                    # Tải lại toàn bộ danh sách để đảm bảo chính xác cho vòng lặp sau
                    self.master_account_list = self.cloud.get_game_accounts()
                    self.log("Đã làm mới bộ nhớ đệm tài khoản sau khi chạy.")
                except Exception as e:
                    self.log(f"Lỗi làm mới bộ nhớ đệm: {e}")

            except Exception as e:
                self.log(f"Lỗi nghiêm trọng trong vòng lặp: {e}. Tạm nghỉ 5 phút.")
                if not self._sleep_coop(300): break

        self.log("Vòng lặp auto đã dừng theo yêu cầu.")
        self.finished_run.emit()

    def _auto_stop_and_uncheck(self):
        row = _table_row_for_port(self.ctrl, self.port)
        if row >= 0: _set_checkbox_state_silent(self.ctrl, row, False)
        self.request_stop()


# ====== API cho UI: gọi khi tick/untick ======
def on_checkbox_toggled(ctrl, port: int, checked: bool):
    row = _table_row_for_port(ctrl, port)
    if row < 0: return

    if checked:
        try:
            lic_status = ctrl.w.cloud.license_status()
            if not lic_status.get("valid"):
                msg = "License chưa kích hoạt hoặc đã hết hạn."
                QMessageBox.warning(ctrl.w, "Lỗi License", msg)
                _ui_log(ctrl, port, f"Không thể bắt đầu auto: {msg}")
                _set_checkbox_state_silent(ctrl, row, False);
                return
        except Exception as e:
            QMessageBox.critical(ctrl.w, "Lỗi kiểm tra License", f"Không thể xác thực license:\n{e}")
            _ui_log(ctrl, port, f"Không thể bắt đầu auto: Lỗi kiểm tra license.")
            _set_checkbox_state_silent(ctrl, row, False);
            return

        accounts_selected = []
        all_online_accounts = ctrl.w.online_accounts
        for r in range(ctrl.w.tbl_acc.rowCount()):
            chk_widget = ctrl.w.tbl_acc.cellWidget(r, 0)
            checkbox = chk_widget.findChild(QCheckBox) if chk_widget else None
            if checkbox and checkbox.isChecked():
                if r < len(all_online_accounts): accounts_selected.append(all_online_accounts[r])

        if not accounts_selected:
            _ui_log(ctrl, port, "Chưa có tài khoản nào được chọn để chạy.")
            _set_checkbox_state_silent(ctrl, row, False);
            return

        user_login_email = ctrl.w.cloud.load_token().email
        if not user_login_email:
            _ui_log(ctrl, port, "Lỗi: Không tìm thấy email người dùng.");
            return

        _ui_log(ctrl, port, f"Chuẩn bị chạy auto cho {len(accounts_selected)} tài khoản đã chọn.")
        try:
            adb_path = str(ADB_PATH)
        except Exception:
            adb_path = r"D:\Program Files\Nox\bin\adb.exe"
        if (r := _RUNNERS.get(port)) and r.is_alive():
            _ui_log(ctrl, port, "Auto đang chạy.");
            return

        runner = AccountRunner(ctrl, port, adb_path, ctrl.w.cloud, accounts_selected, user_login_email)
        runner.finished_run.connect(lambda: _set_checkbox_state_silent(ctrl, row, False))

        _RUNNERS[port] = runner;
        runner.start();
        _ui_log(ctrl, port, "Bắt đầu auto.")

    else:
        if r := _RUNNERS.get(port): r.request_stop()
        _RUNNERS.pop(port, None)
        _ui_log(ctrl, port, "Đã gửi yêu cầu dừng auto.")