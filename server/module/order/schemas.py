# schemas.py
from pydantic import BaseModel, EmailStr, Field


class EmailRequest(BaseModel):
    email: EmailStr


class OrderIdRequest(BaseModel):
    order_id: str


class OrderEmailRequest(EmailRequest, OrderIdRequest): ...


class CodeRequest(BaseModel):
    code: str = Field(..., min_length=6, max_length=6, description="6位验证码")


class TOTPConfirmRequest(OrderIdRequest, EmailRequest):
    code: str = Field(..., min_length=6, max_length=6, description="6位TOTP动态码")


class DeviceHashRequest(BaseModel):
    device_hash: str


class ToolIdRequest(BaseModel):
    tool_code: str


class ToolDeviceBindRequest(ToolIdRequest, DeviceHashRequest): ...


class AuthRequest(OrderIdRequest, CodeRequest, DeviceHashRequest):
    check_method: int = Field(1, description="验证方式，1: TOTP动态码, 2: 邮箱验证码", ge=1, le=2)


class RebindRequest(TOTPConfirmRequest):
    new_device_hash: str


class TOTPSetupResponse(BaseModel):
    uri: str
    message: str = "请使用验证器App扫描二维码或手动输入密钥"
