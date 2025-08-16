# -*- coding: utf-8 -*-
from __future__ import annotations

import sys
import subprocess
import csv
import json  # <-- (THÊM) dùng cho chúc phúc
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Dict
import os
from PySide6.QtCore import Qt, QPoint
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QSplitter, QVBoxLayout, QHBoxLayout,
    QTableWidget, QTableWidgetItem, QHeaderView, QCheckBox,
    QTabWidget, QGroupBox, QFormLayout, QTextEdit, QLabel, QMessageBox, QPushButton,
    QAbstractItemView, QMenu, QLineEdit  # <-- (THÊM) QLineEdit cho cấu hình chúc phúc
)

# ====== Cấu hình ======
ADB_PATH = Path(r"D:\Program Files\Nox\bin\adb.exe")  # chỉnh đúng adb.exe của Nox
DATA_ROOT = Path("data")
DATA_ROOT.mkdir(exist_ok=True)

DEFAULT_WIDTH = 460
DEFAULT_HEIGHT = 920

ACC_HEADERS_VISIBLE = ["Email", "Password", "Server", "Date(YYYYMMDD)"]
ACC_COL_EMAIL, ACC_COL_PASS, ACC_COL_SERVER, ACC_COL_DATE = range(4)

# (THÊM) Cột bảng DS Chúc phúc
BLESS_HEADERS_VISIBLE = ["Tên nhân vật", "Lần cuối (yyyymmdd:hh)"]
BLESS_COL_NAME, BLESS_COL_LAST = range(2)
BLESS_MAX_ITEMS_RENDER = 20  # chỉ render tối đa 20 item cho gọn


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

def _normalize_line_to_8cols(parts):
    """
    Chuẩn hoá 1 dòng về 8 cột:
    0 email
    1 password
    2 server
    3 date (yyyymmdd) — dùng cho 'xây dựng' mỗi ngày 1 lần
    4 status
    5 last_leave (yyyymmdd:hhmm) — thời điểm rời liên minh
    6 vienchinh (yyyymmdd:hhmm) — thời điểm hoàn thành viễn chinh lần cuối
    7 chucphuc (yyyymmdd:int) — dự phòng, mặc định ''
    """
    parts = [p.strip() for p in parts]
    if len(parts) < 8:
        parts = parts + [""] * (8 - len(parts))
    else:
        parts = parts[:8]
    # đảm bảo field8 có dạng yyyymmdd:int hoặc rỗng
    if parts[7] and ":" not in parts[7]:
        # nếu ai đó lỡ chỉ lưu "0" → chuyển thành "00000000:0"
        parts[7] = f"00000000:{parts[7]}"
    return tuple(parts)  # trả về tuple 8 phần tử

def read_accounts_8cols(path: str):
    """
    Đọc file accounts, chấp nhận 5/6/7/8 cột, trả về list[tuple[str,str,str,str,str,str,str,str]]
    Không phá định dạng cũ — thiếu cột thì fill "".
    """
    rows = []
    if not os.path.exists(path):
        return rows
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip("\n")
            if not line.strip():
                continue
            parts = line.split(",")
            rows.append(_normalize_line_to_8cols(parts))
    return rows

def read_accounts_6cols(path: Path) -> List[List[str]]:
    """
    (Giữ cho tương thích ngược) — vẫn có thể dùng khi cần 6 cột cũ:
      0 email, 1 password, 2 server, 3 date(yyyymmdd), 4 status, 5 last_leave(yyyymmdd:hhmm)
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
    (Giữ để không phá chỗ khác nếu còn dùng.)
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        for r in rows6:
            row = list(r[:6])
            while len(row) < 6:
                row.append("")
            w.writerow(row)

def write_accounts_8cols(path: Path, rows8: List[List[str]]) -> None:
    """
    Ghi danh sách 8 cột theo đúng thứ tự:
      email, pwd, server, date, status, last_leave, vienchinh, chucphuc
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        for r in rows8:
            row = list(r[:8])
            while len(row) < 8:
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

        # (THÊM) Tab DS Chúc phúc
        w_bless = QWidget()
        bless_layout = QVBoxLayout(w_bless)

        # Cấu hình: cooldown_hours & per_run
        grp_bconf = QGroupBox("Cấu hình chúc phúc")
        form_bconf = QFormLayout(grp_bconf)
        self.ed_bless_cooldown = QLineEdit()
        self.ed_bless_perrun = QLineEdit()
        self.ed_bless_cooldown.setPlaceholderText("Giờ (ví dụ 8)")
        self.ed_bless_perrun.setPlaceholderText("Số lượt mỗi lần (ví dụ 3)")
        form_bconf.addRow(QLabel("Giãn cách (giờ):"), self.ed_bless_cooldown)
        form_bconf.addRow(QLabel("Số lượt chúc mỗi lần:"), self.ed_bless_perrun)
        bless_layout.addWidget(grp_bconf)

        # Bảng DS chúc phúc
        self.tbl_bless = QTableWidget(0, len(BLESS_HEADERS_VISIBLE))
        self.tbl_bless.setHorizontalHeaderLabels(BLESS_HEADERS_VISIBLE)
        self.tbl_bless.horizontalHeader().setSectionResizeMode(BLESS_COL_NAME, QHeaderView.Stretch)
        self.tbl_bless.horizontalHeader().setSectionResizeMode(BLESS_COL_LAST, QHeaderView.ResizeToContents)
        bless_layout.addWidget(self.tbl_bless)

        bless_btns = QHBoxLayout()
        self.btn_bless_add = QPushButton("Thêm hàng")
        self.btn_bless_del = QPushButton("Xoá hàng")
        self.btn_bless_load = QPushButton("Load")
        self.btn_bless_save = QPushButton("Save")
        bless_btns.addWidget(self.btn_bless_add)
        bless_btns.addWidget(self.btn_bless_del)
        bless_btns.addStretch(1)
        bless_btns.addWidget(self.btn_bless_load)
        bless_btns.addWidget(self.btn_bless_save)
        bless_layout.addLayout(bless_btns)

        self.tabs.addTab(w_bless, "DS Chúc phúc")

        bottom_layout.addWidget(self.tabs)
        bottom_layout.addWidget(QLabel("Log:"))
        self.log = QTextEdit()
        self.log.setReadOnly(True)
        bottom_layout.addWidget(self.log, 1)

        splitter.addWidget(bottom)
        splitter.setSizes([380, 540])

        # chọn Nox → load accounts & bless
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

        # (THÊM) buttons Bless
        self.btn_bless_add.clicked.connect(self.bless_add)
        self.btn_bless_del.clicked.connect(self.bless_del)
        self.btn_bless_load.clicked.connect(self.load_bless_current_port)
        self.btn_bless_save.clicked.connect(self.save_bless_current_port)

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

    # (THÊM) đường dẫn file chúc phúc
    def chucphuc_path_for_port(self, port: int) -> Path:
        d = DATA_ROOT / str(port)
        d.mkdir(parents=True, exist_ok=True)
        return d / "chucphuc.txt"

    def on_nox_selection_changed(self):
        port = self.get_current_port()
        self.active_port = port
        if port is None:
            self.tbl_acc.setRowCount(0)
            self.tbl_bless.setRowCount(0)  # (THÊM) clear bảng bless khi chưa chọn
            self.log_msg("Chưa chọn Nox.")
            return

        # Accounts
        path = self.accounts_path_for_port(port)
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("", encoding="utf-8")
            self.log_msg(f"Tạo mới {path}")
        self.load_accounts_for_port(port)

        # (THÊM) Bless
        bpath = self.chucphuc_path_for_port(port)
        if not bpath.exists():
            # Khởi tạo file JSON rỗng theo schema
            init_obj = {"cooldown_hours": 0, "per_run": 0, "items": []}
            bpath.write_text(json.dumps(init_obj, ensure_ascii=False, indent=2), encoding="utf-8")
            self.log_msg(f"Tạo mới {bpath}")
        self.load_bless_for_port(port)

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
            self.tbl_bless.setRowCount(0)  # (THÊM)

    # ---------- ACCOUNTS ----------
    def load_accounts_for_port(self, port: int):
        path = self.accounts_path_for_port(port)
        rows8 = read_accounts_8cols(str(path))

        self.tbl_acc.setRowCount(0)
        for r8 in rows8:
            email, pwd, server, date = r8[0], r8[1], r8[2], r8[3]
            r = self.tbl_acc.rowCount()
            self.tbl_acc.insertRow(r)
            self.tbl_acc.setItem(r, ACC_COL_EMAIL, QTableWidgetItem(email))
            self.tbl_acc.setItem(r, ACC_COL_PASS, QTableWidgetItem(pwd))
            s_item = QTableWidgetItem(server); s_item.setTextAlignment(Qt.AlignCenter)
            d_item = QTableWidgetItem(date);   d_item.setTextAlignment(Qt.AlignCenter)
            self.tbl_acc.setItem(r, ACC_COL_SERVER, s_item)
            self.tbl_acc.setItem(r, ACC_COL_DATE, d_item)

        self.log_msg(f"Loaded {len(rows8)} accounts từ {path}")

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
        Lưu bảng 4 cột về file **8 cột**:
          - Giữ nguyên 'status', 'last_leave', 'vienchinh', 'chucphuc' (nếu email đã có).
          - Với email mới: status="1", last_leave="", vienchinh="", chucphuc=""
        """
        path = self.accounts_path_for_port(port)
        rows4 = self.collect_accounts_visible4()

        # đọc hiện trạng cũ (để giữ 4 cột cuối)
        old8 = read_accounts_8cols(str(path))
        old_map: Dict[str, tuple] = {r[0].strip(): r for r in old8 if r and r[0].strip()}

        rows8: List[List[str]] = []
        for email, pwd, server, date in rows4:
            if not email:
                continue
            if email in old_map:
                _, _, _, _, status, last_leave, vienchinh, chucphuc = old_map[email]
            else:
                status, last_leave, vienchinh, chucphuc = "1", "", "", ""
            rows8.append([email, pwd, server, date, status, last_leave, vienchinh, chucphuc])

        write_accounts_8cols(path, rows8)
        self.log_msg(f"Saved {len(rows8)} accounts → {path}")

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

    # ---------- DS CHÚC PHÚC (MỚI) ----------
    def _read_bless_json(self, path: Path) -> dict:
        try:
            if path.exists():
                txt = path.read_text(encoding="utf-8").strip()
                if txt:
                    obj = json.loads(txt)
                    if isinstance(obj, dict):
                        obj.setdefault("cooldown_hours", 0)
                        obj.setdefault("per_run", 0)
                        obj.setdefault("items", [])
                        return obj
        except Exception:
            pass
        return {"cooldown_hours": 0, "per_run": 0, "items": []}

    def _write_bless_json(self, path: Path, obj: dict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")

    def load_bless_for_port(self, port: int):
        bpath = self.chucphuc_path_for_port(port)
        obj = self._read_bless_json(bpath)

        # set cấu hình
        self.ed_bless_cooldown.setText(str(obj.get("cooldown_hours", 0)))
        self.ed_bless_perrun.setText(str(obj.get("per_run", 0)))

        # render bảng (tối đa 20 item)
        items = obj.get("items") or []
        self.tbl_bless.setRowCount(0)
        for idx, it in enumerate(items[:BLESS_MAX_ITEMS_RENDER]):
            name = str(it.get("name", "")).strip()
            last = str(it.get("last", "")).strip()
            r = self.tbl_bless.rowCount()
            self.tbl_bless.insertRow(r)
            self.tbl_bless.setItem(r, BLESS_COL_NAME, QTableWidgetItem(name))
            li = QTableWidgetItem(last)
            li.setTextAlignment(Qt.AlignCenter)
            self.tbl_bless.setItem(r, BLESS_COL_LAST, li)

        self.log_msg(f"Loaded DS chúc phúc ({len(items)} items) từ {bpath}")

    def save_bless_for_port(self, port: int):
        bpath = self.chucphuc_path_for_port(port)
        obj = self._read_bless_json(bpath)

        # cấu hình
        try:
            cd = int(self.ed_bless_cooldown.text().strip() or "0")
        except Exception:
            cd = 0
        try:
            pr = int(self.ed_bless_perrun.text().strip() or "0")
        except Exception:
            pr = 0
        obj["cooldown_hours"] = max(0, cd)
        obj["per_run"] = max(0, pr)

        # đọc bảng
        items: List[dict] = []
        for r in range(self.tbl_bless.rowCount()):
            name_it = self.tbl_bless.item(r, BLESS_COL_NAME)
            last_it = self.tbl_bless.item(r, BLESS_COL_LAST)
            name = name_it.text().strip() if name_it else ""
            last = last_it.text().strip() if last_it else ""
            if not name:
                continue
            # giữ lại map blessed cũ của item nếu tồn tại (tránh mất dữ liệu lịch sử)
            old_map = {}
            for old in (obj.get("items") or []):
                if str(old.get("name","")).strip() == name:
                    old_map = old.get("blessed") or {}
                    break
            items.append({"name": name, "last": last, "blessed": old_map})

        obj["items"] = items
        self._write_bless_json(bpath, obj)
        self.log_msg(f"Saved DS chúc phúc ({len(items)} items) → {bpath}")

    def load_bless_current_port(self):
        if self.active_port is None:
            QMessageBox.information(self, "Chú ý", "Chọn một Nox ở bảng trên trước.")
            return
        self.load_bless_for_port(self.active_port)

    def save_bless_current_port(self):
        if self.active_port is None:
            QMessageBox.information(self, "Chú ý", "Chọn một Nox ở bảng trên trước.")
            return
        self.save_bless_for_port(self.active_port)

    def bless_add(self):
        r = self.tbl_bless.rowCount()
        if r >= BLESS_MAX_ITEMS_RENDER:
            QMessageBox.information(self, "Chú ý", f"Tối đa {BLESS_MAX_ITEMS_RENDER} dòng hiển thị.")
            return
        self.tbl_bless.insertRow(r)

    def bless_del(self):
        rows = sorted({i.row() for i in self.tbl_bless.selectedIndexes()}, reverse=True)
        for r in rows:
            self.tbl_bless.removeRow(r)

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
