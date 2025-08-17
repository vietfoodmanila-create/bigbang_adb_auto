# -*- coding: utf-8 -*-
from __future__ import annotations

import sys
import subprocess
import shutil
import csv
import json
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Dict
import os
from datetime import datetime
import time

# Import các thư viện cần thiết cho Selenium
from selenium import webdriver
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
from webdriver_manager.chrome import ChromeDriverManager
import requests

from PySide6.QtCore import Qt, QPoint
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QSplitter, QVBoxLayout, QHBoxLayout,
    QTableWidget, QTableWidgetItem, QHeaderView, QCheckBox,
    QTabWidget, QGroupBox, QFormLayout, QTextEdit, QLabel, QMessageBox, QPushButton,
    QAbstractItemView, QMenu, QLineEdit, QDialog, QDialogButtonBox
)
from ui_auth import CloudClient
from ui_license import AccountBanner

# ====== Cấu hình ======
ADB_PATH = Path(r"D:\Program Files\Nox\bin\adb.exe")
DATA_ROOT = Path("data")
DATA_ROOT.mkdir(exist_ok=True)
DEFAULT_WIDTH = 450
DEFAULT_HEIGHT = 900

GAME_LOGIN_URL = "https://pay.bigbangthoikhong.vn/login?game_id=105"

ACC_HEADERS_VISIBLE = ["", "Email", "Trạng thái", "Sửa", "Xóa"]
ACC_COL_CHECK, ACC_COL_EMAIL, ACC_COL_STATUS, ACC_COL_EDIT, ACC_COL_DELETE = range(5)

BLESS_HEADERS_VISIBLE = ["Tên nhân vật", "Lần cuối (yyyymmdd:hh)"]
BLESS_COL_NAME, BLESS_COL_LAST = range(2)
BLESS_MAX_ITEMS_RENDER = 20


# ---------------- Helpers ----------------
def _run_quiet(cmd: list[str], timeout: int = 8) -> str:
    try:
        startupinfo = None
        if os.name == 'nt':
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, startupinfo=startupinfo)
        return out.stdout
    except Exception:
        return ""


def list_adb_ports_with_status() -> dict[int, str]:
    text = ""
    adb_executable = str(ADB_PATH) if ADB_PATH.exists() else "adb"
    text = _run_quiet([adb_executable, "devices"], timeout=6)
    result: dict[int, str] = {}
    for line in text.splitlines():
        s = line.strip()
        if not s or s.startswith("List of devices"): continue
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
    ports: List[int] = []
    if not DATA_ROOT.exists(): return ports
    for p in DATA_ROOT.iterdir():
        if p.is_dir():
            try:
                ports.append(int(p.name))
            except Exception:
                pass
    return ports


# (HOÀN CHỈNH) Tích hợp hàm kiểm tra mật khẩu đã hoạt động thành công
def check_game_login_client_side(email: str, password: str) -> tuple[bool, str]:
    """
    Sử dụng Selenium với cơ chế chờ đợi thông minh (WebDriverWait) để tương tác
    với các phần tử được tạo ra bởi JavaScript.
    """
    chrome_options = webdriver.ChromeOptions()
    chrome_options.add_argument("--start-maximized")
    chrome_options.add_argument("--log-level=3")
    chrome_options.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36")
    chrome_options.add_experimental_option("excludeSwitches", ["enable-logging"])
    driver = None
    try:
        service = ChromeService(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=chrome_options)
        driver.get(GAME_LOGIN_URL)
        wait = WebDriverWait(driver, 20)

        email_field = wait.until(EC.visibility_of_element_located((By.NAME, "username")))
        password_field = driver.find_element(By.NAME, "password")

        email_field.clear()
        email_field.send_keys(email)
        password_field.clear()
        password_field.send_keys(password)
        time.sleep(0.5)

        login_button = driver.find_element(By.CSS_SELECTOR, "form button[type='submit']")
        login_button.click()

        wait.until(lambda d: "login" not in d.current_url.lower())

        final_url = driver.current_url
        if "rechargepackage" in final_url.lower():
            return True, "Xác thực thành công!"
        else:
            return False, f"Chuyển hướng đến trang không mong đợi: {final_url}"

    except TimeoutException:
        try:
            if driver and (
                    "sai mật khẩu" in driver.page_source.lower() or "incorrect password" in driver.page_source.lower()):
                return False, "Thông tin đăng nhập không chính xác."
        except:
            pass
        return False, "Hết thời gian chờ. Trang web không phản hồi như mong đợi."
    except Exception as e:
        return False, f"Lỗi Selenium: {e}"
    finally:
        if driver:
            driver.quit()


class AccountDialog(QDialog):
    def __init__(self, account_data: dict = None, parent=None):
        super().__init__(parent)
        self.account_data = account_data;
        self.is_edit_mode = account_data is not None
        self.setWindowTitle("Sửa tài khoản" if self.is_edit_mode else "Thêm tài khoản mới");
        self.setMinimumWidth(400)
        layout = QVBoxLayout(self);
        form_layout = QFormLayout()
        self.email_edit = QLineEdit();
        self.password_edit = QLineEdit();
        self.password_edit.setEchoMode(QLineEdit.Password);
        self.server_edit = QLineEdit()
        if self.is_edit_mode:
            self.email_edit.setText(self.account_data.get("game_email", ""));
            self.email_edit.setReadOnly(True)
            self.server_edit.setText(str(self.account_data.get("server", "")));
            self.password_edit.setPlaceholderText("Nhập mật khẩu mới nếu muốn thay đổi")
        else:
            self.email_edit.setPlaceholderText("Nhập email game");
            self.password_edit.setPlaceholderText("Nhập mật khẩu game");
            self.server_edit.setPlaceholderText("Nhập server (mặc định: 8)")
        form_layout.addRow("Email:", self.email_edit);
        form_layout.addRow("Mật khẩu:", self.password_edit);
        form_layout.addRow("Server:", self.server_edit)
        layout.addLayout(form_layout)
        self.buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.buttons.accepted.connect(self.accept);
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)

    def get_data(self) -> dict:
        data = {"game_email": self.email_edit.text().strip().lower(),
                "game_password": self.password_edit.text().strip(), "server": self.server_edit.text().strip() or "8"}
        if self.is_edit_mode and not data["game_password"]: del data["game_password"]
        return data


class MainWindow(QMainWindow):
    def __init__(self, cloud: CloudClient):
        super().__init__()
        self.cloud = cloud
        self.setWindowTitle("BigBang ADB Auto")
        self.resize(DEFAULT_WIDTH, DEFAULT_HEIGHT)
        self.setMinimumSize(420, 760)
        self.active_port: Optional[int] = None
        self.online_accounts: List[Dict] = []
        self._is_closing = False

        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        main_layout = QVBoxLayout(main_widget)
        main_layout.setContentsMargins(0, 0, 0, 0);
        main_layout.setSpacing(0)

        self.banner = AccountBanner(self.cloud, controller=self, parent=self)
        main_layout.addWidget(self.banner)

        splitter = QSplitter(Qt.Vertical)
        main_layout.addWidget(splitter)

        top = QWidget();
        top_layout = QVBoxLayout(top)
        self.tbl_nox = QTableWidget(0, 5)
        self.tbl_nox.setHorizontalHeaderLabels(["Start", "Tên máy ảo", "ADB Port", "Trạng thái", "Status"])
        self.tbl_nox.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents);
        self.tbl_nox.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.tbl_nox.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents);
        self.tbl_nox.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.tbl_nox.horizontalHeader().setSectionResizeMode(4, QHeaderView.Stretch)
        self.tbl_nox.setSelectionMode(QAbstractItemView.SingleSelection);
        self.tbl_nox.setSelectionBehavior(QTableWidget.SelectRows)
        self.tbl_nox.setEditTriggers(QAbstractItemView.NoEditTriggers);
        self.tbl_nox.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tbl_nox.customContextMenuRequested.connect(self._show_nox_context_menu)
        top_layout.addWidget(self.tbl_nox);
        splitter.addWidget(top)

        bottom = QWidget();
        bottom_layout = QVBoxLayout(bottom)
        self.tabs = QTabWidget()

        w_acc = QWidget();
        acc_layout = QVBoxLayout(w_acc);
        acc_toolbar = QHBoxLayout()
        self.chk_select_all_accs = QCheckBox("Chọn tất cả");
        self.btn_acc_add = QPushButton("Thêm tài khoản");
        self.btn_acc_refresh = QPushButton("Làm mới DS")
        acc_toolbar.addWidget(self.chk_select_all_accs);
        acc_toolbar.addStretch();
        acc_toolbar.addWidget(self.btn_acc_add);
        acc_toolbar.addWidget(self.btn_acc_refresh)
        acc_layout.addLayout(acc_toolbar)
        self.tbl_acc = QTableWidget(0, len(ACC_HEADERS_VISIBLE));
        self.tbl_acc.setHorizontalHeaderLabels(ACC_HEADERS_VISIBLE)
        self.tbl_acc.horizontalHeader().setSectionResizeMode(ACC_COL_CHECK, QHeaderView.ResizeToContents);
        self.tbl_acc.horizontalHeader().setSectionResizeMode(ACC_COL_EMAIL, QHeaderView.Stretch)
        self.tbl_acc.horizontalHeader().setSectionResizeMode(ACC_COL_STATUS, QHeaderView.ResizeToContents);
        self.tbl_acc.horizontalHeader().setSectionResizeMode(ACC_COL_EDIT, QHeaderView.ResizeToContents)
        self.tbl_acc.horizontalHeader().setSectionResizeMode(ACC_COL_DELETE, QHeaderView.ResizeToContents)
        self.tbl_acc.setEditTriggers(QAbstractItemView.NoEditTriggers);
        acc_layout.addWidget(self.tbl_acc);
        self.tabs.addTab(w_acc, "Accounts")

        w_feat = QWidget();
        feat_layout = QVBoxLayout(w_feat);
        grp = QGroupBox("Chọn tính năng");
        form = QFormLayout(grp)
        self.chk_build = QCheckBox("Xây dựng liên minh / xem quảng cáo");
        self.chk_expedition = QCheckBox("Viễn chinh")
        self.chk_auto_leave = QCheckBox("Tự thoát liên minh sau khi thao tác xong");
        self.chk_bless = QCheckBox("Chúc phúc")
        form.addRow(self.chk_build);
        form.addRow(self.chk_expedition);
        form.addRow(self.chk_auto_leave);
        form.addRow(self.chk_bless)
        feat_layout.addWidget(grp);
        feat_layout.addStretch(1);
        self.tabs.addTab(w_feat, "Tính năng")

        w_bless = QWidget();
        bless_layout = QVBoxLayout(w_bless);
        grp_bconf = QGroupBox("Cấu hình chúc phúc");
        form_bconf = QFormLayout(grp_bconf)
        self.ed_bless_cooldown = QLineEdit();
        self.ed_bless_cooldown.setPlaceholderText("Giờ (ví dụ 8)")
        self.ed_bless_perrun = QLineEdit();
        self.ed_bless_perrun.setPlaceholderText("Số lượt mỗi lần (ví dụ 3)")
        form_bconf.addRow(QLabel("Giãn cách (giờ):"), self.ed_bless_cooldown);
        form_bconf.addRow(QLabel("Số lượt chúc mỗi lần:"), self.ed_bless_perrun)
        bless_layout.addWidget(grp_bconf)
        self.tbl_bless = QTableWidget(0, len(BLESS_HEADERS_VISIBLE));
        self.tbl_bless.setHorizontalHeaderLabels(BLESS_HEADERS_VISIBLE)
        self.tbl_bless.horizontalHeader().setSectionResizeMode(BLESS_COL_NAME, QHeaderView.Stretch);
        self.tbl_bless.horizontalHeader().setSectionResizeMode(BLESS_COL_LAST, QHeaderView.ResizeToContents)
        bless_layout.addWidget(self.tbl_bless)
        bless_btns = QHBoxLayout();
        self.btn_bless_add = QPushButton("Thêm hàng");
        self.btn_bless_del = QPushButton("Xoá hàng")
        self.btn_bless_load = QPushButton("Load");
        self.btn_bless_save = QPushButton("Save")
        bless_btns.addWidget(self.btn_bless_add);
        bless_btns.addWidget(self.btn_bless_del);
        bless_btns.addStretch(1);
        bless_btns.addWidget(self.btn_bless_load);
        bless_btns.addWidget(self.btn_bless_save)
        bless_layout.addLayout(bless_btns);
        self.tabs.addTab(w_bless, "DS Chúc phúc")

        bottom_layout.addWidget(self.tabs);
        bottom_layout.addWidget(QLabel("Log:"))
        self.log = QTextEdit();
        self.log.setReadOnly(True);
        bottom_layout.addWidget(self.log, 1)
        splitter.addWidget(bottom);
        splitter.setSizes([250, 670])

        self.tbl_nox.itemSelectionChanged.connect(self.on_nox_selection_changed)
        self.btn_acc_add.clicked.connect(self.on_add_account);
        self.btn_acc_refresh.clicked.connect(self.load_accounts_current_port);
        self.chk_select_all_accs.toggled.connect(self.on_select_all_accounts)
        self.btn_bless_add.clicked.connect(self.bless_add);
        self.btn_bless_del.clicked.connect(self.bless_del);
        self.btn_bless_load.clicked.connect(self.load_bless_current_port);
        self.btn_bless_save.clicked.connect(self.save_bless_current_port)

        self.refresh_nox()
        if self.tbl_nox.rowCount() > 0: self.tbl_nox.selectRow(0)

    def closeEvent(self, event: QCloseEvent):
        self._is_closing = True; super().closeEvent(event)

    def refresh_nox(self):
        adb_map = list_adb_ports_with_status();
        known = set(list_known_ports_from_data())
        all_ports = sorted(set(adb_map.keys()) | known);
        self.tbl_nox.setRowCount(0)
        for port in all_ports:
            r = self.tbl_nox.rowCount();
            self.tbl_nox.insertRow(r)
            chk = QCheckBox();
            self.tbl_nox.setCellWidget(r, 0, chk)
            items = [QTableWidgetItem(f"Nox({port})"), QTableWidgetItem(str(port)),
                     QTableWidgetItem("online" if adb_map.get(port) == "device" else "offline"),
                     QTableWidgetItem("IDLE")]
            for i, it in enumerate(items, start=1):
                it.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
                if i in (2, 3): it.setTextAlignment(Qt.AlignCenter)
                self.tbl_nox.setItem(r, i, it)

    def get_current_port(self) -> Optional[int]:
        row = self.tbl_nox.currentRow()
        if row < 0: return None
        it = self.tbl_nox.item(row, 2)
        return int(it.text()) if it and it.text().isdigit() else None

    def _show_nox_context_menu(self, pos: QPoint):
        index = self.tbl_nox.indexAt(pos)
        if not index.isValid(): return
        row = index.row()
        status = self.tbl_nox.item(row, 3).text().strip() if self.tbl_nox.item(row, 3) else ""
        port_item = self.tbl_nox.item(row, 2)
        port = int(port_item.text()) if port_item and port_item.text().isdigit() else None
        menu = QMenu(self);
        act_delete = menu.addAction("Xoá thông tin máy ảo (offline)")
        if status != "offline": act_delete.setEnabled(False)
        action = menu.exec(self.tbl_nox.viewport().mapToGlobal(pos))
        if action == act_delete and port is not None: self._delete_offline_instance(row, port)

    def _delete_offline_instance(self, row: int, port: int):
        ret = QMessageBox.question(self, "Xác nhận",
                                   f"Xoá thông tin máy ảo offline cho port {port}?\nThao tác sẽ xoá thư mục: {DATA_ROOT / str(port)}",
                                   QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if ret != QMessageBox.Yes: return
        folder = DATA_ROOT / str(port)
        try:
            if folder.exists() and folder.is_dir(): shutil.rmtree(folder)
            self.tbl_nox.removeRow(row);
            self.log_msg(f"Đã xoá thông tin máy ảo offline port {port}.")
        except Exception as e:
            QMessageBox.warning(self, "Lỗi", f"Không xoá được: {e}")
        if self.tbl_nox.rowCount() > 0:
            if self.tbl_nox.currentRow() == -1: self.tbl_nox.selectRow(0)
        else:
            self.tbl_acc.setRowCount(0); self.tbl_bless.setRowCount(0); self.active_port = None

    def on_nox_selection_changed(self):
        port = self.get_current_port()
        if port is None: self.tbl_acc.setRowCount(0); self.tbl_bless.setRowCount(0); return
        if port != self.active_port:
            self.active_port = port;
            self.log_msg(f"Đã chọn máy ảo port {port}.")
            self.load_accounts_current_port();
            self.load_bless_for_port(port)

    def load_accounts_current_port(self):
        if self.active_port is None: return
        try:
            self.log_msg(f"Đang tải DS tài khoản...");
            self.online_accounts = self.cloud.get_game_accounts()
            self.populate_accounts_table()
        except Exception as e:
            self.online_accounts = [];
            self.populate_accounts_table()
            self.log_msg(f"Lỗi tải DS tài khoản: {e}");
            QMessageBox.critical(self, "Lỗi API", f"Không thể tải danh sách tài khoản:\n{e}")

    def populate_accounts_table(self):
        self.tbl_acc.setRowCount(0)
        for row_data in self.online_accounts:
            row = self.tbl_acc.rowCount();
            self.tbl_acc.insertRow(row)
            chk_widget = QWidget();
            chk_layout = QHBoxLayout(chk_widget);
            chk_box = QCheckBox();
            chk_layout.addWidget(chk_box);
            chk_layout.setAlignment(Qt.AlignCenter);
            chk_layout.setContentsMargins(0, 0, 0, 0);
            self.tbl_acc.setCellWidget(row, ACC_COL_CHECK, chk_widget)
            self.tbl_acc.setItem(row, ACC_COL_EMAIL, QTableWidgetItem(row_data.get('game_email', '')))
            status_text = "OK" if row_data.get('status') == 'ok' else "Sai Pass";
            btn_info = QPushButton(status_text);
            btn_info.setToolTip("Xem chi tiết thông tin");
            btn_info.clicked.connect(lambda c, r=row: self.on_info_account(r));
            self.tbl_acc.setCellWidget(row, ACC_COL_STATUS, btn_info)
            btn_edit = QPushButton("Sửa");
            btn_edit.setToolTip("Sửa thông tin tài khoản");
            btn_edit.clicked.connect(lambda c, r=row: self.on_edit_account(r));
            self.tbl_acc.setCellWidget(row, ACC_COL_EDIT, btn_edit)
            btn_delete = QPushButton("Xóa");
            btn_delete.setToolTip("Xóa tài khoản khỏi danh sách");
            btn_delete.clicked.connect(lambda c, r=row: self.on_delete_account(r));
            self.tbl_acc.setCellWidget(row, ACC_COL_DELETE, btn_delete)
        self.log_msg(f"Đã hiển thị {len(self.online_accounts)} tài khoản.")

    def on_add_account(self):
        dialog = AccountDialog(parent=self)
        if dialog.exec() == QDialog.Accepted:
            new_data = dialog.get_data()
            email = new_data.get("game_email")
            password = new_data.get("game_password")

            if not email or not password:
                QMessageBox.warning(self, "Thiếu thông tin", "Vui lòng nhập đầy đủ email và mật khẩu.");
                return

            # (LOGIC MỚI) Kiểm tra xem email đã tồn tại trong danh sách hay chưa
            existing_emails = [acc.get('game_email', '').lower() for acc in self.online_accounts]
            if email.lower() in existing_emails:
                QMessageBox.warning(self, "Tài khoản đã tồn tại", f"Tài khoản '{email}' đã có trong danh sách của bạn.")
                self.log_msg(f"Thao tác thêm bị hủy: tài khoản {email} đã tồn tại.")
                return  # Dừng lại ngay tại đây

            # Nếu không tồn tại, tiếp tục quy trình xác thực và thêm mới
            self.log_msg(f"Đang mở trình duyệt để xác thực tài khoản {email}...")
            QApplication.setOverrideCursor(Qt.WaitCursor)
            success, message = check_game_login_client_side(email, password)
            QApplication.restoreOverrideCursor()

            if not success:
                self.log_msg(f"Xác thực thất bại: {message}")
                QMessageBox.critical(self, "Xác thực thất bại", message);
                return

            self.log_msg(f"Xác thực thành công! Đang thêm tài khoản vào hệ thống...")
            try:
                self.cloud.add_game_account(new_data)
                self.log_msg("Thêm thành công! Đang làm mới danh sách...");
                self.load_accounts_current_port()
            except Exception as e:
                self.log_msg(f"Lỗi khi thêm tài khoản: {e}");
                QMessageBox.critical(self, "Lỗi API", f"Không thể thêm tài khoản vào hệ thống:\n{e}")

    def on_info_account(self, row):
        account = self.online_accounts[row]

        def fmt_dt(s): return datetime.fromisoformat(s).strftime('%d/%m/%Y %H:%M:%S') if s else "N/A"

        def fmt_d(s): return datetime.fromisoformat(s).strftime('%d/%m/%Y') if s else "N/A"

        info = (
            f"<b>Email:</b> {account.get('game_email', 'N/A')}<br>"f"<b>Server:</b> {account.get('server', 'N/A')}<br>"f"<b>Trạng thái:</b> <span style='color:green;'>{account.get('status', 'N/A')}</span><br><br>"f"<b>Xây dựng cuối:</b> {fmt_d(account.get('last_build_date'))}<br>"f"<b>Viễn chinh cuối:</b> {fmt_dt(account.get('last_expedition_time'))}<br>"f"<b>Rời LM cuối:</b> {fmt_dt(account.get('last_leave_time'))}<br>"f"<b>Chúc phúc:</b> {account.get('last_bless_info', 'N/A')}")
        QMessageBox.information(self, "Thông tin tài khoản", info)

    def on_edit_account(self, row):
        account = self.online_accounts[row];
        dialog = AccountDialog(account_data=account, parent=self)
        if dialog.exec() == QDialog.Accepted:
            updated_data = dialog.get_data();
            new_password = updated_data.get("game_password")
            if new_password:
                self.log_msg(f"Đang mở trình duyệt để xác thực mật khẩu mới cho {account['game_email']}...");
                QApplication.setOverrideCursor(Qt.WaitCursor)
                success, message = check_game_login_client_side(account['game_email'], new_password);
                QApplication.restoreOverrideCursor()
                if not success: self.log_msg(f"Xác thực mật khẩu mới thất bại: {message}"); QMessageBox.critical(self,
                                                                                                                 "Mật khẩu không chính xác",
                                                                                                                 message); return
            self.log_msg(f"Đang cập nhật tài khoản {account['game_email']}...")
            try:
                self.cloud.update_game_account(account['id'], updated_data)
                self.log_msg("Cập nhật thành công! Đang làm mới danh sách...");
                self.load_accounts_current_port()
            except Exception as e:
                self.log_msg(f"Lỗi khi cập nhật: {e}"); QMessageBox.critical(self, "Lỗi API",
                                                                             f"Không thể cập nhật tài khoản:\n{e}")

    def on_delete_account(self, row):
        account = self.online_accounts[row]
        reply = QMessageBox.question(self, 'Xác nhận xóa',
                                     f"Bạn có chắc muốn xóa tài khoản '{account['game_email']}' khỏi danh sách?",
                                     QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if reply == QMessageBox.Yes:
            self.log_msg(f"Đang xóa tài khoản {account['game_email']}...")
            try:
                self.cloud.delete_game_account(account['id'])
                self.log_msg("Xóa thành công! Đang làm mới danh sách...");
                self.load_accounts_current_port()
            except Exception as e:
                self.log_msg(f"Lỗi khi xóa: {e}"); QMessageBox.critical(self, "Lỗi", f"Không thể xóa tài khoản:\n{e}")

    def on_select_all_accounts(self, checked):
        for row in range(self.tbl_acc.rowCount()):
            widget = self.tbl_acc.cellWidget(row, ACC_COL_CHECK)
            if widget and (chk_box := widget.findChild(QCheckBox)): chk_box.setChecked(checked)

    def chucphuc_path_for_port(self, port: int) -> Path:
        d = DATA_ROOT / str(port); d.mkdir(parents=True, exist_ok=True); return d / "chucphuc.txt"

    def _read_bless_json(self, path: Path) -> dict:
        try:
            if path.exists():
                txt = path.read_text(encoding="utf-8").strip()
                if txt:
                    obj = json.loads(txt)
                    if isinstance(obj, dict): obj.setdefault("cooldown_hours", 0); obj.setdefault("per_run",
                                                                                                  0); obj.setdefault(
                        "items", []); return obj
        except Exception:
            pass
        return {"cooldown_hours": 0, "per_run": 0, "items": []}

    def _write_bless_json(self, path: Path, obj: dict):
        path.parent.mkdir(parents=True, exist_ok=True); path.write_text(json.dumps(obj, ensure_ascii=False, indent=2),
                                                                        encoding="utf-8")

    def load_bless_for_port(self, port: int):
        bpath = self.chucphuc_path_for_port(port);
        obj = self._read_bless_json(bpath)
        self.ed_bless_cooldown.setText(str(obj.get("cooldown_hours", 0)));
        self.ed_bless_perrun.setText(str(obj.get("per_run", 0)))
        items = obj.get("items") or [];
        self.tbl_bless.setRowCount(0)
        for idx, it in enumerate(items[:BLESS_MAX_ITEMS_RENDER]):
            name = str(it.get("name", "")).strip();
            last = str(it.get("last", "")).strip()
            r = self.tbl_bless.rowCount();
            self.tbl_bless.insertRow(r)
            self.tbl_bless.setItem(r, BLESS_COL_NAME, QTableWidgetItem(name))
            li = QTableWidgetItem(last);
            li.setTextAlignment(Qt.AlignCenter);
            self.tbl_bless.setItem(r, BLESS_COL_LAST, li)
        self.log_msg(f"Loaded DS chúc phúc ({len(items)} items) từ {bpath}")

    def save_bless_for_port(self, port: int):
        bpath = self.chucphuc_path_for_port(port);
        obj = self._read_bless_json(bpath)
        try:
            cd = int(self.ed_bless_cooldown.text().strip() or "0")
        except Exception:
            cd = 0
        try:
            pr = int(self.ed_bless_perrun.text().strip() or "0")
        except Exception:
            pr = 0
        obj["cooldown_hours"] = max(0, cd);
        obj["per_run"] = max(0, pr);
        items: List[dict] = []
        for r in range(self.tbl_bless.rowCount()):
            name_it = self.tbl_bless.item(r, BLESS_COL_NAME);
            last_it = self.tbl_bless.item(r, BLESS_COL_LAST)
            name = name_it.text().strip() if name_it else "";
            last = last_it.text().strip() if last_it else ""
            if not name: continue
            old_map = {}
            for old in (obj.get("items") or []):
                if str(old.get("name", "")).strip() == name: old_map = old.get("blessed") or {}; break
            items.append({"name": name, "last": last, "blessed": old_map})
        obj["items"] = items;
        self._write_bless_json(bpath, obj);
        self.log_msg(f"Saved DS chúc phúc ({len(items)} items) → {bpath}")

    def load_bless_current_port(self):
        if self.active_port is not None: self.load_bless_for_port(self.active_port)

    def save_bless_current_port(self):
        if self.active_port is not None: self.save_bless_for_port(self.active_port)

    def bless_add(self):
        if self.tbl_bless.rowCount() < BLESS_MAX_ITEMS_RENDER: self.tbl_bless.insertRow(self.tbl_bless.rowCount())

    def bless_del(self):
        rows = sorted({i.row() for i in self.tbl_bless.selectedIndexes()}, reverse=True)
        for r in rows: self.tbl_bless.removeRow(r)

    def log_msg(self, msg: str):
        if self._is_closing or not hasattr(self, 'log') or self.log is None: print(f"(LOG-STDOUT) {msg}"); return
        try:
            self.log.append(msg); self.log.ensureCursorVisible()
        except RuntimeError:
            print(f"(LOG-STDOUT-ERR) {msg}")


def main():
    app = QApplication(sys.argv)
    from ui_auth import CloudClient
    w = MainWindow(cloud=CloudClient())
    w.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()