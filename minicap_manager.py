# minicap_manager.py (Phiên bản cuối cùng, sử dụng cơ chế chờ và thử lại ổn định)
import socket
import struct
import subprocess
import time
from pathlib import Path
import threading

import cv2
import numpy as np

from module import resource_path


class MinicapManager:
    """Quản lý toàn bộ vòng đời của Minicap, có cơ chế dọn dẹp và khởi động bền bỉ."""

    def __init__(self, worker):
        self.wk = worker
        self.device_id = worker.device_id
        self.minicap_process = None
        self.client_socket = None
        self.banner = {}
        try:
            self.port = 1717 + int(''.join(filter(str.isdigit, self.device_id))) % 1000
        except ValueError:
            self.port = 1717
        self.read_lock = threading.Lock()

    def _force_cleanup_on_device(self):
        self.wk._log("Đang tìm và dọn dẹp các tiến trình Minicap cũ trên thiết bị...")
        try:
            _, pid_str, _ = self.wk.adb("shell", "pidof", "minicap")
            pids = pid_str.strip().split()
            if pids:
                for pid in pids:
                    if pid.isdigit():
                        self.wk._log(f"  -> Tìm thấy và tiêu diệt tiến trình Minicap cũ có PID: {pid}")
                        self.wk.adb("shell", "kill", "-9", pid)
            else:
                self.wk._log("Không tìm thấy tiến trình Minicap cũ nào.")
        except Exception as e:
            self.wk._log(f"Lỗi khi dọn dẹp tiến trình Minicap cũ: {e}")

    def setup(self) -> bool:
        try:
            self.wk._log("Bắt đầu thiết lập Minicap...")
            _, abi, _ = self.wk.adb("shell", "getprop", "ro.product.cpu.abi")
            abi = abi.strip()
            _, sdk, _ = self.wk.adb("shell", "getprop", "ro.build.version.sdk")
            sdk = sdk.strip()
            if not abi or not sdk: return False
            self.wk._log(f"Thông tin thiết bị: ABI={abi}, SDK={sdk}")
            minicap_bin_path = resource_path(f"vendor/minicap/bin/{abi}/minicap")
            minicap_so_path = resource_path(f"vendor/minicap/lib/android-{sdk}/{abi}/minicap.so")
            if not Path(minicap_bin_path).exists() or not Path(minicap_so_path).exists():
                self.wk._log(f"Lỗi: Không tìm thấy file minicap hoặc minicap.so phù hợp cho ABI={abi}, SDK={sdk}.")
                return False
            self.wk.adb("push", minicap_bin_path, "/data/local/tmp/minicap")
            self.wk.adb("push", minicap_so_path, "/data/local/tmp/minicap.so")
            self.wk.adb("shell", "chmod", "755", "/data/local/tmp/minicap")
            self.wk._log("Thiết lập Minicap thành công.")
            return True
        except Exception as e:
            self.wk._log(f"Lỗi nghiêm trọng khi thiết lập Minicap: {e}")
            return False

    def start_stream(self) -> bool:
        """Khởi động Minicap và kết nối bằng cơ chế chờ và thử lại."""
        try:
            self._force_cleanup_on_device()
            self.wk.adb("forward", "--remove-all")

            self.wk._log("Đang khởi động stream Minicap...")

            _, size_str, _ = self.wk.adb("shell", "wm", "size")
            real_size_str = size_str.strip().split(' ')[-1]
            if not real_size_str or 'x' not in real_size_str: return False

            real_w, real_h = map(int, real_size_str.split('x'))
            scaled_w = (real_w // 2) // 2 * 2
            scaled_h = (real_h // 2) // 2 * 2
            scaled_size_str = f"{scaled_w}x{scaled_h}"

            self.wk._log(f"Stream sẽ được tối ưu hóa ở độ phân giải: {scaled_size_str} (gốc: {real_size_str})")

            self.wk.adb("forward", f"tcp:{self.port}", "localabstract:minicap")

            command = (f"LD_LIBRARY_PATH=/data/local/tmp "
                       f"/data/local/tmp/minicap -P {real_size_str}@{scaled_size_str}/0 -Q 90")

            creationflags = 0
            if hasattr(subprocess, 'CREATE_NO_WINDOW'):
                creationflags = subprocess.CREATE_NO_WINDOW

            self.minicap_process = subprocess.Popen(
                [self.wk._adb, "-s", self.device_id, "shell", command],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                creationflags=creationflags
            )

            # ***CƠ CHẾ MỚI: CHỜ CỐ ĐỊNH VÀ THỬ KẾT NỐI LẠI***
            self.wk._log("Đã gửi lệnh khởi động, chờ 3 giây để Minicap sẵn sàng...")
            time.sleep(3.0)

            for i in range(5):  # Thử kết nối 5 lần
                try:
                    self.client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    self.client_socket.connect(("127.0.0.1", self.port))
                    self._read_banner()
                    self.wk._log("Kết nối Minicap thành công!")
                    return True
                except Exception as connect_error:
                    self.wk._log(f"Kết nối lần {i + 1} thất bại, thử lại sau 1s...")
                    time.sleep(1.0)

            self.wk._log("Lỗi: Không thể kết nối tới socket của Minicap sau nhiều lần thử.")
            self.teardown()
            return False

        except Exception as e:
            self.wk._log(f"Lỗi khi khởi động stream Minicap: {e}")
            self.teardown()
            return False

    def _read_banner(self):
        # (Nội dung không đổi)
        header = self.client_socket.recv(2)
        version = header[0]
        banner_length = header[1]
        if banner_length != 24:
            raise RuntimeError(f"Banner length không hợp lệ. Mong đợi 24, nhận được {banner_length}")
        banner_data = self.client_socket.recv(banner_length)
        (pid, real_width, real_height,
         virtual_width, virtual_height,
         orientation, quirks) = struct.unpack('<IIIIIBB', banner_data)
        self.banner = {
            'pid': pid, 'real_width': real_width, 'real_height': real_height,
            'virtual_width': virtual_width, 'virtual_height': virtual_height,
            'orientation': orientation * 90, 'quirks': quirks
        }
        self.wk._log(f"Banner Minicap: {self.banner}")

    def get_frame(self) -> np.ndarray | None:
        # (Nội dung không đổi)
        if not self.client_socket:
            return None
        with self.read_lock:
            try:
                frame_size_data = self.client_socket.recv(4)
                if not frame_size_data or len(frame_size_data) < 4:
                    return None
                frame_size = struct.unpack('<I', frame_size_data)[0]
                buffer = b''
                while len(buffer) < frame_size:
                    chunk = self.client_socket.recv(frame_size - len(buffer))
                    if not chunk: return None
                    buffer += chunk
                if not buffer.startswith(b'\xff\xd8') or not buffer.endswith(b'\xff\xd9'):
                    self.wk._log("Cảnh báo: Nhận được frame ảnh không hợp lệ. Bỏ qua.")
                    return None
                image = cv2.imdecode(np.frombuffer(buffer, dtype=np.uint8), cv2.IMREAD_COLOR)
                if image is not None:
                    return image.copy()
                else:
                    return None
            except (socket.error, struct.error):
                self.teardown()
                return None
            except Exception:
                self.teardown()
                return None

    def teardown(self):
        # (Nội dung không đổi)
        self.wk._log("Đang dọn dẹp Minicap...")
        self._force_cleanup_on_device()
        if self.client_socket:
            try:
                self.client_socket.close()
            except:
                pass
            self.client_socket = None
        if self.minicap_process:
            try:
                self.minicap_process.terminate()
            except:
                pass
            self.minicap_process = None
        try:
            self.wk.adb("forward", "--remove-all")
        except:
            pass
        self.wk._log("Dọn dẹp Minicap hoàn tất.")