import os
import subprocess
import cv2
import numpy as np
import pytesseract

# ======================
# CẤU HÌNH ADB
# ======================
ADB = r"C:\platform-tools\adb.exe"  # Hoặc đường dẫn nox_adb.exe
DEVICE = "127.0.0.1:62025"

# ======================
# CẤU HÌNH TESSERACT
# ======================
TESSERACT_PATH = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
TESSDATA_DIR = r"C:\Program Files\Tesseract-OCR\tessdata"

pytesseract.pytesseract.tesseract_cmd = TESSERACT_PATH
os.environ["TESSDATA_PREFIX"] = TESSDATA_DIR  # Đặt biến môi trường trực tiếp

# ======================
# HÀM TIỆN ÍCH
# ======================
def adb(*args):
    """Chạy lệnh adb"""
    return subprocess.run([ADB] + list(args), capture_output=True, text=True)

def ensure_connected():
    """Kết nối lại nếu chưa thấy thiết bị"""
    out = adb("devices").stdout
    if DEVICE not in out:
        print(f"🔄 Đang kết nối {DEVICE}...")
        adb("connect", DEVICE)
    else:
        print(f"✅ Đã kết nối {DEVICE}")

def screencap_bytes():
    """Chụp màn hình và trả về dữ liệu bytes"""
    p = subprocess.run([ADB, "exec-out", "screencap", "-p"], capture_output=True)
    return p.stdout

# ======================
# MAIN
# ======================
if __name__ == "__main__":
    ensure_connected()

    print("📸 Đang chụp màn hình...")
    img_data = screencap_bytes()
    img_arr = np.frombuffer(img_data, np.uint8)
    img = cv2.imdecode(img_arr, cv2.IMREAD_COLOR)

    if img is None:
        print("❌ Không chụp được màn hình. Kiểm tra kết nối ADB.")
        exit()

    cv2.imwrite("../screen.png", img)
    print("✅ Đã lưu screen.png")

    # Xử lý ảnh cho OCR
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    gray = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1]

    try:
        text = pytesseract.image_to_string(gray, lang="vie")
        print("📄 Kết quả OCR:")
        print(text)
    except Exception as e:
        print(f"❌ Lỗi OCR: {e}")
