# rescue_utils.py
import time
import cv2
import numpy as np
import re

DEFAULT_CONFIDENCE = 0.88
TAP_DELAY = 0.05

def logmsg(wk, msg: str):
    """Log có prefix theo port/worker."""
    print(f"[{getattr(wk, 'port', '?')}] {msg}")

def adb_safe(wk, *args, timeout=4):
    """Gọi wk.adb() an toàn, luôn trả (code, out_bytes, err_text)."""
    try:
        return wk.adb(*args, timeout=timeout)
    except Exception as e:
        logmsg(wk, f"ADB error: {e}")
        return -1, b"", str(e)

# -------------------- Screen capture --------------------

def _screencap_bytes(wk):
    """Chụp màn hình qua exec-out; fallback qua sdcard."""
    # Ưu tiên exec-out nếu wk.adb_bin có sẵn
    if hasattr(wk, "adb_bin") and callable(getattr(wk, "adb_bin")):
        code, out, _ = wk.adb_bin("exec-out", "screencap", "-p", timeout=5)
        if code == 0 and out:
            return out

    # Fallback: lưu /sdcard rồi cat ra
    adb_safe(wk, "shell", "screencap", "-p", "/sdcard/__cap.png", timeout=4)
    if hasattr(wk, "adb_bin") and callable(getattr(wk, "adb_bin")):
        code, out, _ = wk.adb_bin("shell", "cat", "/sdcard/__cap.png", timeout=6)
        if code == 0 and out:
            return out
    code, out, _ = adb_safe(wk, "shell", "cat", "/sdcard/__cap.png", timeout=6)
    if code == 0 and out:
        return out if isinstance(out, (bytes, bytearray)) else str(out).encode("latin1", "ignore")
    return None

def _grab_screen_np(wk):
    raw = _screencap_bytes(wk)
    if not raw:
        return None
    img = cv2.imdecode(np.frombuffer(raw, dtype=np.uint8), 1)  # BGR
    return img

# -------------------- Template matching --------------------

def _match(img, tpl_path, region=None, threshold=DEFAULT_CONFIDENCE):
    """
    So khớp 1 template trên 1 frame (không đa scale).
    region = (x1,y1,x2,y2) giới hạn vùng tìm.
    """
    tpl = cv2.imread(tpl_path, cv2.IMREAD_COLOR)
    if tpl is None or img is None:
        return (False, None, 0.0)

    crop = img
    rx1 = ry1 = 0
    if region:
        x1, y1, x2, y2 = region
        rx1, ry1 = x1, y1
        crop = img[y1:y2, x1:x2]
        if crop.size == 0 or crop.shape[0] < tpl.shape[0] or crop.shape[1] < tpl.shape[1]:
            return (False, None, 0.0)

    res = cv2.matchTemplate(crop, tpl, cv2.TM_CCOEFF_NORMED)
    _, maxv, _, maxl = cv2.minMaxLoc(res)
    if maxv >= threshold:
        h, w = tpl.shape[:2]
        cx = rx1 + maxl[0] + w // 2
        cy = ry1 + maxl[1] + h // 2
        return (True, (cx, cy), float(maxv))
    return (False, None, float(maxv))

# -------------------- Public helpers (flows_login dùng) --------------------

def find_image_region(wk, tpl_path, region, timeout=2.0, threshold=DEFAULT_CONFIDENCE):
    """
    Tìm ảnh trong 'region' trong khoảng 'timeout' giây.
    Trả về True nếu thấy, False nếu hết thời gian mà không thấy.
    """
    end = time.time() + timeout
    last_score = 0.0
    while time.time() < end:
        img = _grab_screen_np(wk)
        if img is None:
            time.sleep(0.2)
            continue
        ok, pt, sc = _match(img, tpl_path, region=region, threshold=threshold)
        last_score = sc
        logmsg(wk, f"find '{tpl_path}' in {region}: ok={ok}, score={sc:.3f}, pt={pt}")
        if ok:
            return True
        time.sleep(0.2)
    return False

def _tap(wk, x, y):
    logmsg(wk, f"TAP ({x},{y})")
    adb_safe(wk, "shell", "input", "tap", str(x), str(y), timeout=3)
    time.sleep(TAP_DELAY)

def find_and_tap(wk, tpl_path, region, timeout=3.0, threshold=DEFAULT_CONFIDENCE):
    """
    Tìm ảnh trong 'region' rồi TAP vào tâm; lặp cho đến khi hết 'timeout'.
    Trả về True nếu tap thành công, ngược lại False.
    """
    end = time.time() + timeout
    while time.time() < end:
        img = _grab_screen_np(wk)
        if img is None:
            time.sleep(0.2)
            continue
        ok, pt, sc = _match(img, tpl_path, region=region, threshold=threshold)
        logmsg(wk, f"tap '{tpl_path}' in {region}: ok={ok}, score={sc:.3f}, pt={pt}")
        if ok and pt:
            _tap(wk, pt[0], pt[1])
            return True
        time.sleep(0.2)
    return False
def esc_soft_clear(wk, times=2, wait_each=0.8):
    """Nhấn BACK 1 lần + ESC vài lần để dọn popup/overlay."""
    adb_safe(wk, "shell", "input", "keyevent", "4", timeout=2)  # BACK
    for _ in range(times):
        adb_safe(wk, "shell", "input", "keyevent", "111", timeout=2)  # ESC
        time.sleep(wait_each)

def _dump_top_component(wk) -> str | None:
    # thử dumpsys activity
    code, out, _ = adb_safe(wk, "shell", "dumpsys", "activity", "activities", timeout=5)
    if code == 0 and out:
        text = out.decode(errors="ignore") if isinstance(out, (bytes, bytearray)) else str(out)
        for line in text.splitlines():
            if "topResumedActivity" in line or "mResumedActivity" in line:
                m = re.search(r"([a-zA-Z0-9_.]+/[a-zA-Z0-9_.$]+)", line)
                if m: return m.group(1)
    # fallback dumpsys window
    code, out, _ = adb_safe(wk, "shell", "dumpsys", "window", "windows", timeout=5)
    if code == 0 and out:
        text = out.decode(errors="ignore") if isinstance(out, (bytes, bytearray)) else str(out)
        for line in text.splitlines():
            if "mCurrentFocus" in line or "mFocusedApp" in line:
                m = re.search(r"([a-zA-Z0-9_.]+/[a-zA-Z0-9_.$]+)", line)
                if m: return m.group(1)
    return None

def state_simple(wk) -> str:
    """Trả 'need_login' khi đang ở màn login SDK, 'gametw' khi ở trong game, còn lại 'unknown'."""
    comp = _dump_top_component(wk) or ""
    if "com.bbt.android.sdk.login.HWLoginActivity" in comp:
        return "need_login"
    if "org.cocos2dx.javascript.GameTwActivity" in comp:
        return "gametw"
    return "unknown"