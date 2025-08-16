# workers.py
from PyQt5.QtCore import QObject, pyqtSignal, QTimer
import threading, time, os

from flows_login import login_once
# (tuỳ bạn có muốn logout trước mỗi login hay không)
# from flows_logout import logout_once
from rescue_utils import logmsg

class AccountWorker(QObject):
    # account_id: thường là port hoặc tên máy ảo
    statusChanged = pyqtSignal(str, dict)   # account_id, {status: "OK/ERR/RUN/INIT/STOP", info: "..."}
    log = pyqtSignal(str)                   # log text cho UI (tuỳ dùng)

    def __init__(self, account_id: str, adb_client, parent=None):
        """
        adb_client: đối tượng có hàm run(*args, timeout=..)->(returncode, stdout_bytes, stderr_text)
                    để thỏa giao diện wk.adb(..) mà flows_* đang dùng
        """
        super().__init__(parent)
        self.account_id = account_id
        self._adb = adb_client

        self._running = False
        self._thread = None
        self._last_status = {"status": "INIT", "info": ""}

        # Timer chỉ để heartbeat UI, không xử lý nặng ở đây
        self._hb = QTimer(self)
        self._hb.setInterval(500)
        self._hb.timeout.connect(self._emit_status)

        # required by rescue_utils/flows_*
        self.game_package = getattr(adb_client, "game_package", None) or "your.game.pkg"
        self.game_activity = getattr(adb_client, "game_activity", None) or "your.game.pkg/.MainActivity"
        self.port = getattr(adb_client, "port", None) or account_id  # để logmsg hiện [port]

        # danh sách tài khoản cho vòng lặp
        self._accounts = []
        self._delay_between = 1.5  # nghỉ giữa 2 tài khoản

    # ===== Adapter cho rescue_utils / flows_* =====
    def adb(self, *args, timeout=4):
        """Giao diện bắt buộc để flows_* gọi. Ủy quyền sang self._adb.run()."""
        return self._adb.run(*args, timeout=timeout)

    def start_app(self, pkg, act):
        """Cho phép rescue_utils.restart_game() gọi nếu cần."""
        self.adb("shell", "am", "start", "-n", act,
                 "-a", "android.intent.action.MAIN",
                 "-c", "android.intent.category.LAUNCHER", timeout=8)

    # ===== Public API =====
    def load_accounts_from_file(self, path: str):
        """Đọc accounts dạng mỗi dòng: email|password"""
        accs = []
        try:
            with open(path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    parts = line.split("|", 1)
                    if len(parts) != 2:
                        continue
                    accs.append({"email": parts[0].strip(), "password": parts[1].strip()})
            self._accounts = accs
            self._last_status = {"status": "INIT", "info": f"Loaded {len(accs)} accounts"}
        except Exception as e:
            self._accounts = []
            self._last_status = {"status": "ERR", "info": f"Load accounts failed: {e}"}

    def start(self, delay_between=1.5):
        """Gọi khi checkbox ON."""
        if self._running:
            return
        self._delay_between = delay_between
        self._running = True
        self._hb.start()
        self._thread = threading.Thread(target=self._loop_login_list, daemon=True)
        self._thread.start()
        self._log(f"Bắt đầu chạy vòng lặp ({len(self._accounts)} tài khoản).")

    def stop(self):
        """Gọi khi checkbox OFF."""
        self._running = False
        self._hb.stop()
        self._log("Dừng vòng lặp.")

    def isRunning(self) -> bool:
        return self._running

    # ===== Nội bộ =====
    def _emit_status(self):
        self.statusChanged.emit(self.account_id, dict(self._last_status))

    def _log(self, msg: str):
        logmsg(self, msg)           # in console: [port] msg
        self.log.emit(f"[{self.account_id}] {msg}")  # cho UI (nếu dùng)

    def _loop_login_list(self):
        """Chạy lần lượt từng tài khoản: XONG HẲN 1 tài khoản mới sang tài khoản kế."""
        if not self._accounts:
            self._last_status = {"status": "ERR", "info": "No accounts loaded"}
            self._emit_status()
            return

        # chạy tuần tự: 0..n-1, rồi dừng (hoặc bạn muốn vòng lặp vô hạn thì while)
        for idx, acc in enumerate(self._accounts, start=1):
            if not self._running:
                break

            email = acc["email"]; password = acc["password"]
            self._last_status = {"status": "RUN", "info": f"{idx}/{len(self._accounts)} → {email}"}
            self._emit_status()

            try:
                ok = login_once(self, email=email, password=password, watchdog_deadline=15)
                self._last_status = {"status": "OK" if ok else "FAIL", "info": email}
                self._emit_status()
                self._log(f"Kết quả {email}: {ok}")
            except Exception as e:
                self._last_status = {"status": "ERR", "info": f"{email} | {e}"}
                self._emit_status()
                self._log(f"Lỗi khi login {email}: {e}")

            # nghỉ giữa 2 tài khoản (có thể bị dừng giữa chừng)
            t_end = time.time() + self._delay_between
            while self._running and time.time() < t_end:
                time.sleep(0.1)

        # xong danh sách → tự dừng (tuỳ nhu cầu bạn có thể để tiếp tục lặp lại)
        self._running = False
        self._hb.stop()
        self._last_status = {"status": "STOP", "info": "Done all accounts"}
        self._emit_status()
        self._log("Đã xử lý xong toàn bộ danh sách.")
