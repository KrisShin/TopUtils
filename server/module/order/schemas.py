# schemas.py
from pydantic import BaseModel, EmailStr, Field


class EmailRequest(BaseModel):
    email: EmailStr

class TOTPConfirmRequest(BaseModel):
    email: EmailStr
    code: str = Field(..., min_length=6, max_length=6, description="6位TOTP动态码")

class AuthRequest(BaseModel):
    email: EmailStr
    code: str = Field(..., min_length=6, max_length=6)
    device_hash: str

class RebindRequest(BaseModel):
    email: EmailStr
    code: str = Field(..., min_length=6, max_length=6)
    new_device_hash: str

class AuthSuccessResponse(BaseModel):
    """认证成功的响应模型"""
    message: str = "Authentication successful"
    # 在实际应用中，这里应该返回一个短期的 session token
    # token: str