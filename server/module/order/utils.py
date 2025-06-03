import pyotp


def verify_totp_code(secret: str, code: str) -> bool:
    """验证TOTP动态码"""
    totp = pyotp.TOTP(secret)
    return totp.verify(code)
