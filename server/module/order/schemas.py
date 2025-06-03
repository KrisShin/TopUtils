# schemas.py
from pydantic import BaseModel, EmailStr, Field


class EmailRequest(BaseModel):
    email: EmailStr


class OrderIdRequest(BaseModel):
    order_id: str


class TOTPConfirmRequest(OrderIdRequest):
    code: str = Field(..., min_length=6, max_length=6, description="6位TOTP动态码")


class DeviceHashRequest(BaseModel):
    device_hash: str


class ToolIdRequest(BaseModel):
    tool_code: str


class ToolDeviceBindRequest(ToolIdRequest, DeviceHashRequest): ...


class AuthRequest(TOTPConfirmRequest, DeviceHashRequest): ...


class RebindRequest(TOTPConfirmRequest):
    new_device_hash: str


class TOTPSetupResponse(BaseModel):
    uri: str
    message: str = "请使用验证器App扫描二维码或手动输入密钥"
