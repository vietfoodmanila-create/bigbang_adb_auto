# tests/test_match.py
from adb_utils import ensure_connected
from match_utils import wait_and_tap

if __name__ == "__main__":
    ensure_connected()

    # Đặt template đúng đường dẫn (ảnh cắt từ màn hình 900x1600)
    # ví dụ: images/login_button.png
    template_path = "../images/sample_button.png"

    ok, pos, score = wait_and_tap(template_path, timeout=8, thr=0.88)
    if ok:
        print(f"✅ Match & tap @ {pos}  (score={score:.3f})")
    else:
        print(f"❌ Không tìm thấy. Best score={score:.3f}")
