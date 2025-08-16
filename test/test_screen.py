# tests/test_screen.py
from adb_utils import ensure_connected
from screen_utils import screencap_cv, save_png

if __name__ == "__main__":
    ensure_connected()
    img = screencap_cv()
    print("shape:", img.shape)  # kỳ vọng (1600, 900, 3)
    save_png(img, "screen.png")
    print("✅ saved screen.png")
