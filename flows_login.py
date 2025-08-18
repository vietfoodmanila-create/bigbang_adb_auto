# flows_login.py
# Login theo ảnh + vùng cố định, đồng bộ với flows_logout.py
from __future__ import annotations
import time

# ====== import toàn bộ helper dùng chung từ module.py ======
from module import (
    log_wk as _log,
    adb_safe as _adb_safe,
    tap as _tap,
    tap_center as _tap_center,
    sleep_coop as _sleep_coop,
    aborted as _aborted,
    grab_screen_np as _grab_screen_np,
    find_on_frame as _find_on_frame,
    DEFAULT_THR as _THR_DEFAULT,
    type_text as _type_text,
    back as _back,
    state_simple as _state_simple,
)

# ================== VÙNG ==================
REG_CLEAR_EMAIL_X       = (645, 556, 751, 731)
REG_EMAIL_EMPTY         = (146, 586, 756, 720)
REG_CLEAR_PASSWORD_X    = (645, 688, 750, 881)
REG_PASSWORD_EMPTY      = (146, 701, 755, 820)
REG_LOGIN_BUTTON        = (156, 846, 761, 951)
REG_DA_DANG_NHAP        = (418, 971, 650, 1068)
REG_XAC_NHAN_DANG_NHAP  = (283, 875, 626, 998)
REG_GAME_LOGIN_BUTTON   = (318, 1183, 590, 1308)
REG_XAC_NHAN_OFFLINE    = (511,1253,790,1363)
REG_ICON_LIEN_MINH      = (598, 1463, 753, 1600)
REG_THONG_BAO           = (315, 228, 620, 375)

# ================== ẢNH ==================
IMG_CLEAR_EMAIL_X       = "images/login/clear_email_x.png"
IMG_EMAIL_EMPTY         = "images/login/email_empty.png"
IMG_CLEAR_PASSWORD_X    = "images/login/clear_password_x.png"
IMG_PASSWORD_EMPTY      = "images/login/password_empty.png"
IMG_LOGIN_BUTTON        = "images/login/login_button.png"
IMG_DA_DANG_NHAP        = "images/login/da_dang_nhap.png"
IMG_XAC_NHAN_DANG_NHAP  = "images/login/xac_nhan_dang_nhap.png"
IMG_GAME_LOGIN_BUTTON   = "images/login/game_login_button.png"
IMG_XAC_NHAN_OFFLINE    = "images/login/xac_nhan_offline.png"
IMG_ICON_LIEN_MINH      = "images/login/icon_lien_minh.png"
IMG_THONG_BAO           = "images/login/thong-bao.png"

# ================== GAME PKG/ACT (đồng bộ test) ==================
GAME_PKG = "com.phsgdbz.vn"
GAME_ACT = "com.phsgdbz.vn/org.cocos2dx.javascript.GameTwActivity"


def _sleep(s: float):
    time.sleep(s)

# ------------------ bước phụ: chọn server (đặc thù login) ------------------
def select_server(wk, server: str) -> bool:
    """
    Đặc thù flow login (nếu cần) → để trong file này.
    TODO: bạn sẽ bổ sung sau bằng ảnh/vùng riêng.
    """
    if not server:
        return True
    _log(wk, f"(TODO) Chọn server: {server}")
    return True

# === Tap 3 điểm trước khi bắt đầu login (đặc thù login)
def _pre_login_taps(wk):
    # Bấm 3 điểm để đóng tips/ads, mở bàn phím, v.v.
    seq = [(690, 650, 0.15), (693, 758, 0.15), (690, 650, 0.15)]
    for x, y, delay in seq:
        _tap(wk, x, y)
        _sleep(delay)

# ------------------ login pipeline ------------------
def login_once(wk, email: str, password: str, server: str = "", date: str = "") -> bool:
    """
    Tiến trình login (đặc thù):
      - Đảm bảo đang ở màn hình login (caller nên gọi logout trước, nhưng vẫn tự check)
      - Tap 3 điểm
      - Clear & nhập email/password
      - (tuỳ chọn) chọn server
      - Nhấn Login
      - Khi không thấy cặp 'ĐÃ ĐĂNG NHẬP' + 'VÀO GAME' → ưu tiên đóng 'thông báo', nếu không thì thử 'XÁC NHẬN ĐĂNG NHẬP'
      - Nếu báo offline → xác nhận
      - Chờ icon liên minh → OK
    """
    if _aborted(wk):
        _log(wk, "⛔ Hủy trước khi login.")
        return False
    _log(wk, "Bắt đầu LOGIN…")

    # Nếu không ở need_login, thử back nhẹ vài lần để lộ form
    st = _state_simple(wk, package_hint=GAME_PKG)
    if st != "need_login":
        _log(wk, f"State hiện tại: {st} → BACK 2 lần cho về form.")
        _back(wk, times=2, wait_each=0.4)
        if not _sleep_coop(wk, 0.6):
            return False

    # Tap 3 điểm trước khi login
    _pre_login_taps(wk)
    if _aborted(wk):
        return False

    # 1) Clear & nhập email
    img = _grab_screen_np(wk)
    ok, pt, sc = _find_on_frame(img, IMG_CLEAR_EMAIL_X, region=REG_CLEAR_EMAIL_X, threshold=0.86)
    _log(wk, f"Tìm clear-email-X: ok={ok}, score={sc:.3f}, pt={pt}")
    del img
    if ok and pt:
        _tap(wk, *pt)
        if not _sleep_coop(wk, 0.2):
            return False
    _tap_center(wk, REG_EMAIL_EMPTY)
    if not _sleep_coop(wk, 0.2):
        return False
    _type_text(wk, email)
    if not _sleep_coop(wk, 0.2):
        return False

    # 2) Clear & nhập password
    img = _grab_screen_np(wk)
    ok, pt, sc = _find_on_frame(img, IMG_CLEAR_PASSWORD_X, region=REG_CLEAR_PASSWORD_X, threshold=0.86)
    _log(wk, f"Tìm clear-password-X: ok={ok}, score={sc:.3f}, pt={pt}")
    del img
    if ok and pt:
        _tap(wk, *pt)
        if not _sleep_coop(wk, 0.2):
            return False
    _tap_center(wk, REG_PASSWORD_EMPTY)
    if not _sleep_coop(wk, 0.2):
        return False
    _type_text(wk, password)
    if not _sleep_coop(wk, 0.2):
        return False

    # 3) (tuỳ chọn) chọn server
    if not select_server(wk, server):
        _log(wk, "Chọn server thất bại.")
        return False
    if _aborted(wk):
        return False

    # 4) Nhấn Login
    img = _grab_screen_np(wk)
    ok, pt, sc = _find_on_frame(img, IMG_LOGIN_BUTTON, region=REG_LOGIN_BUTTON, threshold=0.86)
    _log(wk, f"Tìm login_button: ok={ok}, score={sc:.3f}, pt={pt}")
    del img
    if ok and pt:
        _tap(wk, *pt)
    else:
        _log(wk, "Không thấy ảnh login_button → tap trung tâm vùng.")
        _tap_center(wk, REG_LOGIN_BUTTON)
    if not _sleep_coop(wk, 1.0):
        return False

    # ===== 5) PHA "VÀO GAME" + fallback 'XÁC NHẬN ĐĂNG NHẬP' + xử lý THÔNG BÁO =====
    pressed_once = False
    phase_deadline = time.time() + 60  # tối đa 60s cho cả pha

    def _both_buttons(img_now):
        ok_da, _, sc_da = _find_on_frame(img_now, IMG_DA_DANG_NHAP, region=REG_DA_DANG_NHAP, threshold=0.86)
        ok_game, pt_game, sc_game = _find_on_frame(img_now, IMG_GAME_LOGIN_BUTTON, region=REG_GAME_LOGIN_BUTTON,
                                                   threshold=0.86)
        _log(wk, f"Check cặp nút: da_dang_nhap(ok={ok_da}, sc={sc_da:.3f}), vao_game(ok={ok_game}, sc={sc_game:.3f})")
        return ok_da, ok_game, pt_game

    while time.time() < phase_deadline:
        if _aborted(wk):
            return False

        img = _grab_screen_np(wk)
        ok_da, ok_game, pt_game = _both_buttons(img)

        if ok_da and ok_game:
            if pt_game:
                _tap(wk, *pt_game)
                pressed_once = True
                del img
                if not _sleep_coop(wk, 2.0):
                    return False
                continue
            else:
                del img
                if not _sleep_coop(wk, 0.5):
                    return False
                continue

        # Khi KHÔNG thấy cả hai → ƯU TIÊN xử lý THÔNG BÁO nếu có
        if (not ok_da) and (not ok_game):
            ok_tb = False
            try:
                ok_tb, _, _ = _find_on_frame(img, IMG_THONG_BAO, region=REG_THONG_BAO, threshold=0.86)
            except Exception:
                ok_tb = False

            if ok_tb:
                _log(wk, "Thấy 'thong-bao' → bấm đóng cho tới khi biến mất…")
                del img
                for _ in range(20):  # an toàn
                    _tap(wk, 443, 1300)
                    if not _sleep_coop(wk, 1.5):
                        return False
                    img_tb = _grab_screen_np(wk)
                    still_tb, _, _ = _find_on_frame(img_tb, IMG_THONG_BAO, region=REG_THONG_BAO, threshold=0.86)
                    del img_tb
                    if not still_tb:
                        _log(wk, "Đã đóng xong tất cả 'thong-bao'.")
                        break
                continue

            # Không có thông báo → thử 'XÁC NHẬN ĐĂNG NHẬP'
            ok_xn, pt_xn, sc_xn = _find_on_frame(
                img, IMG_XAC_NHAN_DANG_NHAP, region=REG_XAC_NHAN_DANG_NHAP, threshold=0.86
            )
            _log(wk, f"Check 'XÁC NHẬN ĐĂNG NHẬP': ok={ok_xn}, score={sc_xn:.3f}, pt={pt_xn}")
            if ok_xn and pt_xn:
                _tap(wk, *pt_xn)
                del img
                if not _sleep_coop(wk, 1.0):
                    return False
                continue

            del img
            if pressed_once:
                _log(wk, "Cả 'đã đăng nhập' và 'vào game' đã biến mất → sang bước kế tiếp.")
                break

        else:
            del img

        if not _sleep_coop(wk, 0.5):
            return False

    # ===== 6) Kiểm tra 'xác nhận offline' một vài nhịp ngắn (nếu có) =====
    for _ in range(5):
        if _aborted(wk):
            return False
        img = _grab_screen_np(wk)
        ok, pt, sc = _find_on_frame(img, IMG_XAC_NHAN_OFFLINE, region=REG_XAC_NHAN_OFFLINE, threshold=0.86)
        _log(wk, f"Check 'xác nhận offline': ok={ok}, score={sc:.3f}, pt={pt}")
        del img
        if ok and pt:
            _tap(wk, *pt)
            if not _sleep_coop(wk, 1.0):
                return False
            break
        if not _sleep_coop(wk, 0.5):
            return False

    # ===== 7) Đợi vào game (KHÔNG bấm ESC trong giai đoạn chờ) =====
    end = time.time() + 60
    while time.time() < end:
        if _aborted(wk):
            return False
        st = _state_simple(wk, package_hint=GAME_PKG)
        if st == "gametw":
            img = _grab_screen_np(wk)
            ok, pt, sc = _find_on_frame(img, IMG_ICON_LIEN_MINH, region=REG_ICON_LIEN_MINH, threshold=0.86)
            _log(wk, f"Đợi icon liên minh: ok={ok}, score={sc:.3f}")
            del img
            if ok:
                _log(wk, "LOGIN OK — đã vào game.")
                return True
        if not _sleep_coop(wk, 1.0):
            return False

    _log(wk, "LOGIN FAIL — quá thời gian đợi vào game.")
    return False