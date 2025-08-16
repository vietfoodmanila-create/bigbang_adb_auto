# -*- coding: utf-8 -*-
import sys
import subprocess
import csv
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Dict

from PySide6.QtCore import Qt, QPoint
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QSplitter, QVBoxLayout, QHBoxLayout,
    QTableWidget, QTableWidgetItem, QHeaderView, QCheckBox,
    QTabWidget, QGroupBox, QFormLayout, QTextEdit, QLabel, QMessageBox, QPushButton,
    QAbstractItemView, QMenu
)

# ====== Cấu hình ======
ADB_PATH = Path(r"D:\Program Files\Nox\bin\adb.exe")  # chỉnh đúng adb.exe của Nox
DATA_ROOT = Path("data")
DATA_ROOT.mkdir(exist_ok=True)

DEFAULT_WIDTH = 460
DEFAULT_HEIGHT = 920

ACC_HEADERS_VISIBLE = ["Email", "Password", "Server", "Date(YYYYMMDD)"]
ACC_COL_EMAIL, ACC_COL_PASS, ACC_COL_SERVER, ACC_COL_DATE = range(4)


@dataclass
class NoxInstance:
    port: int
    status: str  # online/offline


# ---------------- Helpers ----------------
def _run_quiet(cmd: list[str], timeout: int = 8) -> str:
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return out.stdout
    except Exception:
        return ""


def list_adb_ports_with_status() -> dict[int, str]:
    """
    Đọc tất cả cổng hiện trong `adb devices` và trả {port: adb_status}
    adb_status: 'device' | 'offline' | 'unauthorized' | ...
    """
    text = ""
    if ADB_PATH.exists():
        text = _run_quiet([str(ADB_PATH), "devices"], timeout=6)
    if not text:
        text = _run_quiet(["adb", "devices"], timeout=6)

    result: dict[int, str] = {}
    for line in text.splitlines():
        s = line.strip()
        if not s or s.startswith("List of devices"):
            continue
        if s.startswith("127.0.0.1:"):
            parts = s.split()
            try:
                port = int(parts[0].split(":")[1])
                status = parts[1] if len(parts) > 1 else "unknown"
                result[port] = status
            except Exception:
                pass
    return result


def list_known_ports_from_data() -> List[int]:
    """Các thư mục data/<port>/ đã có."""
    ports: List[int] = []
    for p in DATA_ROOT.iterdir():
        if p.is_dir():
            try:
                ports.append(int(p.name))
            except Exception:
                pass
    return ports


def read_accounts_6cols(path: Path) -> List[List[str]]:
    """
    Đọc accounts với 6 cột:
      0 email, 1 password, 2 server, 3 date(yyyymmdd), 4 status, 5 last_leave(yyyymmdd:hhmm)
    Tự bù đủ 6 cột nếu thiếu.
    """
    rows: List[List[str]] = []
    if not path.exists():
        return rows
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or "," not in line:
                continue
            parts = [p.strip() for p in line.split(",")]
            while len(parts) < 6:
                parts.append("")
            rows.append(parts[:6])
    return rows


def write_accounts_6cols(path: Path, rows6: List[List[str]]) -> None:
    """
    Ghi danh sách 6 cột theo đúng thứ tự:
      email, pwd, server, date, status, last_leave
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        for r in rows6:
            row = list(r[:6])
            while len(row) < 6:
                row.append("")
            w.writerow(row)


# ---------------- Main Window ----------------
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("BigBang ADB Auto")
        self.resize(DEFAULT_WIDTH, DEFAULT_HEIGHT)
        self.setMinimumSize(420, 760)

        self.active_port: Optional[int] = None

        splitter = QSplitter(Qt.Vertical, self)
        self.setCentralWidget(splitter)

        # ===== TOP: NOX TABLE =====
        top = QWidget()
        top_layout = QVBoxLayout(top)

        self.tbl_nox = QTableWidget(0, 5)
        self.tbl_nox.setHorizontalHeaderLabels(
            ["Start", "Tên máy ảo", "ADB Port", "Trạng thái", "Status"]
        )
        self.tbl_nox.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.tbl_nox.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.tbl_nox.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.tbl_nox.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.tbl_nox.horizontalHeader().setSectionResizeMode(4, QHeaderView.Stretch)
        # Chỉ cho phép chọn 1 hàng
        self.tbl_nox.setSelectionMode(QAbstractItemView.SingleSelection)
        self.tbl_nox.setSelectionBehavior(QTableWidget.SelectRows)
        # Chặn sửa nội dung (trừ checkbox cột 0)
        self.tbl_nox.setEditTriggers(QAbstractItemView.NoEditTriggers)

        # Chuột phải
        self.tbl_nox.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tbl_nox.customContextMenuRequested.connect(self._show_nox_context_menu)

        top_layout.addWidget(self.tbl_nox)
        splitter.addWidget(top)

        # ===== BOTTOM: Tabs + Log =====
        bottom = QWidget()
        bottom_layout = QVBoxLayout(bottom)
        self.tabs = QTabWidget()

        # Tab Accounts
        w_acc = QWidget()
        acc_layout = QVBoxLayout(w_acc)
        self.tbl_acc = QTableWidget(0, len(ACC_HEADERS_VISIBLE))
        self.tbl_acc.setHorizontalHeaderLabels(ACC_HEADERS_VISIBLE)
        self.tbl_acc.horizontalHeader().setSectionResizeMode(ACC_COL_EMAIL, QHeaderView.Stretch)
        self.tbl_acc.horizontalHeader().setSectionResizeMode(ACC_COL_PASS, QHeaderView.ResizeToContents)
        self.tbl_acc.horizontalHeader().setSectionResizeMode(ACC_COL_SERVER, QHeaderView.ResizeToContents)
        self.tbl_acc.horizontalHeader().setSectionResizeMode(ACC_COL_DATE, QHeaderView.ResizeToContents)
        self.tbl_acc.setColumnWidth(ACC_COL_PASS, 120)
        self.tbl_acc.setColumnWidth(ACC_COL_SERVER, 60)
        self.tbl_acc.setColumnWidth(ACC_COL_DATE, 98)

        acc_btns = QHBoxLayout()
        self.btn_acc_add = QPushButton("Thêm hàng")
        self.btn_acc_del = QPushButton("Xoá hàng")
        self.btn_acc_load = QPushButton("Load")
        self.btn_acc_save = QPushButton("Save")
        acc_btns.addWidget(self.btn_acc_add)
        acc_btns.addWidget(self.btn_acc_del)
        acc_btns.addStretch(1)
        acc_btns.addWidget(self.btn_acc_load)
        acc_btns.addWidget(self.btn_acc_save)
        acc_layout.addWidget(self.tbl_acc)
        acc_layout.addLayout(acc_btns)
        self.tabs.addTab(w_acc, "Accounts")

        # Tab Features
        w_feat = QWidget()
        feat_layout = QVBoxLayout(w_feat)
        grp = QGroupBox("Chọn tính năng")
        form = QFormLayout(grp)
        self.chk_build = QCheckBox("Xây dựng liên minh / xem quảng cáo")
        self.chk_expedition = QCheckBox("Viễn chinh")
        self.chk_auto_leave = QCheckBox("Tự thoát liên minh sau khi thao tác xong")
        self.chk_bless = QCheckBox("Chúc phúc")
        form.addRow(self.chk_build)
        form.addRow(self.chk_expedition)
        form.addRow(self.chk_auto_leave)
        form.addRow(self.chk_bless)
        feat_layout.addWidget(grp)
        feat_layout.addStretch(1)
        self.tabs.addTab(w_feat, "Tính năng")

        bottom_layout.addWidget(self.tabs)
        bottom_layout.addWidget(QLabel("Log:"))
        self.log = QTextEdit()
        self.log.setReadOnly(True)
        bottom_layout.addWidget(self.log, 1)

        splitter.addWidget(bottom)
        splitter.setSizes([380, 540])

        # chọn Nox → load accounts
        self.tbl_nox.itemSelectionChanged.connect(self.on_nox_selection_changed)

        # init
        self.refresh_nox()
        if self.tbl_nox.rowCount() > 0:
            self.tbl_nox.selectRow(0)
            self.on_nox_selection_changed()

        # buttons Accounts
        self.btn_acc_add.clicked.connect(self.acc_add)
        self.btn_acc_del.clicked.connect(self.acc_del)
        self.btn_acc_load.clicked.connect(self.load_accounts_current_port)
        self.btn_acc_save.clicked.connect(self.save_accounts_current_port)

    # ---------- NOX TABLE ----------
    def refresh_nox(self):
        """
        Hiển thị:
        - TẤT CẢ port có trong `adb devices` (kể cả offline/unauthorized)
        - Cộng thêm các port có thư mục data/<port>/
        """
        adb_map = list_adb_ports_with_status()     # {port: 'device'|'offline'|'unauthorized'|...}
        online_ports = {p for p, st in adb_map.items() if st == "device"}
        known = set(list_known_ports_from_data())
        all_ports = sorted(set(adb_map.keys()) | known)

        self.tbl_nox.setRowCount(0)
        for port in all_ports:
            name = f"Nox({port})"
            r = self.tbl_nox.rowCount()
            self.tbl_nox.insertRow(r)

            # cột 0: checkbox Start
            chk = QCheckBox()
            chk.setChecked(False)
            self.tbl_nox.setCellWidget(r, 0, chk)

            # các cột còn lại: read-only
            items = [
                QTableWidgetItem(name),                         # cột 1
                QTableWidgetItem(str(port)),                    # cột 2
                QTableWidgetItem("online" if port in online_ports else "offline"),  # cột 3
                QTableWidgetItem("IDLE"),                       # cột 4
            ]
            for i, it in enumerate(items, start=1):
                it.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
                if i in (2, 3):
                    it.setTextAlignment(Qt.AlignCenter)
                self.tbl_nox.setItem(r, i, it)

    def get_current_port(self) -> Optional[int]:
        row = self.tbl_nox.currentRow()
        if row < 0:
            return None
        it = self.tbl_nox.item(row, 2)
        return int(it.text()) if it else None

    def accounts_path_for_port(self, port: int) -> Path:
        d = DATA_ROOT / str(port)
        d.mkdir(parents=True, exist_ok=True)
        return d / "accounts.txt"

    def on_nox_selection_changed(self):
        port = self.get_current_port()
        self.active_port = port
        if port is None:
            self.tbl_acc.setRowCount(0)
            self.log_msg("Chưa chọn Nox.")
            return
        path = self.accounts_path_for_port(port)
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("", encoding="utf-8")
            self.log_msg(f"Tạo mới {path}")
        self.load_accounts_for_port(port)

    # ---------- Context menu: xóa máy ảo offline ----------
    def _show_nox_context_menu(self, pos: QPoint):
        index = self.tbl_nox.indexAt(pos)
        if not index.isValid():
            return
        row = index.row()
        status_item = self.tbl_nox.item(row, 3)
        status = status_item.text().strip() if status_item else ""
        port_item = self.tbl_nox.item(row, 2)
        port = int(port_item.text()) if port_item else None

        menu = QMenu(self)
        act_delete = menu.addAction("Xoá thông tin máy ảo (offline)")
        if status != "offline":
            act_delete.setEnabled(False)

        action = menu.exec(self.tbl_nox.viewport().mapToGlobal(pos))
        if action == act_delete and port is not None:
            self._delete_offline_instance(row, port)

    def _delete_offline_instance(self, row: int, port: int):
        ret = QMessageBox.question(
            self, "Xác nhận",
            f"Xoá thông tin máy ảo offline cho port {port}?\n"
            f"Thao tác sẽ xoá thư mục: {DATA_ROOT / str(port)}",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        if ret != QMessageBox.Yes:
            return

        folder = DATA_ROOT / str(port)
        try:
            if folder.exists():
                for p in folder.glob("*"):
                    try: p.unlink()
                    except Exception: pass
                folder.rmdir()
            self.tbl_nox.removeRow(row)
            self.log_msg(f"Đã xoá thông tin máy ảo offline port {port}.")
        except Exception as e:
            QMessageBox.warning(self, "Lỗi", f"Không xoá được: {e}")

        if self.tbl_nox.rowCount() > 0:
            self.tbl_nox.selectRow(0)
            self.on_nox_selection_changed()
        else:
            self.tbl_acc.setRowCount(0)

    # ---------- ACCOUNTS ----------
    def load_accounts_for_port(self, port: int):
        path = self.accounts_path_for_port(port)
        rows6 = read_accounts_6cols(path)

        self.tbl_acc.setRowCount(0)
        for r6 in rows6:
            email, pwd, server, date, _status, _last_leave = r6
            r = self.tbl_acc.rowCount()
            self.tbl_acc.insertRow(r)
            self.tbl_acc.setItem(r, ACC_COL_EMAIL, QTableWidgetItem(email))
            self.tbl_acc.setItem(r, ACC_COL_PASS, QTableWidgetItem(pwd))
            s_item = QTableWidgetItem(server); s_item.setTextAlignment(Qt.AlignCenter)
            d_item = QTableWidgetItem(date);   d_item.setTextAlignment(Qt.AlignCenter)
            self.tbl_acc.setItem(r, ACC_COL_SERVER, s_item)
            self.tbl_acc.setItem(r, ACC_COL_DATE, d_item)

        self.log_msg(f"Loaded {len(rows6)} accounts từ {path}")

    def collect_accounts_visible4(self) -> List[List[str]]:
        rows4: List[List[str]] = []
        for r in range(self.tbl_acc.rowCount()):
            row = []
            for c in range(self.tbl_acc.columnCount()):
                it = self.tbl_acc.item(r, c)
                row.append(it.text().strip() if it else "")
            if any(row):
                while len(row) < 4:
                    row.append("")
                rows4.append(row[:4])
        return rows4

    def save_accounts_for_port(self, port: int):
        """
        Lưu bảng 4 cột về file 6 cột:
          - Giữ nguyên 'status' và 'last_leave' của email đã có trong file (nếu tồn tại).
          - Với email mới: status="1", last_leave="" (rỗng).
        """
        path = self.accounts_path_for_port(port)
        rows4 = self.collect_accounts_visible4()

        # đọc hiện trạng cũ (để giữ status & last_leave)
        old6 = read_accounts_6cols(path)
        old_map: Dict[str, List[str]] = {r[0].strip(): r for r in old6 if r and r[0].strip()}

        rows6: List[List[str]] = []
        for email, pwd, server, date in rows4:
            if not email:
                continue
            status = old_map.get(email, ["","","","", "1", ""])[4] or "1"
            last_leave = old_map.get(email, ["","","","","",""])[5] or ""
            rows6.append([email, pwd, server, date, status, last_leave])

        write_accounts_6cols(path, rows6)
        self.log_msg(f"Saved {len(rows6)} accounts → {path}")

    def load_accounts_current_port(self):
        if self.active_port is None:
            QMessageBox.information(self, "Chú ý", "Chọn một Nox ở bảng trên trước.")
            return
        self.load_accounts_for_port(self.active_port)

    def save_accounts_current_port(self):
        if self.active_port is None:
            QMessageBox.information(self, "Chú ý", "Chọn một Nox ở bảng trên trước.")
            return
        self.save_accounts_for_port(self.active_port)

    def acc_add(self):
        r = self.tbl_acc.rowCount()
        self.tbl_acc.insertRow(r)

    def acc_del(self):
        rows = sorted({i.row() for i in self.tbl_acc.selectedIndexes()}, reverse=True)
        for r in rows:
            self.tbl_acc.removeRow(r)

    # ---------- Log ----------
    def log_msg(self, msg: str):
        self.log.append(msg)
        self.log.ensureCursorVisible()


def main():
    app = QApplication(sys.argv)
    w = MainWindow()
    w.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
