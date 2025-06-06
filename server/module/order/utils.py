import pyotp

from server.config.settings import DEBUG
from server.module.common.exceptions import AuthorizationFailed, BadRequest
from server.module.common.utils import get_now_UTC_time
from server.module.order.models import Order


def verify_totp_code(secret: str, code: str) -> bool:
    """验证TOTP动态码"""
    totp = pyotp.TOTP(secret)
    return totp.verify(code)


async def varify_code(check_method: int, old_order: Order, code: str) -> bool:
    """验证验证码"""
    if DEBUG:
        return True

    if check_method == 1:
        if not verify_totp_code(Order.totp_secret, code):
            return AuthorizationFailed("动态码错误")
    elif check_method == 2:
        code = code.strip().upper()  # 确保验证码是大写
        if not old_order.email_verify_code:
            return BadRequest("请先发送验证码邮件")
        if old_order.email_verify_code != code or old_order.email_verify_expire < get_now_UTC_time():
            return BadRequest("验证码错误或失效")
        old_order.email_verify_code = None  # 验证成功后清除验证码
        old_order.email_verify_expire = None
        await old_order.save()
    else:
        return BadRequest("无效的验证方式")
    return True
