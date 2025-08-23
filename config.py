# config.py
# ==== DEBUG ====
DEBUG = True                     # ← bật/tắt debug toàn cục
SHOT_DIR = "shots"               # thư mục lưu ảnh debug

# ==== ADB ====
# Giữ lại đường dẫn cũ cho Nox
NOX_ADB_PATH = r"D:\Program Files\Nox\bin\nox_adb.exe"

# Thêm đường dẫn cho LDPlayer (sử dụng dnadb.exe là chuẩn cho LDPlayer 9)
LDPLAYER_ADB_PATH = r"D:\LDPlayer\LDPlayer9\dnadb.exe"

# Biến mới để chọn loại máy ảo sẽ quét
# Có thể là "NOX", "LDPLAYER", hoặc "BOTH"
EMULATOR_TYPE = "BOTH"

# Đổi tên biến ADB_PATH cũ để tránh nhầm lẫn và giữ tương thích
ADB_PATH = r"D:\Program Files\Nox\bin\nox_adb.exe"      # hoặc r"D:\Program Files\Nox\bin\nox_adb.exe"
DEVICE   = "127.0.0.1:62025"

# ==== Screen size (Android) ====
SCREEN_W, SCREEN_H = 900, 1600

# ==== Tesseract ====
TESSERACT_EXE = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
TESSDATA_DIR  = r"C:\Program Files\Tesseract-OCR\tessdata"   # đúng thư mục tessdata