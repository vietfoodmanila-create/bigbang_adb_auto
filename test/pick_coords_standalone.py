# File: pick_coords_standalone_final.py
# KẾT HỢP TỪ CÁC FILE GỐC ĐANG HOẠT ĐỘNG CỦA BẠN.
# Giữ nguyên 100% logic gốc, chỉ thêm tính năng refresh ảnh bằng phím 'r'.

import sys
import subprocess
import time
import os
import uuid
from pathlib import Path

# CÁC THƯ VIỆN BÊN NGOÀI CẦN CÀI ĐẶT
# pip install opencv-python numpy pytesseract pyperclip
import cv2
import numpy as np
import pytesseract

try:
    import pyperclip
except ImportError:
    print("Cảnh báo: Thư viện pyperclip chưa được cài đặt. Sẽ không thể copy tọa độ vào clipboard.")
    print("Để cài đặt, chạy: pip install pyperclip")
    pyperclip = None

# ====================================================================
# === PHẦN 1: CODE SAO CHÉP TỪ CONFIG.PY =============================
# ====================================================================

# !!! VUI LÒNG KIỂM TRA VÀ CHỈNH LẠI CÁC ĐƯỜNG DẪN BÊN DƯỚI !!!
DEBUG = True
SHOT_DIR = "shots"
ADB_PATH = r"D:\Program Files\Nox\bin\nox_adb.exe"
DEVICE = "127.0.0.1:62025"
SCREEN_W, SCREEN_H = 900, 1600
TESSERACT_EXE = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
TESSDATA_DIR = r"C:\Program Files\Tesseract-OCR\tessdata"


# ====================================================================
# === PHẦN 2: CODE SAO CHÉP TỪ ADB_UTILS.PY ==========================
# ====================================================================

def _run(args, text=True):
    return subprocess.run(args, capture_output=True, text=text)


def adb(*args, text=True):
    # Thêm -s DEVICE vào lệnh, y hệt code gốc của bạn
    cmd_with_device = [ADB_PATH, "-s", DEVICE] + list(args)
    if DEBUG:
        print("→ ADB:", " ".join([str(x) for x in cmd_with_device]))
    return _run(cmd_with_device, text=text)


def ensure_connected():
    # Hàm này từ file gốc của bạn
    if not Path(ADB_PATH).exists():
        raise FileNotFoundError(f"Không thấy ADB ở: {ADB_PATH}")

    # Chạy lệnh adb devices không có -s để kiểm tra kết nối chung
    out = _run([ADB_PATH, "devices"]).stdout
    if DEVICE not in out:
        print(f"🔌 Đang kết nối {DEVICE} ...")
        _run([ADB_PATH, "connect", DEVICE])
        out = _run([ADB_PATH, "devices"]).stdout

    if DEVICE not in out or "device" not in out.split(DEVICE)[-1]:
        raise RuntimeError(f"ADB chưa thấy {DEVICE}. Hãy mở Nox và đúng cổng.")
    print(f"✅ ADB đã kết nối {DEVICE}")


# ====================================================================
# === PHẦN 3: CODE SAO CHÉP TỪ SCREEN_UTILS.PY ========================
# ====================================================================

def screencap_bytes() -> bytes:
    p = adb("exec-out", "screencap", "-p", text=False)
    if p.returncode != 0 or not p.stdout:
        raise RuntimeError("Không chụp được màn hình qua ADB.")
    return p.stdout


def screencap_cv(debug_save: bool | None = None) -> np.ndarray | None:
    if debug_save is None:
        debug_save = DEBUG
    try:
        data = screencap_bytes()
        img = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
        if img is None:
            raise RuntimeError("Giải mã ảnh thất bại.")

        if debug_save:
            Path(SHOT_DIR).mkdir(parents=True, exist_ok=True)
            ts = time.strftime("%Y%m%d_%H%M%S")
            path = Path(SHOT_DIR) / f"screen_{ts}.png"
            cv2.imwrite(str(path), img)
            print(f"💾 Saved: {path}  shape={img.shape}")
        return img
    except Exception as e:
        print(f"Lỗi khi chụp màn hình: {e}")
        return None


# ====================================================================
# === PHẦN 4: CODE SAO CHÉP TỪ OCR_UTILS.PY ==========================
# ====================================================================

pytesseract.pytesseract.tesseract_cmd = TESSERACT_EXE


def _set_tess_prefix():
    prefix = str(Path(TESSDATA_DIR))
    if not prefix.endswith(("\\", "/")):
        prefix += os.sep
    os.environ["TESSDATA_PREFIX"] = prefix


_set_tess_prefix()


def ocr_image(img_bgr, lang="vie", psm=6, whitelist=None, save_roi: bool | None = None) -> str:
    # Đây là hàm ocr_image từ file gốc của bạn
    if save_roi is None: save_roi = DEBUG

    gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
    gray = cv2.GaussianBlur(gray, (3, 3), 0)
    gray = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1]

    if save_roi:
        Path(SHOT_DIR).mkdir(parents=True, exist_ok=True)
        p = Path(SHOT_DIR, f"roi_{uuid.uuid4().hex[:6]}.png")
        cv2.imwrite(str(p), gray)
        print(f"💾 ROI saved: {p}")

    cfg = f"--oem 3 --psm {psm}"
    if whitelist:
        cfg += f" -c tessedit_char_whitelist={whitelist}"

    try:
        return pytesseract.image_to_string(gray, lang=lang, config=cfg).strip()
    except Exception as e:
        print(f"Lỗi Tesseract: {e}")
        return "[OCR FAILED]"


# ====================================================================
# === PHẦN 5: CODE TỪ TEST/PICK_COORDS.PY (Thêm tính năng) ===========
# ====================================================================

# Các biến toàn cục từ file gốc
SCALE = 0.6
img = None
disp = None
start = None
dragging = False


def copy_clip(txt: str):
    if pyperclip:
        pyperclip.copy(txt)
    else:
        print("(pyperclip not installed, cannot copy to clipboard)")


def on_mouse(event, x, y, flags, param):
    global start, dragging, disp, img
    gx, gy = int(x / SCALE), int(y / SCALE)

    if event == cv2.EVENT_RBUTTONDOWN:
        print(f"📍 Point: {gx},{gy}")
        copy_clip(f"{gx},{gy}")

    if event == cv2.EVENT_LBUTTONDOWN:
        start = (gx, gy)
        dragging = True

    elif event == cv2.EVENT_MOUSEMOVE and dragging:
        disp[:] = cv2.resize(img, None, fx=SCALE, fy=SCALE, interpolation=cv2.INTER_AREA)
        x1, y1 = start
        x2, y2 = gx, gy
        cv2.rectangle(disp, (int(x1 * SCALE), int(y1 * SCALE)), (int(x2 * SCALE), int(y2 * SCALE)), (0, 255, 0), 2)

    elif event == cv2.EVENT_LBUTTONUP and dragging:
        dragging = False
        x1, y1 = start
        x2, y2 = gx, gy
        if x2 < x1: x1, x2 = x2, x1
        if y2 < y1: y1, y2 = y2, y1
        h, w = img.shape[:2]
        x1 = max(0, min(w - 1, x1));
        x2 = max(0, min(w, x2))
        y1 = max(0, min(h - 1, y1));
        y2 = max(0, min(h, y2))
        if x2 <= x1 or y2 <= y1:
            print("⚠️ ROI rỗng, bỏ qua.")
            return

        roi_txt = f"{x1},{y1},{x2},{y2}"
        print("📐 ROI:", roi_txt)
        copy_clip(roi_txt)
        roi = img[y1:y2, x1:x2].copy()
        Path(SHOT_DIR).mkdir(parents=True, exist_ok=True)
        ts = time.strftime("%Y%m%d_%H%M%S")
        roi_path = Path(SHOT_DIR) / f"roi_{ts}_{x1}-{y1}_{x2}-{y2}.png"
        cv2.imwrite(str(roi_path), roi)
        print(f"💾 ROI saved: {roi_path}")
        try:
            text = ocr_image(roi, lang="vie", psm=6, save_roi=False)
            print("🔎 OCR:", text if text else "(rỗng)")
        except Exception as e:
            print("❌ OCR error:", e)


if __name__ == "__main__":
    try:
        ensure_connected()
        img = screencap_cv(debug_save=DEBUG)
        if img is None:
            raise RuntimeError("Không thể chụp ảnh màn hình ban đầu.")

        disp = cv2.resize(img, None, fx=SCALE, fy=SCALE, interpolation=cv2.INTER_AREA)

        title = "Pick ROI (L-drag=OCR, R-click=point, r=Refresh, q/ESC=quit)"
        cv2.namedWindow(title)
        cv2.setMouseCallback(title, on_mouse)

        while True:
            cv2.imshow(title, disp)
            key = cv2.waitKey(20) & 0xFF

            # Thoát chương trình
            if key in (ord('q'), 27):  # 27 là mã của phím ESC
                break

            # TÍNH NĂNG MỚI: Nhấn 'r' để refresh ảnh
            if key == ord('r'):
                print("\nĐang làm mới ảnh màn hình...")
                new_img = screencap_cv(debug_save=DEBUG)
                if new_img is not None:
                    img = new_img
                    disp = cv2.resize(img, None, fx=SCALE, fy=SCALE, interpolation=cv2.INTER_AREA)
                    print("Làm mới thành công!")
                else:
                    print("Làm mới thất bại, giữ lại ảnh cũ.")

        cv2.destroyAllWindows()

    except Exception as e:
        print(f"\nLỗi nghiêm trọng: {e}")
        input("Nhấn Enter để thoát.")
        sys.exit(1)