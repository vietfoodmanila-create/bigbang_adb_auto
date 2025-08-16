# ocr_utils.py
import os, uuid, subprocess
from pathlib import Path
import cv2, pytesseract
from config import TESSERACT_EXE, TESSDATA_DIR, DEBUG, SHOT_DIR

# --- Setup Tesseract ---
pytesseract.pytesseract.tesseract_cmd = TESSERACT_EXE

def _set_tess_prefix():
    # IMPORTANT: on your system Tesseract expects PREFIX == tessdata folder itself
    prefix = str(Path(TESSDATA_DIR))
    if not prefix.endswith(("\\", "/")):
        prefix += os.sep
    os.environ["TESSDATA_PREFIX"] = prefix
_set_tess_prefix()

def _tess_cmd(*args, timeout=5):
    # inherits env with our TESSDATA_PREFIX
    return subprocess.run([TESSERACT_EXE, *args], capture_output=True, text=True, timeout=timeout)

def tess_list_langs() -> list[str]:
    try:
        out = _tess_cmd("--list-langs").stdout
        langs = []
        for line in out.splitlines():
            s = line.strip()
            if not s or s.lower().startswith("list of"):
                continue
            s = s.replace("/", os.sep).replace("\\", os.sep).split(os.sep)[-1]
            if s.endswith(".traineddata"): s = s[:-len(".traineddata")]
            langs.append(s.lower())
        return langs
    except Exception:
        return []

def tess_diag():
    _set_tess_prefix()
    langs = tess_list_langs()
    print(f"Tesseract exe : {TESSERACT_EXE}  [{'OK' if Path(TESSERACT_EXE).exists() else 'MISSING'}]")
    print(f"TESSDATA_PREFIX: {os.environ.get('TESSDATA_PREFIX')}")
    print(f"Langs         : {', '.join(langs) or '(none)'}")
    print(f"vie exists    : {Path(TESSDATA_DIR,'vie.traineddata').exists()}")
    print(f"eng exists    : {Path(TESSDATA_DIR,'eng.traineddata').exists()}")

def _cfg(psm=6, whitelist=None) -> str:
    # no --tessdata-dir here
    cfg = f"--oem 3 --psm {psm}"
    if whitelist:
        cfg += f" -c tessedit_char_whitelist={whitelist}"
    return cfg

def _preprocess(img_bgr):
    gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
    gray = cv2.GaussianBlur(gray, (3,3), 0)
    gray = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY+cv2.THRESH_OTSU)[1]
    return gray

def ocr_image(img_bgr, lang="vie", psm=6, whitelist=None, save_roi: bool | None = None) -> str:
    if save_roi is None: save_roi = DEBUG
    gray = _preprocess(img_bgr)

    if save_roi:
        Path(SHOT_DIR).mkdir(parents=True, exist_ok=True)
        p = Path(SHOT_DIR, f"roi_{uuid.uuid4().hex[:6]}.png")
        cv2.imwrite(str(p), gray)
        print(f"💾 ROI saved: {p}")

    # sanity: required files
    if not Path(TESSDATA_DIR, "vie.traineddata").exists():
        print("⚠️ Missing vie.traineddata in TESSDATA_DIR; will try ENG fallback.")
    if not Path(TESSDATA_DIR, "eng.traineddata").exists():
        print("⚠️ Missing eng.traineddata in TESSDATA_DIR.")

    cfg = _cfg(psm, whitelist)
    langs = tess_list_langs()
    chosen = (lang if lang.lower() in langs else
              ("vie+eng" if "vie" in langs and "eng" in langs else
               ("eng" if "eng" in langs else None)))
    if chosen is None:
        raise RuntimeError(f"No usable languages. langs={langs}, PREFIX={os.environ.get('TESSDATA_PREFIX')}")

    _set_tess_prefix()
    return pytesseract.image_to_string(gray, lang=chosen, config=cfg).strip()

def ocr_region(img_bgr, x1, y1, x2, y2, **kw) -> str:
    return ocr_image(img_bgr[y1:y2, x1:x2], **kw)
