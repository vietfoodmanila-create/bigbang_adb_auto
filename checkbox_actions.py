# checkbox_actions.py
# Auto runner cho từng port Nox: (có thể SKIP login theo bộ lọc) -> logout -> login -> (join nếu cần) -> build/expedition -> (autoleave nếu bật) -> logout
from __future__ import annotations
import os, time, threading, json, re
from threading import Thread
from pathlib import Path
from typing import Dict, List, Tuple, Optional
from datetime import datetime, timedelta

# ====== Import các hàm/flow sẵn có ======
from ui_main import read_accounts_8cols
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
        if not it: continue
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

def _now_time_str() -> str:
    return time.strftime("%Y%m%d:%H%M")  # yyyymmdd:hhmm

def _parse_time_str(s: str) -> Optional[datetime]:
    try:
        return datetime.strptime(s.strip(), "%Y%m%d:%H%M")
    except Exception:
        return None

def _leave_cooldown_passed(last_leave: str | None, minutes: int = 61) -> bool:
    if not last_leave:
        return True
    t = _parse_time_str(last_leave)
    if not t:
        return True
    return (datetime.now() - t) >= timedelta(minutes=minutes)

def _expe_cooldown_passed(last_expe: str | None, hours: int = 12) -> bool:
    if not last_expe:
        return True
    t = _parse_time_str(last_expe)
    if not t:
        return True
    return (datetime.now() - t) >= timedelta(hours=hours)

# ====== Đọc/Ghi accounts.txt (mở rộng 8 cột) ======
def _read_accounts_for(ctrl, port: int) -> List[List[str]]:
    """
    Trả về danh sách đã lọc status=1|true:
      [email, pwd, server, date, status, last_leave, vienchinh, chucphuc]
    """
    path = ctrl.w.accounts_path_for_port(port)
    rows = read_accounts_8cols(str(path))
    rows = [list(r) for r in rows if len(r) >= 5 and (r[4] == "1" or str(r[4]).lower() == "true")]
    return rows

def _update_account_date_in_file(path: str, email: str, new_date: str) -> bool:
    """Update cột date (index=3) đúng dòng email; giữ nguyên các dòng khác."""
    try:
        if not os.path.exists(path): return False
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
            while len(parts) < 8:
                parts.append("")
            parts[3] = new_date
            out_lines.append(",".join(parts) + ("\n" if line.endswith("\n") else "\n"))
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

def _bless_cfg_path(ctrl, port: int) -> Path:
    try:
        if hasattr(ctrl.w, "chucphuc_path_for_port"):
            return Path(ctrl.w.chucphuc_path_for_port(port))
    except Exception:
        pass
    return Path("data") / str(port) / "chucphuc.txt"

def _update_last_leave_in_file(path: str, email: str, leave_str: str) -> bool:
    """Update/append cột 6 (index=5) 'last_leave' cho đúng dòng email."""
    try:
        if not os.path.exists(path): return False
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
            while len(parts) < 8:
                parts.append("")
            parts[5] = leave_str
            out_lines.append(",".join(parts) + ("\n" if line.endswith("\n") else "\n"))
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

def _prune_bless_history(obj: dict, keep_days: int = 1, today: Optional[str] = None) -> None:
    """
    Giữ lại các entry blessed của 'today' và (tùy chọn) một số ngày gần nhất (keep_days).
    Mặc định keep_days=1 => chỉ còn NGÀY HÔM NAY. Chỉ mutate 'obj' tại chỗ.
    """
    if today is None:
        today = _today_str()
    items = obj.get("items") or []
    for it in items:
        blessed = it.get("blessed")
        if not isinstance(blessed, dict):
            it["blessed"] = {}
            continue

        # Lấy các key dạng yyyymmdd hợp lệ & sắp xếp
        keys = [k for k in blessed.keys() if re.fullmatch(r"\d{8}", str(k or ""))]
        keys.sort()
        keep = set()

        # Giữ lại 'today'
        if today in blessed:
            keep.add(today)

        # Giữ lại N-1 ngày gần nhất (nếu muốn). Với keep_days=1 thì đoạn này giữ 0 ngày cũ.
        if keep_days > 1 and keys:
            tail = keys[-keep_days:]  # ví dụ keep_days=3 => giữ 3 ngày cuối
            keep.update(tail)

        # Lọc lại dict
        it["blessed"] = {k: blessed[k] for k in keep if k in blessed}

def _update_last_expedition_in_file(path: str, email: str, expe_str: str) -> bool:
    """Update/append cột 7 (index=6) 'vienchinh' cho đúng dòng email."""
    try:
        if not os.path.exists(path): return False
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
            while len(parts) < 8:
                parts.append("")
            parts[6] = expe_str
            out_lines.append(",".join(parts) + ("\n" if line.endswith("\n") else "\n"))
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
    def __init__(self, adb_path: str, port: int, log_cb):
        self.port = port
        self._adb = adb_path
        self._serial = f"127.0.0.1:{port}"
        self.game_package = GAME_PKG
        self.game_activity = GAME_ACT
        self._log_cb = log_cb

    def _log(self, s: str):
        self._log_cb(f"{s}")

    def _run(self, args: List[str], timeout=8, text=True):
        import subprocess
        try:
            p = subprocess.run([self._adb, "-s", self._serial, *args],
                               capture_output=True, text=text, timeout=timeout)
            return p.returncode, p.stdout or "", p.stderr or ""
        except subprocess.TimeoutExpired:
            return 124, "", "timeout"
        except Exception as e:
            return 125, "", str(e)

    def _run_raw(self, args: List[str], timeout=8):
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
            if code == 0: return True
        code, _, _ = self.adb("shell", "monkey", "-p", package, "-c", "android.intent.category.LAUNCHER", "1", timeout=10)
        return code == 0

    def wait_app_ready(self, pkg: str, timeout_sec: int = 35) -> bool:
        end = time.time() + timeout_sec
        while time.time() < end:
            if self.app_in_foreground(pkg):
                return True
            time.sleep(1.0)
        return False


def _read_bless_json(ctrl, port: int) -> dict:
    p = _bless_cfg_path(ctrl, port)
    try:
        if p.exists():
            txt = p.read_text(encoding="utf-8").strip()
            if txt:
                obj = json.loads(txt)
                if isinstance(obj, dict):
                    obj.setdefault("cooldown_hours", 0)
                    obj.setdefault("per_run", 0)
                    obj.setdefault("items", [])
                    return obj
    except Exception:
        pass
    return {"cooldown_hours": 0, "per_run": 0, "items": []}


def _write_bless_json(ctrl, port: int, obj: dict) -> None:
    p = _bless_cfg_path(ctrl, port)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


def _add_email_blessed_today(obj: dict, target_name: str, day: str, email: str):
    for it in obj.get("items", []):
        if str(it.get("name", "")).strip().lower() == target_name.strip().lower():
            blessed = it.setdefault("blessed", {})
            lst = blessed.setdefault(day, [])
            if email not in lst:
                lst.append(email)
            return


def _set_target_last_now(obj: dict, target_name: str, now_h: str):
    for it in obj.get("items", []):
        if str(it.get("name", "")).strip().lower() == target_name.strip().lower():
            it["last"] = now_h
            return


def _parse_bless_counter(s: str) -> tuple[str, int]:
    if not s:
        return ("", 0)
    m = re.fullmatch(r"(\d{8}):(\d{1,2})", s.strip())
    if not m:
        return ("", 0)
    return (m.group(1), int(m.group(2)))


def _format_bless_counter(day: str, cnt: int) -> str:
    return f"{day}:{cnt}"

# === PREF-PLANNER cho chúc phúc: ưu tiên tài khoản sẽ đăng nhập vì Build/Expedition ===
def _plan_bless_assignments_prefer_busy_accounts(
    ctrl,
    port: int,
    accounts8: List[tuple],
    will_login_emails: List[str],
    *,
    allow_extra_logins_if_busy: bool = False,  # False = KHÔNG đăng nhập thêm chỉ để bless nếu đã có build/expedition
) -> Dict[str, List[str]]:
    """
    Trả về dict {email: [target_name, ...]}.
    - Ưu tiên phân bổ cho các email có trong will_login_emails (các tk sẽ đăng nhập vì build/expedition).
    - Mỗi account tối đa 20 lần/ngày (cột 8 yyyymmdd:int). Nếu sang ngày mới thì reset.
    - Một account chỉ chúc 1 target <= 1 lần trong ngày (không trùng blessed[today]).
    - per_run: số lượt chúc mỗi lần / target (lấy từ chucphuc.txt). Nếu 0 thì không lập kế hoạch.
    - cooldown_hours: chỉ lập kế hoạch cho target đã hết cooldown theo trường 'last' (yyyymmdd:hh).

    Nếu allow_extra_logins_if_busy=False:
      - Khi có tài khoản sẽ đăng nhập vì build/expedition, chỉ dùng đúng các tài khoản đó cho bless (có thể thiếu so với per_run).
    Nếu True:
      - Sau khi phân bổ cho will_login_emails, nếu còn thiếu mới rót sang các account hợp lệ khác.
    """
    from datetime import datetime, timedelta

    # Đọc cấu hình bless + dọn lịch sử cũ
    cfg = _read_bless_json(ctrl, port)
    _prune_bless_history(cfg, keep_days=1, today=_today_str())

    per_run = int(cfg.get("per_run") or 0)
    cooldown_h = int(cfg.get("cooldown_hours") or 0)
    items = cfg.get("items") or []
    if per_run <= 0 or not items:
        return {}

    # Lọc target đến hạn (hết cooldown)
    now = datetime.now()
    def _cool_ok(last_str: str) -> bool:
        if cooldown_h <= 0:
            return True
        try:
            dt = datetime.strptime(str(last_str or ""), "%Y%m%d:%H")
            return (now - dt) >= timedelta(hours=cooldown_h)
        except Exception:
            # nếu không có 'last' hợp lệ → coi như đến hạn
            return True

    targets_due = []
    blessed_today_map: Dict[str, set] = {}
    today = _today_str()
    for it in items:
        name = str(it.get("name", "")).strip()
        if not name:
            continue
        if not _cool_ok(it.get("last", "")):
            continue
        # danh sách email đã bless tên này hôm nay
        blessed_today = set((it.get("blessed") or {}).get(today, []) or [])
        blessed_today_map[name.lower()] = blessed_today
        # mỗi target cần per_run account cho lần chạy này
        targets_due.append(name)

    if not targets_due:
        return {}

    # Năng lực mỗi account hôm nay
    cap: Dict[str, int] = {}  # email -> remaining bless today (<=20)
    active_emails: List[str] = []
    for r in accounts8:
        email = str(r[0]).strip()
        status = str(r[4]).strip()
        if not email or status != "1":
            continue
        d, c = _parse_bless_counter(r[7] if len(r) > 7 else "")
        left = 20 - (c if d == today else 0)
        if left <= 0:
            continue
        cap[email] = left
        active_emails.append(email)

    if not cap:
        return {}

    # Thứ tự ưu tiên: các email sẽ đăng nhập vì build/expedition → còn lại
    pref = [e for e in will_login_emails if e in cap]
    others = [e for e in active_emails if (e not in pref)]
    order_full = pref + (others if allow_extra_logins_if_busy or not pref else [])

    # Phân bổ: vòng qua từng target, rót cho các account trong order_full
    plan: Dict[str, List[str]] = {}
    # để đảm bảo 1 email không bless cùng 1 tên nhiều lần trong cùng lần chạy
    assigned_for_target: Dict[str, set] = {}

    for name in targets_due:
        want = per_run
        name_key = name.lower()
        already = blessed_today_map.get(name_key, set())
        assigned_for_target[name_key] = set()
        if want <= 0:
            continue

        for email in order_full:
            if want <= 0:
                break
            if cap.get(email, 0) <= 0:
                continue
            if email in already:
                continue
            if email in assigned_for_target[name_key]:
                continue

            # cấp 1 lượt bless cho target 'name' bởi 'email'
            plan.setdefault(email, []).append(name)
            cap[email] -= 1
            assigned_for_target[name_key].add(email)
            want -= 1

        # Nếu còn thiếu nhưng đang có build/expedition (pref != []), và không cho phép extra → chấp nhận thiếu.
        # Nếu không có build/expedition (pref rỗng) → đã bao gồm 'others' rồi (order_full = others).

    return plan

def _update_bless_counter_in_file(path: str, email: str, day: str, delta: int = 1):
    try:
        if not os.path.exists(path): return False
        with open(path, "r", encoding="utf-8") as f:
            lines = f.readlines()
        out = []
        changed = False
        for line in lines:
            raw = line.rstrip("\n")
            parts = [p.strip() for p in raw.split(",")] if raw else []
            if parts and parts[0].strip().lower() == email.strip().lower():
                while len(parts) < 8:
                    parts.append("")
                d, c = _parse_bless_counter(parts[7])
                if d != day:
                    c = 0
                c = min(20, max(0, c + delta))
                parts[7] = _format_bless_counter(day, c)
                out.append(",".join(parts) + ("\n" if line.endswith("\n") else "\n"))
                changed = True
            else:
                out.append(line)
        if changed:
            with open(path, "w", encoding="utf-8") as f:
                f.writelines(out)
        return changed
    except Exception:
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

        # cache accounts + mtime
        self._acc_mtime = None
        self._cached_accounts: List[List[str]] = []

        # ===== NEW: kế hoạch chúc phúc cho vòng chạy =====
        self._bless_plan: Dict[str, List[str]] = {}

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

    # ====== accounts cache + reload-on-change theo mtime ======
    def _maybe_reload_accounts(self):
        path = self.ctrl.w.accounts_path_for_port(self.port)
        m = os.path.getmtime(path) if os.path.exists(path) else 0
        if self._acc_mtime is None or self._acc_mtime != m:
            rows = _read_accounts_for(self.ctrl, self.port)
            self._cached_accounts = rows
            self._acc_mtime = m

    def _get_accounts_cached(self) -> List[List[str]]:
        self._maybe_reload_accounts()
        return self._cached_accounts or []

    # ====== tiện ích khác ======
    def _ensure_device_online(self) -> bool:
        code, out, _ = self.wk.adb("get-state", timeout=3)
        if code == 0 and out.strip() == "device": return True
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

    def _get_features(self) -> Dict[str, bool]:
        return dict(
            build=self.ctrl.w.chk_build.isChecked(),
            expedition=self.ctrl.w.chk_expedition.isChecked(),
            bless=self.ctrl.w.chk_bless.isChecked(),
            autoleave=self.ctrl.w.chk_auto_leave.isChecked(),
        )

    # ===================== BLESS (kế hoạch) =====================
    def _bless_cfg_path(self) -> Path:
        """Thư mục data/{port}/chucphuc.txt (JSON). Nếu UI có helper thì dùng helper."""
        try:
            if hasattr(self.ctrl.w, "chucphuc_path_for_port"):
                return Path(self.ctrl.w.chucphuc_path_for_port(self.port))
        except Exception:
            pass
        return Path("data") / str(self.port) / "chucphuc.txt"

    def _load_bless_cfg(self) -> dict:
        """
        Định dạng JSON gợi ý:
        {
          "cooldown_hours": 8,
          "per_run": 3,
          "items": [
            {"name":"NV1", "last":"20250813:09", "blessed":{"20250813":["a@x.com","b@y.com"]}}
          ]
        }
        """
        p = self._bless_cfg_path()
        try:
            if p.exists():
                s = p.read_text(encoding="utf-8").strip()
                if s:
                    return json.loads(s)
        except Exception as e:
            self.log(f"[bless] Không đọc được cấu hình: {e}")
        return {"cooldown_hours": 0, "per_run": 0, "items": []}

    def _parse_daily_counter(self, s: str) -> tuple[str,int]:
        """
        Trường cột 8 (index 7) trong accounts: 'yyyymmdd:int'
        Trả (day, count); sai định dạng -> ('', 0)
        """
        if not s: return ("", 0)
        s = s.strip()
        if ":" not in s: return ("", 0)
        day, cnt = s.split(":", 1)
        try:
            return (day.strip(), int(cnt.strip()))
        except Exception:
            return (day.strip(), 0)

    def _parse_last_hh(self, s: str) -> Optional[datetime]:
        if not s: return None
        try:
            return datetime.strptime(s.strip(), "%Y%m%d:%H")
        except Exception:
            return None

    def _due_targets(self, cfg: dict) -> list[dict]:
        items = cfg.get("items") or []
        cd = int(cfg.get("cooldown_hours") or 0)
        cd = max(0, cd)
        now = datetime.now()
        due = []
        for it in items:
            last = self._parse_last_hh(str(it.get("last","")))
            if (last is None) or ((now - last) >= timedelta(hours=cd)):
                due.append(it)
        return due

    def _plan_bless_assignments(self, accounts: List[List[str]]) -> tuple[set[str], dict]:
        """
        Lập kế hoạch:
          - Chỉ các 'target' tới hạn (qua cooldown).
          - Mỗi target lấy tối đa 'per_run' email khác nhau.
          - Mỗi email có sức chứa: 20 - số lần đã chúc phúc hôm nay (theo cột 8).
          - Không chọn email đã chúc phúc target đó trong hôm nay (dựa vào blessed[today]).
        Trả:
          - emails_need_bless: set các email cần đăng nhập để chúc phúc
          - plan: {email: [target_name, ...]}
        """
        cfg = self._load_bless_cfg()
        _prune_bless_history(cfg, keep_days=1, today=_today_str())
        per_run = int(cfg.get("per_run") or 0)
        if per_run <= 0:
            return set(), {}

        due_items = self._due_targets(cfg)
        if not due_items:
            return set(), {}

        today = _today_str()

        # capacity từ accounts
        cap: Dict[str,int] = {}
        for rec in accounts:
            email = (rec[0] if len(rec)>0 else "").strip()
            dcnt   = (rec[7] if len(rec)>7 else "").strip()
            d, c = self._parse_daily_counter(dcnt)
            used_today = c if d == today else 0
            remain = max(0, 20 - used_today)
            if email:
                cap[email] = remain

        plan: Dict[str, List[str]] = {}

        for it in due_items:
            name = str(it.get("name","")).strip()
            if not name:
                continue
            blessed = it.get("blessed") or {}
            already = set([str(x).strip() for x in blessed.get(today, [])])
            need = per_run

            # chọn theo thứ tự của accounts
            for rec in accounts:
                if need <= 0:
                    break
                email = (rec[0] if len(rec)>0 else "").strip()
                if not email:
                    continue
                if email in already:
                    continue
                if cap.get(email,0) <= 0:
                    continue
                # gán
                plan.setdefault(email, []).append(name)
                cap[email] = cap[email] - 1
                need -= 1

        emails_need = set([e for e, targets in plan.items() if targets])
        return emails_need, plan

    # ===================== Lọc tài khoản (giữ nguyên + bổ sung bless) =====================
    def _is_account_eligible(self, rec: List[str]) -> Tuple[bool, str]:
        """
        Giữ nguyên tiêu chí lọc như trong BỘ LỌC TRƯỚC-KHI-LOGIN cũ.
        Trả (eligible, reason) — reason chỉ dùng log khi cần.
        """
        email, pwd, server, date, _status = (rec + [""]*8)[:5]
        last_leave  = rec[5] if len(rec) > 5 else ""
        last_expe   = rec[6] if len(rec) > 6 else ""
        # chucphuc    = rec[7] if len(rec) > 7 else ""

        feats = self._get_features()
        want_build = bool(feats.get("build"))
        want_expe  = bool(feats.get("expedition"))
        want_bless = bool(feats.get("bless"))

        KNOWN_ALLOWED = {"build", "expedition", "autoleave", "bless"}
        other_selected = any(v for k, v in feats.items() if v and k not in KNOWN_ALLOWED)
        only_guild_related = ((want_build or want_expe) and not want_bless and not other_selected)

        today   = _today_str()
        cool_ok = _leave_cooldown_passed(last_leave, minutes=61)
        build_due = want_build and (str(date).strip() != today)
        expe_due  = want_expe and _expe_cooldown_passed(last_expe, hours=12)

        if only_guild_related:
            if not cool_ok:
                return (False, f"chưa đủ cooldown rời (last={last_leave})")
            if (not build_due) and (not expe_due):
                return (False, "không có tác vụ Liên minh nào đến hạn (build đã làm hôm nay / expe <12h)")
        # Nếu có bless hoặc 'khác', vẫn coi là hợp lệ ở bước này,
        # bước _scan_eligible_accounts sẽ khống chế thêm theo danh sách assignment bless.
        return (True, "")

    def _scan_eligible_accounts(self, accounts: List[List[str]]) -> List[List[str]]:
        """
        Quét trước:
          - Lọc như hiện tại.
          - Nếu bật bless: lập kế hoạch bless và CHỈ đưa vào danh sách các account có assignment bless
            khi account đó KHÔNG có build/expe đến hạn (tránh login thừa).
          - Ưu tiên phân bổ bless cho chính các account sẽ login vì build/expe.
          - Lưu self._bless_plan để dùng khi chạy.
        """
        feats = self._get_features()
        want_build = bool(feats.get("build"))
        want_expe  = bool(feats.get("expedition"))
        want_bless = bool(feats.get("bless"))

        bless_emails: set[str] = set()
        bless_plan: Dict[str, List[str]] = {}

        # Tính trước danh sách email sẽ CHẮC CHẮN login vì build/expe (đến hạn & qua cooldown)
        today = _today_str()
        will_login_emails: List[str] = []
        for rec in accounts:
            email = (rec[0] if len(rec)>0 else "").strip()
            if not email:
                continue
            date = (rec[3] if len(rec)>3 else "").strip()
            last_leave = (rec[5] if len(rec)>5 else "").strip()
            last_expe  = (rec[6] if len(rec)>6 else "").strip()
            cool_ok  = _leave_cooldown_passed(last_leave, minutes=61)
            build_due = want_build and (str(date).strip() != today) and cool_ok
            expe_due  = want_expe  and _expe_cooldown_passed(last_expe, hours=12) and cool_ok
            if build_due or expe_due:
                will_login_emails.append(email)
        # giữ nguyên thứ tự & unique
        will_login_emails = list(dict.fromkeys(will_login_emails))

        if want_bless:
            # ƯU TIÊN dùng chính các account sẽ login vì build/expe; KHÔNG login thêm chỉ để bless
            bless_plan = _plan_bless_assignments_prefer_busy_accounts(
                self.ctrl, self.port, accounts, will_login_emails,
                allow_extra_logins_if_busy=False
            )
            self._bless_plan = bless_plan
            bless_emails = set(bless_plan.keys())
            # Log tóm tắt kế hoạch
            if bless_plan:
                total_pairs = sum(len(v) for v in bless_plan.values())
                self.log(f"[Bless] Dự kiến (ưu tiên account bận): {len(bless_plan)} account, {total_pairs} lượt.")
            else:
                self.log("[Bless] Không có target tới hạn hoặc per_run=0.")
        else:
            self._bless_plan = {}

        eligible: List[List[str]] = []

        for rec in accounts:
            ok, _ = self._is_account_eligible(rec)
            if not ok:
                continue

            email = (rec[0] if len(rec)>0 else "").strip()
            date  = (rec[3] if len(rec)>3 else "").strip()
            last_leave = (rec[5] if len(rec)>5 else "").strip()
            last_expe  = (rec[6] if len(rec)>6 else "").strip()

            cool_ok  = _leave_cooldown_passed(last_leave, minutes=61)
            build_due = want_build and (str(date).strip() != today) and cool_ok
            expe_due  = want_expe  and _expe_cooldown_passed(last_expe, hours=12) and cool_ok

            if build_due or expe_due:
                eligible.append(rec)
                continue

            # Nếu chỉ còn lý do "bless": chỉ chọn account có assignment bless
            if want_bless and email in bless_emails:
                eligible.append(rec)
                continue

            # khác: bỏ qua để tránh login thừa
        return eligible

    def _auto_stop_and_uncheck(self, msg: str):
        """Bỏ tick checkbox + dừng runner + log thông báo."""
        row = _table_row_for_port(self.ctrl, self.port)
        # Cập nhật checkbox (không phát signal), rồi gọi hàm toggle để dừng runner
        if row >= 0:
            try:
                # Hiển thị bỏ tick trên UI
                _set_checkbox_state_silent(self.ctrl, row, False)
            except Exception:
                pass
        self.log(msg)
        # Yêu cầu dừng thread (phòng khi UI không bắt sự kiện)
        self.request_stop()

    def run(self):
        self.log("Bắt đầu auto (quét trước danh sách đủ điều kiện).")

        # Vòng lớn: quét → chạy danh sách hợp lệ → quét lại… đến khi không còn tài khoản hợp lệ
        round_no = 0
        while not self._stop.is_set() and not self.stop_evt.is_set():
            round_no += 1

            # 1) lấy & reload danh sách
            self._maybe_reload_accounts()
            all_accounts = self._get_accounts_cached()

            if not all_accounts:
                if not self._sleep_coop(self.poll): break
                continue

            # 2) quét lọc trước (có lập kế hoạch bless ưu tiên account bận)
            eligible = self._scan_eligible_accounts(all_accounts)
            self.log(f"[Round {round_no}] Tài khoản hợp lệ: {len(eligible)}/{len(all_accounts)}")

            # 3) nếu không còn tài khoản hợp lệ → bỏ tick & kết thúc
            if not eligible:
                self._auto_stop_and_uncheck("✅ Tất cả tài khoản đã xử lý hoàn tất. Kết thúc auto.")
                break

            # 4) duyệt danh sách hợp lệ và xử lý
            for rec in eligible:
                if self._stop.is_set() or self.stop_evt.is_set():
                    break

                # UI/Device state
                row = _table_row_for_port(self.ctrl, self.port)
                if row < 0 or _get_ui_state(self.ctrl, row) != "online":
                    if not self._sleep_coop(self.poll): break
                    continue
                if not self._ensure_game_up():
                    if not self._sleep_coop(self.poll): break
                    continue

                email, pwd, server, date, _status = (rec + [""]*8)[:5]
                last_leave  = rec[5] if len(rec) > 5 else ""
                last_expe   = rec[6] if len(rec) > 6 else ""
                chucphuc    = rec[7] if len(rec) > 7 else ""

                time.sleep(2.5)
                self.log(f"Xử lý tài khoản: {email} / server={server} / date={date} / last_leave={last_leave} / last_expe={last_expe}")

                # ====== BỘ LỌC TRƯỚC-KHI-LOGIN (giữ nguyên để an toàn) ======
                feats = self._get_features()
                want_build = bool(feats.get("build"))
                want_expe  = bool(feats.get("expedition"))
                want_bless = bool(feats.get("bless"))
                want_autol = bool(feats.get("autoleave"))

                KNOWN_ALLOWED = {"build", "expedition", "autoleave", "bless"}
                other_selected = any(v for k, v in feats.items() if v and k not in KNOWN_ALLOWED)
                only_guild_related = ((want_build or want_expe) and not want_bless and not other_selected)

                today   = _today_str()
                cool_ok = _leave_cooldown_passed(last_leave, minutes=61)
                build_due = want_build and (str(date).strip() != today)
                expe_due  = want_expe and _expe_cooldown_passed(last_expe, hours=12)

                if only_guild_related:
                    if not cool_ok:
                        self.log(f"⏭️ Bỏ qua — chỉ nhóm Liên minh và chưa đủ cooldown rời (last={last_leave}).")
                        continue
                    if (not build_due) and (not expe_due):
                        self.log("⏭️ Bỏ qua — không có tác vụ Liên minh nào đến hạn (build đã làm hôm nay / expe <12h).")
                        continue

                # ===== NEW: nếu không có build/expe đến hạn, chỉ chạy khi có assignment bless =====
                bless_targets_assigned = self._bless_plan.get(email, []) if want_bless else []
                if not ( (build_due and cool_ok) or (expe_due and cool_ok) or bless_targets_assigned ):
                    self.log("⏭️ Bỏ qua — không đến hạn build/expe và không có assignment bless.")
                    continue

                if self.stop_evt.is_set(): break

                # 1) logout để về form
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
                feats = self._get_features()
                want_build = bool(feats.get("build"))
                want_expe  = bool(feats.get("expedition"))

                accounts_path = self.ctrl.w.accounts_path_for_port(self.port)
                today = _today_str()
                cool_ok = _leave_cooldown_passed(last_leave, minutes=61)

                did_build = False
                did_expe  = False

                # 3.1) Gia nhập liên minh CHỈ khi có ÍT NHẤT một tác vụ build/expe đến hạn
                if (want_build or want_expe) and not self.stop_evt.is_set():
                    build_due_now = want_build and (str(date).strip() != today)
                    expe_due_now  = want_expe and _expe_cooldown_passed(last_expe, hours=12)
                    if build_due_now or expe_due_now:
                        if not cool_ok:
                            self.log(f"⏭️ Bỏ qua Join/Build/Expedition — chưa đủ 1h1p sau khi rời (last={last_leave}).")
                        else:
                            self.log("[Liên minh] Bắt đầu gia nhập liên minh…")
                            join_guild_once(self.wk, log=self.log)
                    else:
                        self.log("[Liên minh] Bỏ qua gia nhập — không có tác vụ build/viễn chinh đến hạn cho tài khoản này.")

                # 3.2) Xây dựng liên minh
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

                # 3.3) Viễn chinh (thêm kiểm tra 12h)
                if want_expe and not self.stop_evt.is_set():
                    if not cool_ok:
                        self.log("⏭️ Bỏ qua Viễn chinh — chưa qua cooldown rời.")
                    elif not _expe_cooldown_passed(last_expe, hours=12):
                        self.log(f"⏭️ Bỏ qua Viễn chinh — chưa đủ 12 giờ từ lần gần nhất (last_expe={last_expe}).")
                    else:
                        self.log("Chạy tính năng: vien-chinh")
                        ensure_guild_inside(self.wk, log=self.log)
                        expe_ok = run_guild_expedition_flow(self.wk, log=self.log)
                        did_expe = bool(expe_ok)
                        if expe_ok:
                            expe_str = _now_time_str()
                            if _update_last_expedition_in_file(str(accounts_path), email, expe_str):
                                self.log(f"📝 Lưu mốc hoàn thành Viễn chinh: {expe_str}")
                                last_expe = expe_str
                            else:
                                self.log("⚠️ Không cập nhật được mốc Viễn chinh — kiểm tra accounts.txt")

                # 3.4) Chúc phúc — placeholder (dựa trên kế hoạch đã lập ở pre-scan)
                if feats.get("bless") and not self.stop_evt.is_set():
                    from flows_chuc_phuc import run_bless_flow
                    targets = self._bless_plan.get(email, [])
                    if targets:
                        self.log(f"Chạy tính năng: chuc-phuc → targets={targets}")
                        blessed_ok = run_bless_flow(self.wk, targets, log=self.log)
                        if blessed_ok:
                            # cập nhật JSON chucphuc.txt & bộ đếm trong accounts
                            obj = _read_bless_json(self.ctrl, self.port)
                            today = _today_str()
                            now_h = time.strftime("%Y%m%d:%H")
                            for t in blessed_ok:
                                _add_email_blessed_today(obj, t, today, email)
                                _set_target_last_now(obj, t, now_h)
                            _write_bless_json(self.ctrl, self.port, obj)
                            # tăng bộ đếm cho account
                            accounts_path = self.ctrl.w.accounts_path_for_port(self.port)
                            _update_bless_counter_in_file(str(accounts_path), email, today, delta=len(blessed_ok))
                        else:
                            self.log("[BLESS] Không thực hiện được chúc phúc cho bất kỳ target nào ở lượt này.")
                    else:
                        self.log("[BLESS] Không có assignment cho email này trong vòng hiện tại.")

                # 3.5) Tự thoát liên minh — CHỈ khi đã thao tác build/viễn chinh
                if feats.get("autoleave") and (did_build or did_expe) and not self.stop_evt.is_set():
                    self.log("Tự thoát liên minh sau khi thao tác xong…")
                    ok_leave = run_guild_leave_flow(self.wk, log=self.log)
                    if ok_leave:
                        leave_str = _now_time_str()
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

                # RELOAD-ON-CHANGE: kiểm tra 1 lần SAU MỖI LOGOUT (giữ nguyên)
                self._maybe_reload_accounts()

                # nghỉ nhẹ giữa các tài khoản
                if not self._sleep_coop(self.poll):
                    break

            # kết thúc một lượt → quay lại bước 1 để QUÉT LẠI
            if not self._sleep_coop(1.5):
                break

        self.log("Kết thúc auto (đã dừng).")

# ====== API cho UI: gọi khi tick/untick ======
def on_checkbox_toggled(ctrl, port: int, checked: bool):
    row = _table_row_for_port(ctrl, port)
    if row < 0:
        return

    if checked:
        if _get_ui_state(ctrl, row) != "online":
            _ui_log(ctrl, port, "Máy ảo chưa được bật, vui lòng bật máy ảo.")
            _set_checkbox_state_silent(ctrl, row, False)
            return

        try:
            adb_path = str(getattr(ctrl.w, "ADB_PATH", r"D:\Program Files\Nox\bin\adb.exe"))
        except Exception:
            adb_path = r"D:\Program Files\Nox\bin\adb.exe"

        r = _RUNNERS.get(port)
        if r and r.is_alive():
            _ui_log(ctrl, port, "Auto đang chạy.")
            return

        acc_rows = _read_accounts_for(ctrl, port)
        if not acc_rows:
            _ui_log(ctrl, port, "Không có tài khoản (status=1). Vui lòng thêm tài khoản.")
            _set_checkbox_state_silent(ctrl, row, False)
            return

        runner = AccountRunner(ctrl, port, adb_path, poll=1.0)  # muốn nhẹ hơn: poll=3.0
        _RUNNERS[port] = runner
        runner.start()
        _ui_log(ctrl, port, "Bắt đầu auto.")
    else:
        r = _RUNNERS.get(port)
        if r:
            r.request_stop()
        _RUNNERS.pop(port, None)
        _ui_log(ctrl, port, "Kết thúc auto theo yêu cầu.")
