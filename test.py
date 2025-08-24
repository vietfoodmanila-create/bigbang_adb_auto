# test_image_processing.py
import time
from minicap_manager import MinicapManager
from module import find_on_frame, resource_path
from checkbox_actions import SimpleNoxWorker
from config import PLATFORM_TOOLS_ADB_PATH

# ----- CẤU HÌNH TEST -----
# Thay thế bằng ID của máy ảo bạn muốn test
TARGET_DEVICE_ID = "emulator-5554"
# Đường dẫn đến một ảnh mẫu bất kỳ để thử tìm kiếm
# Chúng ta sẽ dùng ảnh nút login làm ví dụ
TEMPLATE_IMAGE_PATH = resource_path("images/login/game_login_button.png")


# -------------------------

def run_processing_test():
    """
    Kịch bản test tập trung vào việc đọc frame và tìm kiếm ảnh ngay lập tức
    để xác định nguyên nhân gây crash.
    """
    print("--- BẮT ĐẦU KIỂM TRA ĐỌC VÀ TÌM KIẾM ẢNH ---")
    print(f"Thiết bị mục tiêu: {TARGET_DEVICE_ID}")

    worker = SimpleNoxWorker(
        adb_path=PLATFORM_TOOLS_ADB_PATH,
        device_id=TARGET_DEVICE_ID,
        log_cb=print
    )
    minicap = MinicapManager(worker)

    if not minicap.setup() or not minicap.start_stream():
        print("\n--- KẾT QUẢ: THẤT BẠI ---")
        print("Không thể khởi động Minicap.")
        return

    print("\n✅ MINICAP ĐÃ SẴN SÀNG. Bắt đầu vòng lặp đọc và tìm kiếm...")
    print("Nhấn Ctrl+C trong cửa sổ terminal để dừng test.")

    test_count = 0
    success_count = 0

    try:
        while True:
            test_count += 1
            frame = minicap.get_frame()

            if frame is None:
                print(f"[{test_count}] Lỗi: Không nhận được frame. Tạm dừng 1 giây.")
                time.sleep(1)
                continue

            # Thực hiện thao tác tìm kiếm ngay lập tức
            ok, pos, score = find_on_frame(frame, TEMPLATE_IMAGE_PATH, threshold=0.7)

            if ok:
                print(f"[{test_count}] OK: Đã đọc frame và tìm thấy ảnh mẫu tại {pos} (score={score:.2f})")
            else:
                print(f"[{test_count}] OK: Đã đọc frame, không tìm thấy ảnh mẫu (score={score:.2f})")

            success_count += 1
            time.sleep(0.1)  # Thêm một khoảng nghỉ nhỏ

    except KeyboardInterrupt:
        print("\nĐã nhận lệnh dừng từ người dùng.")
    except Exception as e:
        print(f"\n--- GẶP LỖI BẤT NGỜ ---: {e}")
    finally:
        print("\nĐang dọn dẹp và đóng kết nối...")
        minicap.teardown()
        print("\n--- KIỂM TRA KẾT THÚC ---")
        print(f"Tổng cộng đã thực hiện thành công: {success_count} lần đọc và tìm kiếm.")


if __name__ == "__main__":
    run_processing_test()