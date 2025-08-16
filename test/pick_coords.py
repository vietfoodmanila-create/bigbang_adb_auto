# tests/pick_coords.py
import time
from pathlib import Path

import cv2
try:
    import pyperclip
except:
    pyperclip = None

from config import DEBUG, SHOT_DIR
from adb_utils import ensure_connected
from screen_utils import screencap_cv
from ocr_utils import ocr_image

SCALE = 0.6  # thu nhỏ ảnh hiển thị cho dễ xem; tọa độ vẫn tính theo ảnh gốc!

img = None      # ảnh gốc BGR (1600x900x3)
disp = None     # ảnh hiển thị đã scale
start = None
dragging = False

def copy_clip(txt: str):
    if pyperclip:
        pyperclip.copy(txt)

def on_mouse(event, x, y, flags, param):
    global start, dragging, disp, img

    # map tọa độ hiển thị -> ảnh gốc
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
        cv2.rectangle(disp,
                      (int(x1 * SCALE), int(y1 * SCALE)),
                      (int(x2 * SCALE), int(y2 * SCALE)),
                      (0, 255, 0), 2)

    elif event == cv2.EVENT_LBUTTONUP and dragging:
        dragging = False
        x1, y1 = start
        x2, y2 = gx, gy
        if x2 < x1: x1, x2 = x2, x1
        if y2 < y1: y1, y2 = y2, y1

        # Giới hạn vào khung ảnh
        h, w = img.shape[:2]
        x1 = max(0, min(w - 1, x1)); x2 = max(0, min(w, x2))
        y1 = max(0, min(h - 1, y1)); y2 = max(0, min(h, y2))
        if x2 <= x1 or y2 <= y1:
            print("⚠️ ROI rỗng, bỏ qua.")
            return

        roi_txt = f"{x1},{y1},{x2},{y2}"
        print("📐 ROI:", roi_txt)
        copy_clip(roi_txt)

        # CẮT & LƯU ROI
        roi = img[y1:y2, x1:x2].copy()
        Path(SHOT_DIR).mkdir(parents=True, exist_ok=True)
        ts = time.strftime("%Y%m%d_%H%M%S")
        roi_path = Path(SHOT_DIR) / f"roi_{ts}_{x1}-{y1}_{x2}-{y2}.png"
        cv2.imwrite(str(roi_path), roi)
        print(f"💾 ROI saved: {roi_path}")

        # OCR ROI (tiếng Việt; đổi psm nếu cần)
        try:
            text = ocr_image(roi, lang="vie", psm=6, save_roi=False)
            print("🔎 OCR:", text if text else "(rỗng)")
        except Exception as e:
            print("❌ OCR error:", e)

if __name__ == "__main__":
    ensure_connected()
    # chụp màn hình; nếu DEBUG=True thì screen đầy đủ vẫn tự lưu ở SHOT_DIR
    img = screencap_cv(debug_save=DEBUG)
    disp = cv2.resize(img, None, fx=SCALE, fy=SCALE, interpolation=cv2.INTER_AREA)

    title = "Pick ROI (L-drag=crop+OCR, R-click=point, q/ESC=quit)"
    cv2.namedWindow(title)
    cv2.setMouseCallback(title, on_mouse)

    while True:
        cv2.imshow(title, disp)
        key = cv2.waitKey(10) & 0xFF
        if key in (ord('q'), 27):
            break

    cv2.destroyAllWindows()
