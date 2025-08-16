import subprocess
import time

ADB_PATH = r"D:\Program Files\Nox\bin\adb.exe"
PORT = 62025  # sửa theo port bạn muốn test
PACKAGE = "com.bigbang.timespace"  # tên package của game
ACTIVITY = "com.bigbang.timespace/com.unity3d.player.UnityPlayerActivity"  # activity nếu biết, không thì để None

def adb(*args):
    """Chạy lệnh adb và trả (code, stdout, stderr)."""
    cmd = [ADB_PATH, "-s", f"127.0.0.1:{PORT}"] + list(args)
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    out, err = proc.communicate()
    return proc.returncode, out.strip(), err.strip()

def app_in_foreground(package):
    """Kiểm tra app có đang foreground không."""
    code, out, _ = adb("shell", "dumpsys", "activity", "activities")
    if code != 0:
        return False
    for line in out.splitlines():
        if "mResumedActivity" in line and package in line:
            return True
    return False

def launch_game():
    if ACTIVITY:
        print(f"[TEST] Mở game bằng am start: {ACTIVITY}")
        adb("shell", "am", "start", "-n", ACTIVITY)
    else:
        print(f"[TEST] Mở game bằng monkey: {PACKAGE}")
        adb("shell", "monkey", "-p", PACKAGE, "-c", "android.intent.category.LAUNCHER", "1")

    print("[TEST] Đợi game vào foreground...")
    for _ in range(60):
        if app_in_foreground(PACKAGE):
            print("[OK] Game đã vào foreground!")
            return True
        time.sleep(1.5)
    print("[FAIL] Game không vào foreground sau timeout.")
    return False

if __name__ == "__main__":
    # Kiểm tra kết nối trước
    code, out, _ = adb("get-state")
    if "device" not in out.lower():
        print("[ERROR] Máy ảo chưa online hoặc chưa boot xong.")
    else:
        launch_game()
