# test_password_check_final.py
# PHIÊN BẢN HOÀN CHỈNH: Sử dụng WebDriverWait để xử lý form được tải bằng JavaScript
# mà không cần logic iframe.

import sys
import time
from selenium import webdriver
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
from webdriver_manager.chrome import ChromeDriverManager

# --- Cấu hình ---
LOGIN_URL = "https://pay.bigbangthoikhong.vn/login?game_id=105"


def check_login_final(email: str, password: str) -> tuple[bool, str]:
    """
    Sử dụng Selenium với cơ chế chờ đợi thông minh (WebDriverWait) để tương tác
    với các phần tử được tạo ra bởi JavaScript.
    """
    print("\nKhởi tạo trình duyệt Chrome (chế độ hiển thị)...")

    chrome_options = webdriver.ChromeOptions()
    chrome_options.add_argument("--start-maximized")
    chrome_options.add_argument("--log-level=3")
    chrome_options.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36")
    chrome_options.add_experimental_option("excludeSwitches", ["enable-logging"])

    driver = None
    try:
        print("Đang cài đặt/cập nhật chromedriver...")
        service = ChromeService(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=chrome_options)

        print(f"Bước 1: Đang mở trang đăng nhập: {LOGIN_URL}")
        driver.get(LOGIN_URL)

        # (BƯỚC QUAN TRỌNG) Khởi tạo WebDriverWait
        # Kịch bản sẽ chờ tối đa 20 giây cho mỗi phần tử
        wait = WebDriverWait(driver, 20)

        # (LOGIC MỚI) Chờ cho đến khi ô email HIỂN THỊ trên màn hình
        print("Bước 2: Chờ và điền thông tin email, mật khẩu...")
        # Dựa theo HTML, tên của ô input là "username"
        email_field = wait.until(EC.visibility_of_element_located((By.NAME, "username")))

        # Sau khi ô email xuất hiện, ô password chắc chắn cũng đã có mặt
        password_field = driver.find_element(By.NAME, "password")

        email_field.clear()
        email_field.send_keys(email)

        password_field.clear()
        password_field.send_keys(password)
        time.sleep(0.5)

        print("Bước 3: Nhấn nút 'Đăng Nhập'...")
        # Tìm nút submit bên trong form
        login_button = driver.find_element(By.CSS_SELECTOR, "form button[type='submit']")
        login_button.click()

        print("Bước 4: Đang chờ phản hồi từ server...")

        # Chờ cho đến khi URL thay đổi và không còn chứa "login" nữa
        wait.until(lambda d: "login" not in d.current_url.lower())

        final_url = driver.current_url
        print(f"-> URL cuối cùng: {final_url}")

        # Dựa vào URL cuối cùng để kết luận
        if "rechargepackage" in final_url.lower():
            return True, "✅ XÁC THỰC THÀNH CÔNG! Đã đăng nhập và chuyển hướng thành công."
        else:
            return False, f"❌ XÁC THỰC THẤT BẠI: Chuyển hướng đến trang không mong đợi: {final_url}"

    except TimeoutException:
        # Lỗi này có thể xảy ra ở 2 giai đoạn:
        # 1. Chờ ô email: trang tải quá chậm hoặc có lỗi.
        # 2. Chờ chuyển trang sau khi login: thông tin đăng nhập sai.
        try:
            page_source = driver.page_source.lower()
            if "sai mật khẩu" in page_source or "incorrect password" in page_source:
                return False, "❌ XÁC THỰC THẤT BẠI: Thông tin đăng nhập không chính xác."
        except:
            pass  # Bỏ qua nếu không đọc được page_source

        return False, "❌ LỖI HẾT THỜI GIAN CHỜ. Trang web không phản hồi như mong đợi. Vui lòng thử lại."
    except Exception as e:
        return False, f"❌ LỖI BẤT NGỜ: Chi tiết lỗi:\n{e}"
    finally:
        if driver:
            driver.quit()
            print("Đã đóng trình duyệt.")


if __name__ == "__main__":
    print("--- KỊCH BẢN KIỂM TRA XÁC THỰC BẰNG SELENIUM (FINAL) ---")
    if len(sys.argv) == 3:
        game_email, game_password = sys.argv[1], sys.argv[2]
        print(f"Đang kiểm tra với Email: {game_email}")
    else:
        game_email = input("Nhập email game cần kiểm tra: ").strip()
        game_password = input("Nhập mật khẩu game: ").strip()

    if not game_email or not game_password:
        print("\nEmail và mật khẩu không được để trống. Kết thúc.")
    else:
        success, message = check_login_final(game_email, game_password)
        print("\n" + "=" * 50)
        print("KẾT QUẢ KIỂM TRA:")
        print(message)
        print("=" * 50)