# checkbox_actions.py
# Start/Stop auto theo từng port khi tick/untick checkbox.
# Quy trình cho mỗi tài khoản: (có thể SKIP login theo bộ lọc) -> logout -> login -> (join nếu cần) -> build/expedition -> (autoleave nếu bật) -> logout.

from __future__ import annotations
import os
import time
import threading
from threading import Thread
from pathlib import Path
from typing import Dict, List, Tuple, Optional
from datetime import datetime, timedelta

# ====== Import các hàm/flow sẵn có ======
from ui_main import read_accounts_6cols       # Nâng từ 5 -> 6 cột, giữ cách đọc cũ
from flows_logout import logout_once
from flows_login import login_once
from flows_lien_minh import join_guild_once, ensure_guild_inside
from flows_thoat_lien_minh import run_guild_leave_flow
from flows_xay_dung_lien_minh import run_guild_build_flow
from flows_vien_chinh import run_guild_expedition_flow

# ====== Cấu hình game ======
GAME_PKG = "com.phsgdbz.vn"
GAME_ACT = "com.phsgdbz.vn/org.cocos2dx.javascript.GameTwActivity"

# ====== Quản lý runner theo port ======
_RUNNERS: Dict[int, "AccountRunner"] = {}

# ====== Tiện ích UI ======
def _table_row_for_port(ctrl, port: int) -> int:
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

# ====== Helpers: ngày/giờ & điều kiện ======
def _today_str() -> str:
    return time.strftime("%Y%m%d")

def _now_leave_str() -> str:
    # yyyymmdd:hhmm
    return time.strftime("%Y%m%d:%H%M")

def _parse_leave_str(s: str) -> Optional[datetime]:
    try:
        return datetime.strptime(s.strip(), "%Y%m%d:%H%M")
    except Exception:
        return None

def _leave_cooldown_passed(last_leave: str | None, minutes: int = 61) -> bool:
    """
    True nếu:
      - chưa có mốc rời, hoặc
      - đã qua >= minutes kể từ mốc rời.
    """
    if not last_leave:
        return True
    t = _parse_leave_str(last_leave)
    if not t:
        return True
    return (datetime.now() - t) >= timedelta(minutes=minutes)

# ====== Đọc accounts.txt cho port (bám cách cũ) ======
def _read_accounts_for(ctrl, port: int) -> List[List[str]]:
    """
    Trả về danh sách đã lọc status=1|true:
      [email, pwd, server, date, status, last_leave]
    KHÔNG chỉnh sửa file khi đọc.
    """
    path = ctrl.w.accounts_path_for_port(port)
    rows = read_accounts_6cols(path)  # giữ style cũ, chỉ khác sang 6 cột
    rows = [r for r in rows if len(r) >= 5 and (r[4] == "1" or str(r[4]).lower() == "true")]
    return rows

# ====== Ghi lại file: CHỈ sửa đúng dòng; giữ nguyên dòng khác (style cũ) ======
def _update_account_date_in_file(path: str, email: str, new_date: str) -> bool:
    """
    Update cột date (index=3). Không đụng dòng khác.
    Giữ nguyên số cột hiện có của dòng (5 hay 6), chỉ pad nếu thiếu.
    """
    try:
        if not os.path.exists(path):
            return False
        with open(path, "r", encoding="utf-8") as f:
            lines = f.readlines()  # giữ nguyên newline từng dòng
    except Exception:
        return False

    changed = False
    out_lines = []
    target = email.strip()

    for line in lines:
        raw = line.rstrip("\n")
        parts = [p.strip() for p in raw.split(",")] if raw else []
        if parts and parts[0] == target:
            while len(parts) < 5:
                parts.append("")
            parts[3] = new_date
            newline = "\n" if line.endswith("\n") else "\n"
            out_lines.append(",".join(parts) + newline)  # giữ nguyên số cột hiện có
            changed = True
        else:
            out_lines.append(line)

    if changed:
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.writelines(out_lines)
        except Exception:
            return False
    return changed

def _update_last_leave_in_file(path: str, email: str, leave_str: str) -> bool:
    """
    Update/append cột 6 (index=5) 'last_leave'.
    Nếu dòng đang 5 cột -> append cột 6; nếu đã >=6 cột -> ghi đè cột 6.
    Không đụng dòng khác.
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
    target = email.strip()

    for line in lines:
        raw = line.rstrip("\n")
        parts = [p.strip() for p in raw.split(",")] if raw else []
        if parts and parts[0] == target:
            while len(parts) < 5:
                parts.append("")
            if len(parts) < 6:
                parts.append(leave_str)
            else:
                parts[5] = leave_str
            newline = "\n" if line.endswith("\n") else "\n"
            out_lines.append(",".join(parts) + newline)
            changed = True
        else:
            out_lines.append(line)

    if changed:
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.writelines(out_lines)
        except Exception:
            return False
    return changed

# ====== Wrapper ADB cho flows_* ======
class SimpleNoxWorker:
    """Đủ method cho flows_login/logout sử dụng (giữ nguyên style cũ)."""
    def __init__(self, adb_path: str, port: int, log_cb):
        self.port = port
        self._adb = adb_path
        self._serial = f"127.0.0.1:{port}"
        self.game_package = GAME_PKG
        self.game_activity = GAME_ACT
        self._log_cb = log_cb

    def _log(self, s: str):
        self._log_cb(f"{s}")

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

    # flows_* dùng các tên này:
    def adb(self, *args, timeout=8):
        return self._run(list(args), timeout=timeout, text=True)

    def adb_bin(self, *args, timeout=8):
        return self._run_raw(list(args), timeout=timeout)

    # tiện khác cho flows_login
    def app_in_foreground(self, pkg: str) -> bool:
        code, out, _ = self.adb("shell", "cmd", "activity", "get-foreground-activity", timeout=6)
        if code == 0 and out and "ComponentInfo{" in out:
            comp = out.split("ComponentInfo{", 1)[1].split("}", 1)[0]
            return pkg in comp
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

# ====== Runner theo port ======
class AccountRunner(threading.Thread):
    daemon = True

    def __init__(self, ctrl, port: int, adb_path: str, poll=1.0):
        super().__init__(name=f"AccountRunner-{port}")
        self.ctrl = ctrl
        self.port = port
        self.adb_path = adb_path
        self.poll = poll

        self._stop = threading.Event()
        self._last_log = None

        self.wk = SimpleNoxWorker(adb_path, port, log_cb=lambda s: _ui_log(ctrl, port, s))

        # dừng mềm khi bỏ tick
        self.stop_evt = threading.Event()
        setattr(self.wk, "_abort", False)

    def request_stop(self):
        self.stop_evt.set()
        self._stop.set()
        setattr(self.wk, "_abort", True)

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

    def _ensure_device_online(self) -> bool:
        code, out, _ = self.wk.adb("get-state", timeout=3)
        if code == 0 and out.strip() == "device":
            return True
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
        if not self.wk.app_in_foreground(GAME_PKG):
            self.log("Mở game…")
            if not self.wk.start_app(GAME_PKG, GAME_ACT):
                self.log("Mở game thất bại.")
                return False
            self.wk.wait_app_ready(GAME_PKG, 35)
            time.sleep(2.0)
        return True

    def _read_accounts(self) -> List[List[str]]:
        return _read_accounts_for(self.ctrl, self.port)

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
            if self.stop_evt.is_set():
                break

            row = _table_row_for_port(self.ctrl, self.port)
            if row < 0:
                time.sleep(self.poll); continue
            if _get_ui_state(self.ctrl, row) != "online":
                time.sleep(self.poll); continue

            if not self._ensure_game_up():
                time.sleep(self.poll); continue

            accounts = self._read_accounts()
            if not accounts:
                self.log("Không có tài khoản (status=1).")
                if not self._sleep_coop(2.0): break
                continue

            feats = self._get_features()

            for rec in accounts:
                if self._stop.is_set() or self.stop_evt.is_set():
                    break

                # unpack 6 cột (giữ nguyên số phần tử nếu dòng đang 5 cột)
                email, pwd, server, date, _status = (rec + [""]*5)[:5]
                last_leave = rec[5] if len(rec) > 5 else ""

                self.log(f"Xử lý tài khoản: {email} / server={server} / date={date} / last_leave={last_leave}")

                # =======================
                # BỘ LỌC TRƯỚC-KHI-LOGIN
                # =======================
                feats = self._get_features()
                want_build = bool(feats.get("build"))
                want_expe  = bool(feats.get("expedition"))
                want_bless = bool(feats.get("bless"))
                want_autol = bool(feats.get("autoleave"))

                KNOWN_ALLOWED = {"build", "expedition", "autoleave", "bless"}
                other_selected = any(v for k, v in feats.items() if v and k not in KNOWN_ALLOWED)

                # chỉ nhóm Liên minh? (build/expedition/autoleave), KHÔNG có bless và KHÔNG có tính năng khác
                only_guild_related = ((want_build or want_expe or want_autol) and not want_bless and not other_selected)

                today = _today_str()
                cool_ok = _leave_cooldown_passed(last_leave, minutes=61)

                # ❶ Chỉ nhóm Liên minh & CHƯA đủ cooldown → khỏi login/logout
                if only_guild_related and not cool_ok:
                    self.log(f"⏭️ Bỏ qua tài khoản — chỉ chọn Xây dựng/Viễn chinh/Tự thoát và chưa đủ cooldown rời (last={last_leave}).")
                    continue

                # ❷ Chỉ Xây dựng (không Viễn chinh) & đã chạy hôm nay → khỏi login/logout
                if only_guild_related and want_build and (not want_expe) and str(date).strip() == today:
                    self.log(f"⏭️ Bỏ qua tài khoản — chỉ Xây dựng và đã xong hôm nay ({today}).")
                    continue

                # --- nếu tới đây mới thực sự cần làm → tiến hành như cũ ---

                # 1) logout để về form
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

                # 3) tính năng theo checkbox (sau login)
                try:
                    feats = self._get_features()
                except Exception:
                    pass

                want_build = bool(feats.get("build"))
                want_expe  = bool(feats.get("expedition"))

                accounts_path = self.ctrl.w.accounts_path_for_port(self.port)
                today = _today_str()

                # cooldown rời (1h1p) — đã check trước khi login, nhưng vẫn giữ cho an toàn
                cool_ok = _leave_cooldown_passed(last_leave, minutes=61)

                # cờ đánh dấu có thực sự thao tác trong liên minh ở tài khoản này không
                did_build = False
                did_expe  = False

                # 3.1) Gia nhập nếu cần và qua cooldown
                if (want_build or want_expe) and not self.stop_evt.is_set():
                    if not cool_ok:
                        self.log(f"⏭️ Bỏ qua Join/Build/Expedition — chưa đủ 1h1p sau khi rời (last={last_leave}).")
                    else:
                        self.log("[Liên minh] Bắt đầu gia nhập liên minh…")
                        join_guild_once(self.wk, log=self.log)

                # 3.2) Xây dựng liên minh — chỉ khi CHƯA chạy hôm nay & qua cooldown
                if want_build and not self.stop_evt.is_set():
                    if not cool_ok:
                        self.log("⏭️ Bỏ qua Xây dựng — chưa qua cooldown rời.")
                    elif str(date).strip() == today:
                        self.log(f"⏭️ Bỏ qua Xây dựng — tài khoản {email} đã chạy hôm nay ({today}).")
                    else:
                        self.log("Chạy tính năng: xay-dung/quang-cao")
                        ensure_guild_inside(self.wk, log=self.log)
                        res = run_guild_build_flow(self.wk, log=self.log)
                        if res is False:
                            self.log("⚠️ Xây dựng thất bại — KHÔNG cập nhật ngày.")
                        else:
                            did_build = True
                            if _update_account_date_in_file(str(accounts_path), email, today):
                                self.log(f"📝 Cập nhật ngày xây dựng: {today}")
                                date = today
                            else:
                                self.log("⚠️ Không cập nhật được ngày xây dựng — kiểm tra accounts.txt")

                # 3.3) Viễn chinh — không phụ thuộc ngày, nhưng phải qua cooldown
                if want_expe and not self.stop_evt.is_set():
                    if not cool_ok:
                        self.log("⏭️ Bỏ qua Viễn chinh — chưa qua cooldown rời.")
                    else:
                        self.log("Chạy tính năng: vien-chinh")
                        ensure_guild_inside(self.wk, log=self.log)
                        expe_ok = run_guild_expedition_flow(self.wk, log=self.log)
                        # coi như đã thao tác, kể cả khi flow trả False/None (đã vào UI)
                        did_expe = True

                # 3.4) Chúc phúc — placeholder (giữ nguyên)
                if feats.get("bless") and not self.stop_evt.is_set():
                    self.log("Chạy tính năng: chuc-phuc")
                    # TODO: flows_chuc_phuc(...)

                # 3.5) Tự thoát liên minh — CHỈ khi đã thao tác build/viễn chinh ở tài khoản này
                if feats.get("autoleave") and (did_build or did_expe) and not self.stop_evt.is_set():
                    self.log("Tự thoát liên minh sau khi thao tác xong…")
                    ok_leave = run_guild_leave_flow(self.wk, log=self.log)
                    if ok_leave:
                        leave_str = _now_leave_str()
                        if _update_last_leave_in_file(str(accounts_path), email, leave_str):
                            self.log(f"📝 Lưu mốc rời liên minh: {leave_str}")
                            last_leave = leave_str
                        else:
                            self.log("⚠️ Không cập nhật được mốc rời — kiểm tra accounts.txt")
                elif feats.get("autoleave") and not (did_build or did_expe):
                    self.log("⏭️ Bỏ qua Tự thoát liên minh — tài khoản này không chạy build/viễn chinh.")

                # 4) logout để sẵn sàng cho tài khoản tiếp theo
                if self.stop_evt.is_set(): break
                logout_once(self.wk, max_rounds=7)

            if not self._sleep_coop(self.poll):
                break

        self.log("Kết thúc auto (đã dừng).")

# ====== API cho UI: gọi khi tick/untick ======
def on_checkbox_toggled(ctrl, port: int, checked: bool):
    row = _table_row_for_port(ctrl, port)
    if row < 0:
        return

    if checked:
        # chỉ start khi trạng thái online
        if _get_ui_state(ctrl, row) != "online":
            _ui_log(ctrl, port, "Máy ảo chưa được bật, vui lòng bật máy ảo.")
            _set_checkbox_state_silent(ctrl, row, False)
            return

        # adb path từ UI (bạn đã set trong ui_main.py)
        try:
            adb_path = str(getattr(ctrl.w, "ADB_PATH", r"D:\Program Files\Nox\bin\adb.exe"))
        except Exception:
            adb_path = r"D:\Program Files\Nox\bin\adb.exe"

        # đang chạy thì bỏ qua
        r = _RUNNERS.get(port)
        if r and r.is_alive():
            _ui_log(ctrl, port, "Auto đang chạy.")
            return

        # có accounts?
        acc_rows = _read_accounts_for(ctrl, port)
        if not acc_rows:
            _ui_log(ctrl, port, "Không có tài khoản (status=1). Vui lòng thêm tài khoản.")
            _set_checkbox_state_silent(ctrl, row, False)
            return

        runner = AccountRunner(ctrl, port, adb_path, poll=1.0)
        _RUNNERS[port] = runner
        runner.start()
        _ui_log(ctrl, port, "Bắt đầu auto.")
    else:
        r = _RUNNERS.get(port)
        if r:
            r.request_stop()
        _RUNNERS.pop(port, None)
        _ui_log(ctrl, port, "Kết thúc auto theo yêu cầu.")
