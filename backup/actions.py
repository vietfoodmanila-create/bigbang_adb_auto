# actions.py
from match_utils import wait_and_tap
from adb_utils import input_text
from screen_utils import screencap_cv
from ocr_utils import ocr_region

def click_template(path, timeout=8, thr=0.88):
    ok, pos, score = wait_and_tap(path, timeout=timeout, thr=thr)
    return ok

def type_text(text):
    input_text(text)

def ocr_wait_contains(x1,y1,x2,y2, keyword, lang="vie", psm=6, timeout=8, interval=0.5):
    import time
    t0 = time.time()
    while time.time() - t0 < timeout:
        img = screencap_cv(debug_save=False)
        txt = ocr_region(img, x1,y1,x2,y2, lang=lang, psm=psm)
        if keyword.lower() in txt.lower():
            return True, txt
        time.sleep(interval)
    return False, txt
