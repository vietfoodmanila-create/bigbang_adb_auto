# config.py
# ==== DEBUG ====
DEBUG = True                     # ← bật/tắt debug toàn cục
SHOT_DIR = "shots"               # thư mục lưu ảnh debug

# ==== ADB ====
ADB_PATH = r"C:\platform-tools\adb.exe"      # hoặc r"D:\Program Files\Nox\bin\nox_adb.exe"
DEVICE   = "127.0.0.1:62025"

# ==== Screen size (Android) ====
SCREEN_W, SCREEN_H = 900, 1600

# ==== Tesseract ====
TESSERACT_EXE = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
TESSDATA_DIR  = r"C:\Program Files\Tesseract-OCR\tessdata"   # đúng thư mục tessdata

