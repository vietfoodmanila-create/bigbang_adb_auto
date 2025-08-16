# match_utils.py
from pathlib import Path
import time
import cv2
import numpy as np

from config import DEBUG, SHOT_DIR
from screen_utils import screencap_cv
from adb_utils import tap

# ===== Template cache =====
_TEMPLATE_CACHE: dict[str, np.ndarray] = {}

def load_template(path: str) -> np.ndarray:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Không thấy template: {p}")
    img = _TEMPLATE_CACHE.get(path)
    if img is None:
        img = cv2.imread(str(p), cv2.IMREAD_COLOR)
        if img is None:
            raise RuntimeError(f"Không đọc được template: {p}")
        _TEMPLATE_CACHE[path] = img
    return img

# ===== Matching primitives =====
def match_once(screen_bgr: np.ndarray, template_bgr: np.ndarray, thr: float = 0.88):
    """
    Trả về: (found:bool, center:(x,y)|None, score:float, box:(x,y,w,h)|None)
    """
    res = cv2.matchTemplate(screen_bgr, template_bgr, cv2.TM_CCOEFF_NORMED)
    _, maxv, _, maxloc = cv2.minMaxLoc(res)
    if maxv >= thr:
        h, w = template_bgr.shape[:2]
        x, y = maxloc
        cx, cy = x + w // 2, y + h // 2
        return True, (cx, cy), float(maxv), (x, y, w, h)
    return False, None, float(maxv), None

def find_all(screen_bgr: np.ndarray, template_bgr: np.ndarray, thr: float = 0.88, max_count: int = 20):
    """
    Tìm tất cả vị trí khớp >= thr. Trả list [(x,y,w,h,score), ...], sort theo score giảm dần.
    """
    res = cv2.matchTemplate(screen_bgr, template_bgr, cv2.TM_CCOEFF_NORMED)
    ys, xs = np.where(res >= thr)
    h, w = template_bgr.shape[:2]
    hits = []
    for y, x in zip(ys, xs):
        score = float(res[y, x])
        hits.append((x, y, w, h, score))
    # Non-maximum suppression đơn giản
    hits.sort(key=lambda t: -t[4])
    picked = []
    for x, y, w, h, s in hits:
        if all(abs(x - px) > w * 0.5 or abs(y - py) > h * 0.5 for px, py, _, _, _ in picked):
            picked.append((x, y, w, h, s))
            if len(picked) >= max_count:
                break
    return picked

def draw_box(img, box, color=(0, 255, 0), thick=2):
    x, y, w, h = box
    cv2.rectangle(img, (x, y), (x + w, y + h), color, thick)

# ===== High-level helpers =====
def wait_and_tap(template_path: str, timeout: float = 10, thr: float = 0.88, interval: float = 0.4):
    """
    Lặp: chụp -> match -> nếu thấy thì tap và (nếu DEBUG) lưu ảnh đã vẽ khung.
    Trả về: (True,(cx,cy),score) nếu thành công; else (False,None,max_score)
    """
    tpl = load_template(template_path)
    t0 = time.time()
    best_score = 0.0
    best_box = None

    while time.time() - t0 < timeout:
        screen = screencap_cv(debug_save=False)
        ok, pos, score, box = match_once(screen, tpl, thr)
        best_score = max(best_score, score)
        if ok and pos:
            tap(*pos)
            if DEBUG:
                Path(SHOT_DIR).mkdir(parents=True, exist_ok=True)
                dbg = screen.copy()
                draw_box(dbg, box, (0, 255, 0), 2)
                out = Path(SHOT_DIR) / f"match_{Path(template_path).stem}_{int(time.time())}.png"
                cv2.imwrite(str(out), dbg)
                print(f"💾 Saved debug: {out} (score={score:.3f})")
            return True, pos, score
        time.sleep(interval)

    # lưu best try nếu fail
    if DEBUG:
        screen = screencap_cv(debug_save=False)
        if best_box:
            dbg = screen.copy()
            draw_box(dbg, best_box, (0, 0, 255), 2)
            out = Path(SHOT_DIR) / f"match_fail_{Path(template_path).stem}.png"
            cv2.imwrite(str(out), dbg)
            print(f"💾 Saved best-try: {out} (best_score={best_score:.3f})")
    return False, None, best_score
