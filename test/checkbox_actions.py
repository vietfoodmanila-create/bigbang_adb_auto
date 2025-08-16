# checkbox_actions.py
# Start/Stop auto theo từng port khi tick/untick checkbox.
# - Tick: chạy thread cho port → vòng lặp đọc accounts.txt → (logout nếu cần) → login → (hook tính năng) → logout → next account
# - Untick: dừng thread port đó.
#
# Không đụng tới main.py. Tất cả logic nằm ở đây.

from __future__ import annotations
import threading, time, re
import os
import time
from pathlib import Path
from typing import Dict, List, Tuple, Optional

from ui_main import read_accounts_5cols  # dùng lại hàm đọc accounts của bạn
from flows_logout import logout_once
from flows_login import login_once
from flows_lien_minh import join_guild_once, ensure_guild_inside
from flows_thoat_lien_minh import run_guild_leave_flow
from flows_xay_dung_lien_minh import run_guild_build_flow
from flows_vien_chinh import run_guild_expedition_flow
from datetime import datetime, timedelta
from threading import Thread

# ====== Cấu hình game (đồng bộ test) ======
GAME_PKG = "com.phsgdbz.vn"
GAME_ACT = "com.phsgdbz.vn/org.cocos2dx.javascript.GameTwActivity"

# ====== Quản lý runner theo port ======
_RUNNERS: Dict[int, "AccountRunner"] = {}

# ====== Tiện ích UI ======
def _table_row_for_port(ctrl, port: int) -> int:
    """Tìm dòng trong bảng Nox theo cột port (cột 2)."""
    tv = ctrl.w.tbl_nox
    for r in range(tv.rowCount()):
        it = tv.item(r, 2)
        if not it:
            continue
        try:
            if int(it.text()) == port:
                return r
        except Exception:
            pass
    return -1

def _get_ui_state(ctrl, row: int) -> str:
    it = ctrl.w.tbl_nox.item(row, 3)
    return it.text().strip().lower() if it else ""

def _set_checkbox_state_silent(ctrl, row: int, checked: bool):
    chk = ctrl.w.tbl_nox.cellWidget(row, 0)
    if chk:
        try:
            # tránh phát sinh tín hiệu lặp
            chk.blockSignals(True)
            chk.setChecked(checked)
        finally:
            chk.blockSignals(False)

def _ui_log(ctrl, port: int, msg: str):
    try:
        ctrl.w.log.append(f"[{port}] {msg}")
        ctrl.w.log.ensureCursorVisible()
    except Exception:
        print(f"[{port}] {msg}")
# đặt gần các helper khác trong file (ví dụ sau _ui_log)
def _today_str() -> str:
    return time.strftime("%Y%m%d")

def _update_account_date_in_file(path: str, email: str, new_date: str) -> bool:
    """
    Cập nhật cột date (index=3) cho đúng email trong accounts.txt (định dạng 5 cột:
    email,pwd,server,date,status). Trả True nếu có thay đổi.
    """
    try:
        if not os.path.exists(path):
            return False
        with open(path, "r", encoding="utf-8") as f:
            lines = f.readlines()
    except Exception:
        return False

    changed = False
    out_lines = []
    for line in lines:
        raw = line.rstrip("\n")
        if not raw.strip():
            out_lines.append(line)
            continue
        parts = raw.split(",")
        # định dạng bạn đang dùng: email, pwd, server, date, status
        if len(parts) >= 5 and parts[0].strip() == email.strip():
            parts[3] = new_date  # update date
            out_lines.append(",".join(parts) + "\n")
            changed = True
        else:
            out_lines.append(line if line.endswith("\n") else line + "\n")

    if changed:
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.writelines(out_lines)
        except Exception:
            return False
    return changed

# ====== Đọc accounts.txt cho port ======
def _read_accounts_for(ctrl, port: int) -> List[List[str]]:
    path = ctrl.w.accounts_path_for_port(port)
    rows = read_accounts_5cols(path)
    # chỉ lấy những dòng status "1"/"true"
    rows = [r for r in rows if len(r) >= 5 and (r[4] == "1" or r[4].lower() == "true")]
    return rows

# ====== Wrapper ADB đơn giản cho flow ======
class SimpleNoxWorker:
    """Đủ method cho flows_logout/login sử dụng."""
    def __init__(self, adb_path: str, port: int, log_cb):
        self.port = port
        self._adb = adb_path
        self._serial = f"127.0.0.1:{port}"
        self.game_package = GAME_PKG
        self.game_activity = GAME_ACT
        self._log_cb = log_cb

    # --- log tiện ---
    def _log(self, s: str):
        self._log_cb(f"{s}")

    # --- ADB core ---
    def _run(self, args: List[str], timeout=8, text=True) -> Tuple[int, str, str]:
        import subprocess
        try:
            p = subprocess.run([self._adb, "-s", self._serial, *args],
                               capture_output=True, text=text, timeout=timeout)
            return p.returncode, p.stdout or "", p.stderr or ""
        except subprocess.TimeoutExpired:
            return 124, "", "timeout"
        except Exception as e:
            return 125, "", str(e)

    def _run_raw(self, args: List[str], timeout=8) -> Tuple[int, bytes, bytes]:
        import subprocess
        try:
            p = subprocess.run([self._adb, "-s", self._serial, *args],
                               capture_output=True, timeout=timeout)
            return p.returncode, p.stdout, p.stderr
        except subprocess.TimeoutExpired:
            return 124, b"", b"timeout"
        except Exception as e:
            return 125, b"", str(e).encode()

    # flows_* gọi những hàm tên này:
    def adb(self, *args, timeout=8):
        return self._run(list(args), timeout=timeout, text=True)

    def adb_bin(self, *args, timeout=8):
        return self._run_raw(list(args), timeout=timeout)

    # --- tiện khác cho flows_login ---
    def app_in_foreground(self, pkg: str) -> bool:
        code, out, _ = self.adb("shell", "cmd", "activity", "get-foreground-activity", timeout=6)
        if code == 0 and out and "ComponentInfo{" in out:
            comp = out.split("ComponentInfo{", 1)[1].split("}", 1)[0]
            return pkg in comp
        # fallback dumpsys
        code, out, _ = self.adb("shell", "dumpsys", "window", "windows", timeout=8)
        if code == 0 and out:
            for line in out.splitlines():
                if pkg in line and "/" in line:
                    return True
        return False

    def start_app(self, package: str, activity: Optional[str] = None) -> bool:
        if activity:
            code, _, _ = self.adb("shell", "am", "start", "-n", activity,
                                  "-a", "android.intent.action.MAIN",
                                  "-c", "android.intent.category.LAUNCHER", timeout=10)
            if code == 0:
                return True
        code, _, _ = self.adb("shell", "monkey", "-p", package, "-c", "android.intent.category.LAUNCHER", "1", timeout=10)
        return code == 0

    def wait_app_ready(self, pkg: str, timeout_sec: int = 35) -> bool:
        end = time.time() + timeout_sec
        while time.time() < end:
            if self.app_in_foreground(pkg):
                return True
            time.sleep(1.0)
        return False

# ====== Runner thread theo port ======
# ====== Runner thread theo port ======
class AccountRunner(threading.Thread):
    daemon = True

    def __init__(self, ctrl, port: int, adb_path: str, poll=1.0):
        super().__init__(name=f"AccountRunner-{port}")
        self.ctrl = ctrl
        self.port = port
        self.adb_path = adb_path
        self.poll = poll

        # cờ dừng vòng lặp runner (giữ nguyên)
        self._stop = threading.Event()
        self._last_log = None

        # worker ADB cho các flow
        self.wk = SimpleNoxWorker(adb_path, port, log_cb=lambda s: _ui_log(ctrl, port, s))

        # ===== NEW: cờ dừng hợp tác cho flow =====
        self.stop_evt = threading.Event()          # để runner biết người dùng yêu cầu dừng
        setattr(self.wk, "_abort", False)          # reset cờ hủy trong wk mỗi lần start

    # gọi khi người dùng BỎ check
    def request_stop(self):
        self.stop_evt.set()
        self._stop.set()                           # dừng vòng lặp runner
        setattr(self.wk, "_abort", True)           # báo các flow dừng hợp tác (login/logout/guild...)

    # sleep hợp tác — dùng nếu cần thay cho sleep dài ở runner
    def _sleep_coop(self, secs: float):
        step = 0.2
        n = int(max(1, secs / step))
        for _ in range(n):
            if self.stop_evt.is_set() or self._stop.is_set():
                return False
            time.sleep(step)
        return True

    def log(self, s: str):
        if s != self._last_log:
            self._last_log = s
            _ui_log(self.ctrl, self.port, s)

    def stop(self):
        # (giữ API cũ) — gọi từ nơi khác vẫn dừng runner, nhưng ưu tiên dùng request_stop()
        self.request_stop()

    def _ensure_device_online(self) -> bool:
        # get-state
        code, out, _ = self.wk.adb("get-state", timeout=3)
        if code == 0 and out.strip() == "device":
            return True
        # thử connect một nhịp
        import subprocess
        try:
            subprocess.run([self.adb_path, "connect", f"127.0.0.1:{self.port}"],
                           capture_output=True, text=True, timeout=5)
        except Exception:
            pass
        code, out, _ = self.wk.adb("get-state", timeout=3)
        return (code == 0 and out.strip() == "device")

    def _ensure_game_up(self) -> bool:
        if not self._ensure_device_online():
            self.log("ADB offline/port chưa sẵn sàng.")
            return False
        # mở game nếu chưa foreground
        if not self.wk.app_in_foreground(GAME_PKG):
            self.log("Mở game…")
            if not self.wk.start_app(GAME_PKG, GAME_ACT):
                self.log("Mở game thất bại.")
                return False
            self.wk.wait_app_ready(GAME_PKG, 35)
            time.sleep(2.0)
        return True

    def _iter_accounts(self) -> List[List[str]]:
        rows = _read_accounts_for(self.ctrl, self.port)
        return rows

    def _get_features(self) -> Dict[str, bool]:
        return dict(
            build=self.ctrl.w.chk_build.isChecked(),
            expedition=self.ctrl.w.chk_expedition.isChecked(),
            bless=self.ctrl.w.chk_bless.isChecked(),
            autoleave=self.ctrl.w.chk_auto_leave.isChecked(),
        )

    def run(self):
        self.log("Bắt đầu auto (vòng lặp theo tài khoản).")
        while not self._stop.is_set():
            # cho phép dừng ngay khi người dùng bỏ check
            if self.stop_evt.is_set():
                break

            # chỉ chạy khi trạng thái UI của port đang online
            row = _table_row_for_port(self.ctrl, self.port)
            if row < 0:
                time.sleep(self.poll); continue
            if _get_ui_state(self.ctrl, row) != "online":
                time.sleep(self.poll); continue

            if not self._ensure_game_up():
                time.sleep(self.poll); continue

            accounts = self._iter_accounts()
            if not accounts:
                self.log("Không có tài khoản (status=1).")
                if not self._sleep_coop(2.0): break
                continue

            feats = self._get_features()

            for email, pwd, server, date, _status in accounts:
                if self._stop.is_set() or self.stop_evt.is_set():
                    break

                self.log(f"Xử lý tài khoản: {email} / server={server} / date={date}")

                # 1) logout (đưa về form login)
                if self.stop_evt.is_set(): break
                ok_logout = logout_once(self.wk, max_rounds=7)
                if not ok_logout:
                    self.log("Logout thất bại, thử next account.")
                    continue

                # 2) login
                if self.stop_evt.is_set(): break
                ok_login = login_once(self.wk, email, pwd, server, date)
                self.log(f"Login {'OK' if ok_login else 'FAIL'}")
                if not ok_login:
                    continue

                # 3) tính năng theo checkbox
                try:
                    feats = self._get_features()
                except Exception:
                    pass

                # 3.1) Nếu có tick Build hoặc Expedition → gia nhập liên minh trước
                if (feats.get("build") or feats.get("expedition")) and not self.stop_evt.is_set():
                    self.log("[Liên minh] Bắt đầu gia nhập liên minh…")
                    join_guild_once(self.wk, log=self.log)

                # 3.2) Xây dựng liên minh / xem quảng cáo — chỉ chạy nếu CHƯA chạy trong ngày
                if feats.get("build") and not self.stop_evt.is_set():
                    accounts_path = self.ctrl.w.accounts_path_for_port(self.port)
                    today = _today_str()
                    # date đọc ở cột 4 (index 3) từ vòng for (email, pwd, server, date, status)
                    if str(date).strip() == today:
                        self.log(f"⏭️ Bỏ qua Xây dựng — tài khoản {email} đã chạy hôm nay ({today}).")
                    else:
                        self.log("Chạy tính năng: xay-dung/quang-cao")
                        ensure_guild_inside(self.wk, log=self.log)
                        res = run_guild_build_flow(self.wk, log=self.log)
                        # nếu flow trả False là thất bại; None/True coi là đã cố và hoàn tất
                        if res is False:
                            self.log(f"⚠️ Xây dựng thất bại cho {email} — KHÔNG cập nhật ngày.")
                        else:
                            if _update_account_date_in_file(accounts_path, email, today):
                                self.log(f"📝 Đã cập nhật ngày {today} cho {email} trong accounts.txt")
                            else:
                                self.log(f"⚠️ Không cập nhật được ngày cho {email} — kiểm tra accounts.txt")
                            # đồng bộ biến date trong vòng lặp hiện tại (để lần sau trong phiên vẫn hiểu là đã chạy)
                            date = today

                # 3.3) Viễn chinh (placeholder)
                if feats.get("expedition") and not self.stop_evt.is_set():
                    self.log("Chạy tính năng: vien-chinh")
                    ensure_guild_inside(self.wk, log=self.log)
                    # TODO: flows_vien_chinh(...)
                    run_guild_expedition_flow(self.wk, log=self.log)
                # 3.4) Chúc phúc (placeholder)
                if feats.get("bless") and not self.stop_evt.is_set():
                    self.log("Chạy tính năng: chuc-phuc")
                    # TODO: flows_chuc_phuc(...)

                # 3.5) Tự thoát liên minh (nếu bật)
                # ngay TRƯỚC khi logout
                if feats.get("autoleave") and not self.stop_evt.is_set():
                    self.log("Tự thoát liên minh sau khi thao tác xong…")
                    from flows_thoat_lien_minh import run_guild_leave_flow
                    run_guild_leave_flow(self.wk, log=self.log)

                # 4) xong account → logout để sẵn sàng cho tài khoản tiếp theo
                if self.stop_evt.is_set(): break
                logout_once(self.wk, max_rounds=7)

            if not self._sleep_coop(self.poll):
                break

        self.log("Kết thúc auto (đã dừng).")


# ====== API UI: gọi từ _hook_row_checkbox ======
def on_checkbox_toggled(ctrl, port: int, checked: bool):
    """
    ctrl: đối tượng điều khiển đã có .w (MainWindow)
    port: adb port
    checked: True = start, False = stop
    """
    row = _table_row_for_port(ctrl, port)
    if row < 0:
        return

    if checked:
        # chỉ start khi cột Trạng thái = "online"
        if _get_ui_state(ctrl, row) != "online":
            _ui_log(ctrl, port, "Máy ảo chưa được bật, vui lòng bật máy ảo.")
            _set_checkbox_state_silent(ctrl, row, False)
            return

        # đọc ADB path từ UI/main (bạn đã cấu hình ở đó)
        try:
            # ưu tiên ADB_PATH nếu bạn có biến đó public trong ui_main
            adb_path = str(getattr(ctrl.w, "ADB_PATH", r"D:\Program Files\Nox\bin\adb.exe"))
        except Exception:
            adb_path = r"D:\Program Files\Nox\bin\adb.exe"

        # nếu runner đang chạy thì bỏ qua
        r = _RUNNERS.get(port)
        if r and r.is_alive():
            _ui_log(ctrl, port, "Auto đang chạy.")
            return

        # kiểm tra có tài khoản chưa
        acc_rows = _read_accounts_for(ctrl, port)
        if not acc_rows:
            _ui_log(ctrl, port, "Không có tài khoản (status=1). Vui lòng thêm tài khoản.")
            _set_checkbox_state_silent(ctrl, row, False)
            return

        # start runner
        runner = AccountRunner(ctrl, port, adb_path, poll=1.0)
        _RUNNERS[port] = runner
        runner.start()
        _ui_log(ctrl, port, "Bắt đầu auto.")
    else:
        # stop runner
        r = _RUNNERS.get(port)
        if r:
            r.request_stop()
        _RUNNERS.pop(port, None)
        _ui_log(ctrl, port, "Kết thúc auto theo yêu cầu.")
