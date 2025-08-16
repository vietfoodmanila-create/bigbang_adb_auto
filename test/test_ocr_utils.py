# test_ocr_utils.py
from adb_utils import ensure_connected
from screen_utils import screencap_cv
from ocr_utils import ocr_region, tess_diag

ensure_connected()
tess_diag()

img = screencap_cv(debug_save=True)

# Dùng ROI bạn vừa đo: 355,871,541,935
x1, y1, x2, y2 = 355, 871, 541, 935
txt = ocr_region(img, x1, y1, x2, y2, lang="vie", psm=6)
print("📄 OCR:", txt)
