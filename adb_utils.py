# adb_utils.py
import subprocess, shutil
from pathlib import Path
from config import ADB_PATH, DEVICE, DEBUG

def _run(args, text=True):
    return subprocess.run(args, capture_output=True, text=text)

def adb_ok() -> bool:
    return Path(ADB_PATH).exists() or shutil.which(Path(ADB_PATH).name) is not None

def adb(*args, text=True):
    if DEBUG:
        print("→ ADB:", " ".join([str(x) for x in ([ADB_PATH] + list(args))]))
    return _run([ADB_PATH] + list(args), text=text)

def ensure_connected() -> None:
    if not adb_ok():
        raise FileNotFoundError(f"Không thấy ADB ở: {ADB_PATH}")
    out = adb("devices").stdout
    if DEVICE not in out:
        adb("connect", DEVICE)
        out = adb("devices").stdout
    if DEVICE not in out or "device" not in out.split(DEVICE)[-1]:
        raise RuntimeError(f"ADB chưa thấy {DEVICE}. Hãy mở Nox và đúng cổng 62xxx")

def tap(x: int, y: int, delay_ms: int = 0):
    adb("shell", "input", "tap", str(x), str(y))
    if delay_ms:
        import time; time.sleep(delay_ms/1000)

def swipe(x1, y1, x2, y2, dur_ms=200):
    adb("shell", "input", "swipe", str(x1), str(y1), str(x2), str(y2), str(dur_ms))

def input_text(text: str):
    adb("shell", "input", "text", text.replace(" ", "%s"))

def wm_size() -> str:
    return adb("shell", "wm", "size").stdout.strip()
