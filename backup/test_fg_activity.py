# test_fg_activity.py
# Tìm ACTIVITY foreground cho package trên Nox (theo port ADB cấu hình sẵn)

import subprocess
import re
from pathlib import Path

# ====== CẤU HÌNH ======
PORT = 62025  # 🔹 Sửa port ở đây
PACKAGE = "com.phsgdbz.vn"  # 🔹 Package game Big Bang Thời Không
ADB_PATH = r"D:\Program Files\Nox\bin\adb.exe"  # 🔹 ADB của Nox
# ======================

def run(cmd, timeout=10):
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return p.returncode, p.stdout.strip(), p.stderr.strip()
    except Exception as e:
        return -1, "", f"ERR:{e}"

def adb(*args, timeout=10):
    return run([ADB_PATH, "-s", f"127.0.0.1:{PORT}", *args], timeout=timeout)

def ensure_device() -> bool:
    code, out, _ = adb("get-state", timeout=5)
    return code == 0 and out.strip() == "device"

_component_re = re.compile(r"([a-zA-Z0-9_.]+/[a-zA-Z0-9_.$]+)")

def extract_component_from_text(text: str, package: str) -> str | None:
    for line in text.splitlines():
        if package in line:
            m = _component_re.search(line)
            if m:
                return m.group(1)
    return None

def get_foreground_component_for_package(package: str) -> str | None:
    # 1) dumpsys activity activities
    code, out, _ = adb("shell", "dumpsys", "activity", "activities", timeout=12)
    if code == 0 and out:
        comp = extract_component_from_text(out, package)
        if comp:
            return comp

    # 2) dumpsys window windows
    code, out, _ = adb("shell", "dumpsys", "window", "windows", timeout=12)
    if code == 0 and out:
        comp = extract_component_from_text(out, package)
        if comp:
            return comp

    # 3) cmd activity get-foreground-activity
    code, out, _ = adb("shell", "cmd", "activity", "get-foreground-activity", timeout=8)
    if code == 0 and out and "ComponentInfo{" in out and package in out:
        return out.split("ComponentInfo{", 1)[1].split("}", 1)[0].strip()

    return None

def main():
    print(f"[INFO] Kiểm tra device 127.0.0.1:{PORT} ...")
    if not Path(ADB_PATH).exists():
        print(f"[ERR] Không tìm thấy adb.exe tại: {ADB_PATH}")
        return
    if not ensure_device():
        print(f"[ERR] Thiết bị chưa online hoặc chưa boot xong.")
        return

    comp = get_foreground_component_for_package(PACKAGE)
    if comp:
        pkg = comp.split("/", 1)[0]
        print(f"PACKAGE : {pkg}")
        print(f"ACTIVITY: {comp}")
    else:
        print(f"[INFO] Không tìm thấy activity foreground cho package '{PACKAGE}'.")
        print(" • Hãy mở game/app đó trên Nox rồi chạy lại.")

if __name__ == "__main__":
    main()
