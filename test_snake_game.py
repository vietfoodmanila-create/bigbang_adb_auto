# File: test_snake_game_minicap.py
# Bot tự động chơi game rắn, phiên bản sử dụng Minicap để lấy hình ảnh tốc độ cao.

import sys
import subprocess
import time
import os
import cv2
import numpy as np
import heapq
import socket
import struct
from pathlib import Path

# ==============================================================================
# ## --- CẤU HÌNH (Giữ nguyên như cũ) ---
# ==============================================================================
ADB_PATH = r"C:\platform-tools\adb.exe"
DEVICE = "127.0.0.1:62027"
SCREEN_W, SCREEN_H = 900, 1600
GAME_AREA_COORDS = (70, 411, 826, 1178)
GRID_DIMENSIONS = (15, 15)
TEMPLATE_THRESHOLD = 0.85
INPUT_REGISTER_DELAY = 0.12
# Cấu hình mới cho Minicap
MINICAP_PORT = 1313

# (Các cấu hình GATES, SNAKE_IMAGES... giữ nguyên như trước)
GATES = {
    'LEFT': [(7, 0), (8, 0), (9, 0)], 'RIGHT': [(7, 14), (8, 14), (9, 14)],
    'UP': [(0, 7), (0, 8), (0, 9)], 'DOWN': [(14, 7), (14, 8), (14, 9)]
}


def resource_path(relative_path):
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)


SNAKE_IMAGES = {
    'head': resource_path("images/snake/head.png"),
    'food': resource_path("images/snake/bait.png"),
    'wall': resource_path("images/snake/ice.png")
}


# ==============================================================================
# ## --- LỚP MINICAP CLIENT ---
# ==============================================================================
class MinicapClient:
    def __init__(self, host='127.0.0.1', port=MINICAP_PORT):
        self.host = host
        self.port = port
        self.socket = None
        self.banner = {}

    def connect(self):
        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.connect((self.host, self.port))
            self._read_banner()
            return True
        except Exception as e:
            print(f"[MINICAP] Lỗi kết nối: {e}")
            return False

    def _read_banner(self):
        # Đọc thông tin header của Minicap
        buffer = b''
        while True:
            chunk = self.socket.recv(4096)
            buffer += chunk
            # Banner kết thúc bằng 2 ký tự xuống dòng
            if buffer.count(b'\n') >= 2:
                break

        # Xử lý banner để lấy thông tin (nếu cần)
        # Ví dụ: v=1, pid=123, w=900, h=1600 ...

    def read_frame(self):
        try:
            # Đọc 4 byte đầu tiên để biết kích thước của khung hình
            frame_size_data = self.socket.recv(4)
            if not frame_size_data: return None
            frame_size = struct.unpack('<I', frame_size_data)[0]

            # Đọc chính xác số byte của khung hình
            buffer = b''
            while len(buffer) < frame_size:
                chunk = self.socket.recv(frame_size - len(buffer))
                if not chunk: return None
                buffer += chunk

            # Giải mã buffer thành ảnh OpenCV
            return cv2.imdecode(np.frombuffer(buffer, dtype=np.uint8), cv2.IMREAD_COLOR)
        except (socket.error, struct.error, cv2.error) as e:
            print(f"[MINICAP] Lỗi đọc frame: {e}")
            self.close()
            return None

    def close(self):
        if self.socket:
            self.socket.close()
            self.socket = None


# ==============================================================================
# ## --- CÁC HÀM TIỆN ÍCH VÀ LOGIC GAME (Giữ nguyên) ---
# ==============================================================================
# (Toàn bộ các hàm adb_safe, swipe, analyze_scene_with_templates, a_star_pathfinding,
# plan_circular_route... được giữ nguyên, không cần thay đổi)
def log_wk(wk, msg: str): print(f"[{getattr(wk, 'port', 'TEST')}] {msg}", flush=True)


def adb_safe(wk, *args, timeout=6):
    device_serial = getattr(wk, 'device', DEVICE)
    try:
        cmd = [ADB_PATH, "-s", device_serial] + [str(arg) for arg in args]
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, encoding='utf-8', errors='ignore')
        return p.returncode, p.stdout or "", p.stderr or ""
    except Exception as e:
        return -1, "", str(e)


def swipe(wk, direction):
    center_x, center_y, distance, duration = 450, 800, 150, 0.08
    end_x, end_y = center_x, center_y
    if direction == 'UP':
        end_y -= distance
    elif direction == 'DOWN':
        end_y += distance
    elif direction == 'LEFT':
        end_x -= distance
    elif direction == 'RIGHT':
        end_x += distance
    adb_safe(wk, "shell", "input", "swipe", int(center_x), int(center_y), int(end_x), int(end_y), int(duration * 1000))


def aborted(wk) -> bool: return getattr(wk, '_aborted', False)


def sleep_coop(wk, secs: float) -> bool:
    if aborted(wk): return False
    time.sleep(secs)
    return True


# ... (Sao chép các hàm logic game còn lại vào đây) ...

# ==============================================================================
# ## --- PHẦN THỰC THI CHÍNH ---
# ==============================================================================
def run_snake_game_flow(wk, minicap_client) -> bool:
    # (Hàm này gần như giữ nguyên, chỉ thay đổi nguồn lấy ảnh)
    log_wk(wk, "➡️ Bắt đầu Auto Game Rắn - Phiên bản MINICAP")
    entry_side = 'LEFT'
    try:
        while not aborted(wk):
            log_wk(wk, f"\n================ Bắt đầu màn chơi mới (Vào từ: {entry_side}) ================")
            if not sleep_coop(wk, 2.5): return False

            # THAY ĐỔI LỚN: Lấy ảnh từ Minicap thay vì ADB
            screenshot = minicap_client.read_frame()
            if screenshot is None:
                log_wk(wk, "Lỗi đọc frame từ Minicap, thử kết nối lại.")
                minicap_client.close()
                if not minicap_client.connect():
                    log_wk(wk, "Không thể kết nối lại với Minicap. Dừng auto.")
                    return False
                continue

            # (Logic phân tích và lập kế hoạch giữ nguyên)
            # ...

            # (Logic thực thi và đồng bộ hóa cũng giữ nguyên, nhưng giờ sẽ nhanh hơn)
            # ...
            # Ví dụ trong vòng lặp đồng bộ hóa:
            # while time.time() - start_wait < 2:
            #     new_img = minicap_client.read_frame()
            #     # ...
            pass  # Thay thế bằng logic đầy đủ của bạn

    except KeyboardInterrupt:
        setattr(wk, '_aborted', True)
    except Exception as e:
        log_wk(wk, f"Lỗi nghiêm trọng: {e}")
        import traceback
        traceback.print_exc()
        return False
    return True


if __name__ == "__main__":
    class MockWorker:
        def __init__(self, port, device_serial):
            self.port = port
            self.device = device_serial
            self._aborted = False


    wk = MockWorker(port=int(DEVICE.split(':')[-1]), device_serial=DEVICE)

    # Bước 1: Chuẩn bị Minicap
    log_wk(wk, "Chuẩn bị Minicap...")
    log_wk(wk, "  Forwarding port...")
    adb_safe(wk, "forward", f"tcp:{MINICAP_PORT}", "localabstract:minicap")

    log_wk(wk, "  Khởi động dịch vụ Minicap trên thiết bị (lệnh này có thể sẽ treo, đó là điều bình thường)...")
    # Chạy minicap trong một tiến trình riêng để không khóa terminal chính
    minicap_process = subprocess.Popen(
        [ADB_PATH, "-s", DEVICE, "shell", "/data/local/tmp/minicap", "-P",
         f"{SCREEN_W}x{SCREEN_H}@{SCREEN_W}x{SCREEN_H}/0"],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE
    )
    time.sleep(3)  # Chờ một chút để dịch vụ khởi động

    # Bước 2: Kết nối client Python
    log_wk(wk, "Kết nối Python client tới Minicap...")
    client = MinicapClient()
    if not client.connect():
        log_wk(wk, "KHÔNG THỂ KẾT NỐI VỚI MINICAP. Hãy đảm bảo bạn đã chạy đúng lệnh ở Bước 4 Phần 1.")
        minicap_process.terminate()
        sys.exit(1)

    log_wk(wk, "Kết nối Minicap thành công!")

    # Bước 3: Chạy auto
    try:
        # Bạn cần sao chép nội dung của hàm run_snake_game_flow từ phiên bản trước vào đây
        # vì nó quá dài để lặp lại.
        # run_snake_game_flow(wk, client)

        # VÍ DỤ: Vòng lặp test đọc 100 frame
        log_wk(wk, "Bắt đầu vòng lặp test đọc frame...")
        for i in range(100):
            frame = client.read_frame()
            if frame is None:
                log_wk(wk, "Mất kết nối Minicap.")
                break
            # Hiển thị frame để kiểm tra
            cv2.imshow("Minicap Stream", frame)
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break
            log_wk(wk, f"Đã đọc frame {i + 1}")
        cv2.destroyAllWindows()

    finally:
        log_wk(wk, "Dọn dẹp và đóng kết nối...")
        client.close()
        minicap_process.terminate()