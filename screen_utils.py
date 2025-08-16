# screen_utils.py
import time
from pathlib import Path
import numpy as np, cv2
from config import DEBUG, SHOT_DIR
from adb_utils import adb

def screencap_bytes() -> bytes:
    p = adb("exec-out", "screencap", "-p", text=False)
    if p.returncode != 0 or not p.stdout:
        raise RuntimeError("Không chụp được màn hình qua ADB.")
    return p.stdout

def screencap_cv(debug_save: bool | None = None):
    """Chụp → OpenCV image (RAM). Nếu debug_save=None sẽ lấy theo config.DEBUG."""
    if debug_save is None:
        debug_save = DEBUG

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

def save_png(img, path):
    cv2.imwrite(str(path), img)

def crop(img, x1, y1, x2, y2):
    return img[y1:y2, x1:x2]
