# api_client.py (精简后)
# ... (保留所有 import 和 get_device_hash, is_running_in_vm 函数) ...

from typing import Optional
import httpx

from widgets.utils import get_device_hash

# --- 配置 ---
BASE_URL = "https://util.toputils.top/api"  # 您的 FastAPI 服务器地址


class ApiClient(object):
    """封装所有与后端API的交互，移除打印语句"""

    def __init__(self, base_url):
        self.base_url = base_url
        self.tool_code = None
        self.order_id = None  # 用于存储订单ID
        self.device_hash = get_device_hash()  # 获取当前设备的唯一标识符

    def setup_totp(self, order_id: str) -> Optional[str]:
        """请求服务器生成TOTP URI"""
        try:
            response = httpx.post(f"{self.base_url}/order/auth/setup-totp", json={"order_id": order_id})
            if response.status_code == 200:
                return response.json().get("uri"), None
            elif response.status_code < 500:
                return None, response.json()['detail'][0]['msg']
            else:
                response.raise_for_status()
        except httpx.HTTPStatusError as e:
            return None, str(e)

    def confirm_totp(self, order_id: str, email: str, code: str):
        try:
            response = httpx.post(f"{self.base_url}/order/auth/confirm-totp", json={"order_id": order_id, "email": email, "code": code})
            if response.status_code == 200:
                return response.json()['data']['token'], None
            elif response.status_code < 500:
                return None, response.json()['detail'][0]['msg']
            else:
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
            elif response.status_code < 500:
                return None, response.json()['detail'][0]['msg']
            else:
                response.raise_for_status()
        except httpx.HTTPStatusError as e:
            from traceback import print_exc

            print_exc()
            return None, str(e)

    def send_email_code(self, order_id: str):
        """发送邮箱验证码"""
        try:
            response = httpx.post(f"{self.base_url}/order/auth/send-email-code", json={"order_id": order_id})
            if response.status_code == 200:
                return response.json(), None
            elif response.status_code < 500:
                return None, response.json()['detail'][0]['msg']
            else:
                response.raise_for_status()
        except httpx.HTTPStatusError as e:
            return None, str(e)

    def rebind(self, email: str, code: str, check_method: str = "1"):
        try:
            response = httpx.post(
                f"{self.base_url}/order/auth/rebind",
                json={
                    "email": email,
                    "code": code,
                    'check_method': check_method,
                    "device_hash": self.device_hash,
                    'tool_code': self.tool_code,
                    'order_id': self.order_id,
                },  # 添加当前订单ID,
            )
            if response.status_code == 200:
                return response.json()['data']['token'], None
            elif response.status_code < 500:
                return None, response.json()['detail'][0]['msg']
            else:
                response.raise_for_status()
        except httpx.HTTPStatusError as e:
            return None, str(e)

    def bind(self):
        try:
            response = httpx.post(f"{self.base_url}/order/bind", json={"tool_code": self.tool_code, "device_hash": self.device_hash})
            if response.status_code == 200:
                self.order_id = response.json()['data']['order_id']  # 保存订单ID
                return response.json()['data']['order_id'], None
            elif response.status_code < 500:
                return None, response.json()['detail'][0]['msg']
            else:
                response.raise_for_status()
        except httpx.HTTPStatusError as e:
            return None, str(e)

    def is_valid(self):
        """检查当前设备是否有效"""
        try:
            response = httpx.post(f"{self.base_url}/order/is-valid", json={"order_id": self.order_id})
            if response.status_code == 200:
                return response.json()['data']['token'], None
            elif response.status_code < 500:
                return None, response.json()['detail'][0]['msg']
            else:
                response.raise_for_status()
        except httpx.HTTPStatusError as e:
            return False, str(e)

    def check_order_exist(self, email: str, current_order_id: str):
        try:
            response = httpx.post(
                f"{self.base_url}/order/check-order-exist",  # 假设的API端点
                json={"email": email, "tool_code": self.tool_code, "current_device_hash": self.device_hash, "current_order_id": current_order_id},  # 刚刚通过bind获取的ID
            )
            if response.status_code == 200:
                return response.json()['data'], None
            elif response.status_code < 500:
                return None, response.json()['detail'][0]['msg']
            else:
                response.raise_for_status()
        except httpx.HTTPStatusError as e:
            from traceback import print_exc

            print_exc()
            return None, str(e)
        except Exception as e:  # 更通用的异常捕获
            return None, str(e)

    def check_subscription_status(self):
        try:
            response = httpx.post(f"{self.base_url}/order/sub-check", json={"order_id": self.order_id})
            token_str = response.json().get("data", {}).get("token")
            if not token_str:
                return None, "服务器未返回有效令牌"
            if response.status_code == 200:
                return token_str, None
            elif response.status_code < 500:
                return None, response.json()['detail'][0]['msg']
            else:
                response.raise_for_status()
        except httpx.HTTPStatusError as e:
            from traceback import print_exc

            print_exc()
            return None, str(e)
        except Exception as e:  # 更通用的异常捕获
            return None, str(e)
