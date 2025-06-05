# api_client.py (精简后)
# ... (保留所有 import 和 get_device_hash, is_running_in_vm 函数) ...

from typing import Optional
import httpx

from widgets.utils import get_device_hash

# --- 配置 ---
BASE_URL = "https://util.toputils.top/api"  # 您的 FastAPI 服务器地址
TOOL_CODE = '2ab2171ad8ba4521baf98ac5ff78a746'


class ApiClient:
    """封装所有与后端API的交互，移除打印语句"""

    def __init__(self, base_url):
        self.base_url = base_url
        self.tool_code = TOOL_CODE
        self.order_id = None  # 用于存储订单ID
        self.device_hash = get_device_hash()  # 获取当前设备的唯一标识符

    def setup_totp(self, order_id: str) -> Optional[str]:
        """请求服务器生成TOTP URI"""
        try:
            response = httpx.post(f"{self.base_url}/order/auth/setup-totp", json={"order_id": order_id})
            response.raise_for_status()  # 如果状态码不是2xx，则抛出异常
            # 返回JSON中的URI字符串
            return response.json().get("uri"), None
        except httpx.HTTPStatusError as e:
            return None, str(e)

    def confirm_totp(self, order_id: str, email: str, code: str):
        try:
            response = httpx.post(f"{self.base_url}/order/auth/confirm-totp", json={"order_id": order_id, "email": email, "code": code})
            if response.status_code == 200:
                return response.json()['data']['token'], None
            else:
                return None, response.json()['detail'][0]['msg']
            response.raise_for_status()
        except httpx.HTTPStatusError as e:
            return None, str(e)

    def login(self, order_id: str, code: str, check_method: str = "1"):
        try:
            # 使用身份验证器App
            response = httpx.post(
                f"{self.base_url}/order/auth/login",
                json={"order_id": order_id, "code": code, "device_hash": self.device_hash, "check_method": int(check_method)},
            )
            if response.status_code == 200:
                return response.json()['data']['token'], None
            else:
                return None, response.json()['detail'][0]['msg']
        except httpx.HTTPStatusError as e:
            from traceback import print_exc

            print_exc()
            return None, str(e)

    def send_email_code(self, order_id: str):
        """发送邮箱验证码"""
        try:
            response = httpx.post(f"{self.base_url}/order/auth/send-email-code", json={"order_id": order_id})
            response.raise_for_status()
            return response.json(), None
        except httpx.HTTPStatusError as e:
            return None, str(e)

    def rebind(self, email: str, code: str):
        try:
            response = httpx.post(f"{self.base_url}/order/auth/rebind", json={"email": email, "code": code, "new_device_hash": self.device_hash})
            response.raise_for_status()
            return response.json(), None
        except httpx.HTTPStatusError as e:
            return None, str(e)

    def bind(self):
        try:
            response = httpx.post(f"{self.base_url}/order/bind", json={"tool_code": self.tool_code, "device_hash": self.device_hash})
            response.raise_for_status()
            return response.json()['data']['order_id'], None
        except httpx.HTTPStatusError as e:
            return None, str(e)

    def is_valid(self):
        """检查当前设备是否有效"""
        try:
            response = httpx.post(f"{self.base_url}/order/is-valid", json={"order_id": self.order_id})
            response.raise_for_status()
            return response.json()['data']['token'], None
        except httpx.HTTPStatusError as e:
            return False, str(e)
