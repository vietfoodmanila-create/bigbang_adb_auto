# test_logout.py
# Test độc lập flow thoát tài khoản (ưu tiên template ảnh; có adb_bin để screencap nhị phân)

import subprocess, time, re
from pathlib import Path
from types import SimpleNamespace as NS

# ===== CẤU HÌNH =====
ADB  = r"D:\Program Files\Nox\bin\adb.exe"   # <— sửa cho đúng
PORT = 62025                                  # <— sửa nếu cần
PKG  = "com.phsgdbz.vn"
ACT  = "com.phsgdbz.vn/org.cocos2dx.javascript.GameTwActivity"
# =====================

def run(cmd, timeout=12, text=True):
    try:
        p = subprocess.run(cmd, capture_output=True, text=text, timeout=timeout)
        return p.returncode, (p.stdout or ""), (p.stderr or "")
    except subprocess.TimeoutExpired:
        return 124, "", "timeout"
    except Exception as e:
        return 125, "", str(e)

def run_bin(cmd, timeout=12):
    try:
        p = subprocess.run(cmd, capture_output=True, timeout=timeout)
        return p.returncode, p.stdout, p.stderr
    except subprocess.TimeoutExpired:
        return 124, b"", b"timeout"
    except Exception as e:
        return 125, b"", str(e).encode()

def adb_raw(*args, timeout=10):
    return run([ADB, *args], timeout=timeout)

def adb(*args, timeout=10):
    return run([ADB, "-s", f"127.0.0.1:{PORT}", *args], timeout=timeout)

def adb_bin(*args, timeout=10):
    return run_bin([ADB, "-s", f"127.0.0.1:{PORT}", *args], timeout=timeout)
# --- NEW: ensure_connect có retry + kill-server fallback
def ensure_connect():
    # start-server: tăng timeout + retry
    for i in range(2):
        code, out, err = adb_raw("start-server", timeout=20)
        if code == 0:
            break
        # nếu timeout/err, thử kill-server rồi start lại
        adb_raw("kill-server", timeout=5)
        time.sleep(0.5)
    # thử connect tới Nox port vài lần
    for i in range(6):
        adb_raw("connect", f"127.0.0.1:{PORT}", timeout=5)
        code, out, _ = adb("get-state", timeout=3)
        if code == 0 and (out or "").strip() == "device":
            return True
        time.sleep(1.5)
    return False

def ensure_connect():
    adb_raw("start-server", timeout=5)
    adb_raw("connect", f"127.0.0.1:{PORT}", timeout=5)
    code, out, _ = adb("get-state", timeout=3)
    return code == 0 and out.strip() == "device"

def start_app():
    adb("shell", "am", "start", "-n", ACT,
        "-a", "android.intent.action.MAIN",
        "-c", "android.intent.category.LAUNCHER", timeout=10)

def top_component():
    code, out, _ = adb("shell", "dumpsys", "activity", "activities", timeout=8)
    if code == 0 and out:
        for line in out.splitlines():
            if "topResumedActivity" in line or "mResumedActivity" in line:
                m = re.search(r"([a-zA-Z0-9_.]+/[a-zA-Z0-9_.$]+)", line)
                if m: return m.group(1)
    code, out, _ = adb("shell", "dumpsys", "window", "windows", timeout=8)
    if code == 0 and out:
        for line in out.splitlines():
            if "mCurrentFocus" in line or "mFocusedApp" in line:
                m = re.search(r"([a-zA-Z0-9_.]+/[a-zA-Z0-9_.$]+)", line)
                if m: return m.group(1)
    return None

def state_simple():
    comp = top_component() or ""
    if "com.bbt.android.sdk.login.HWLoginActivity" in comp:
        return "need_login"
    if "org.cocos2dx.javascript.GameTwActivity" in comp:
        return "gametw"
    return "unknown"

def wait_ready(timeout=30):
    end = time.time() + timeout
    while time.time() < end:
        st = state_simple()
        if st in ("need_login", "gametw"):
            return True
        time.sleep(1.0)
    return False

def pid_running(pkg):
    code, out, _ = adb("shell", "pidof", pkg, timeout=3)
    return code == 0 and bool((out or "").strip())

def _wk_adb(*args, **kw):
    return adb(*args, timeout=kw.get("timeout", 8))

def _wk_start_app(_pkg, _act):
    start_app()

def _wk_wait_app_ready(_pkg, t):
    return wait_ready(t)

def main():
    if not Path(ADB).exists():
        print(f"[ERR] Không tìm thấy ADB: {ADB}")
        return

    print("[*] Kết nối ADB tới Nox…")
    if not ensure_connect():
        print(f"[ERR] Không kết nối được 127.0.0.1:{PORT}")
        return
    print("[OK] ADB sẵn sàng.")

    if not pid_running(PKG):
        print("[*] Mở game…")
        start_app()
        if not wait_ready(45):
            print("[ERR] Game không sẵn sàng.")
            return

    wk = NS(
        port=PORT,
        game_package=PKG,
        game_activity=ACT,
        adb=_wk_adb,
        adb_bin=adb_bin,             # <— rất quan trọng cho screencap nhị phân
        start_app=_wk_start_app,
        wait_app_ready=_wk_wait_app_ready,
    )

    from flows_logout import logout_once
    print("[*] Bắt đầu thoát tài khoản…")
    ok = logout_once(wk, max_rounds=3)
    print("[DONE]" if ok else "[FAIL]", "| STATE:", state_simple())

if __name__ == "__main__":
    main()
