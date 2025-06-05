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
    
    def check_order_exist(self, email: str, current_order_id: str):
        # 后端需要此信息来判断：
        # 1. email + self.tool_code 是否有订单
        # 2. 如果有，该订单的 device_hash 是否与 self.device_hash 不同
        # 3. 如果不同，该订单的 order_id 是否与 current_order_id 不同
        try:
            response = httpx.post(
                f"{self.base_url}/order/check-order-exist", # 假设的API端点
                json={
                    "email": email,
                    "tool_code": self.tool_code,
                    "current_device_hash": self.device_hash,
                    "current_order_id": current_order_id # 刚刚通过bind获取的ID
                }
            )
            response.raise_for_status()
            return response.json().get("data"), None # 假设data是 {"status": "...", "existing_order_id": "..."}
        except httpx.HTTPStatusError as e:
            return None, self.handle_error(e)
        except Exception as e: # 更通用的异常捕获
            return None, str(e)
        
    def transfer_license_to_current_device(self, target_order_id: str, email: str):
        # 后端需要验证 email 是否有权操作 target_order_id (通常是该订单的注册邮箱)
        # 然后将 target_order_id 的 device_hash 更新为 self.device_hash
        # 并且可能重置该订单的 TOTP 设置
        try:
            response = httpx.post(
                f"{self.base_url}/order/transfer-license", # 假设的API端点
                json={
                    "target_order_id": target_order_id,
                    "new_device_hash": self.device_hash,
                    "email_for_verification": email,
                    "tool_code": self.tool_code
                }
            )
            response.raise_for_status()
            return response.json().get("data"), None # 假设data是 {"success": True}
        except httpx.HTTPStatusError as e:
            return None, self.handle_error(e)
        except Exception as e:
            return None, str(e)
