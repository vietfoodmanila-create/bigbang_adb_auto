# config.py
# Cấu hình để sử dụng MỘT ADB DUY NHẤT cho cả Nox và LDPlayer

# ==== DEBUG ====
DEBUG = True
SHOT_DIR = "shots"
import os
from module import resource_path
def get_bundled_adb_path() -> str:
    return resource_path(os.path.join("vendor", "adb.exe"))

# ==== ADB (SỬ DỤNG PHIÊN BẢN ADB CHÍNH THỨC TỪ PLATFORM-TOOLS) ====
# !!! QUAN TRỌNG: Sửa đường dẫn này trỏ đến file adb.exe bạn vừa tải về ở Bước 2 !!!
PLATFORM_TOOLS_ADB_PATH = get_bundled_adb_path()
NOX_ADB_PATH = get_bundled_adb_path()
LDPLAYER_ADB_PATH = get_bundled_adb_path()
print(f"Đã tự động cấu hình ADB path: {PLATFORM_TOOLS_ADB_PATH}")
# Biến này cho phép quét cả hai loại máy ảo
EMULATOR_TYPE = "BOTH"

# Các biến cũ để tương thích
ADB_PATH = PLATFORM_TOOLS_ADB_PATH
DEVICE = ""

# ==== Screen size (Android) ====
SCREEN_W, SCREEN_H = 900, 1600

# ==== Tesseract ====
TESSERACT_EXE = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
TESSDATA_DIR  = r"C:\Program Files\Tesseract-OCR\tessdata"