# tests/test_adb.py
from adb_utils import ensure_connected, tap, swipe, input_text, wm_size

if __name__ == "__main__":
    ensure_connected()
    print("WM:", wm_size())

    # Tap giữa màn (giả định 900x1600)
    tap(450, 800)
    print("✅ tap OK")

    # Vuốt thử nhẹ từ dưới lên
    swipe(450, 1200, 450, 800, 250)
    print("✅ swipe OK")

    # Gõ text thử (nếu đang ở ô nhập)
    # input_text("hello_world")
    # print("✅ input OK")
