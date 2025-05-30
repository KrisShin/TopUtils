import pyotp
from server.module.common.exceptions import BadRequest
from server.module.order.models import Order


async def get_order_by_email(email: str) -> Order:
    """通过邮箱查找订单，如果找不到则抛出异常"""
    order = await Order.get_or_none(email=email)
    if not order:
        raise BadRequest("用户或订单不存在")
    return order


def verify_totp_code(secret: str, code: str) -> bool:
    """验证TOTP动态码"""
    totp = pyotp.TOTP(secret)
    return totp.verify(code)
