# cloud.py — lớp tương thích, chuyển hết sang module.py
from module import api_login, api_logout, api_license_status, stable_device_uid

class CloudClient:
    def __init__(self): pass
    def login(self, email, password, device_uid=None, device_name=None):
        return api_login(email, password, device_uid=device_uid, device_name=device_name)
    def logout(self):
        return api_logout()
    def license_status(self):
        return api_license_status()

def get_device_uid() -> str:
    return stable_device_uid()
