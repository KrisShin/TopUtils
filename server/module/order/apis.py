from datetime import timedelta
import random
import string
from fastapi import APIRouter
import pyotp
from jose import jwt

from server.config.settings import ALGORITHM
from server.module.common.email_utils import send_email
from server.module.common.exceptions import AuthorizationFailed, BadRequest, NoPermission, TooManyRequest
from server.module.common.global_variable import BaseResponse, DataResponse
from server.module.common.utils import get_now_UTC_time
from server.module.order.models import Order
from server.module.order.schemas import (
    BindRequest,
    CheckOrderExistRequest,
    OrderIdRequest,
    ReBindRequest,
    TOTPConfirmRequest,
    TOTPSetupResponse,
    ToolDeviceBindRequest,
)
from server.module.order.utils import verify_totp_code

router = APIRouter()


@router.post("/auth/setup-totp", response_model=TOTPSetupResponse, summary="第一步：为用户请求TOTP设置信息")  # 使用新的响应模型
async def setup_totp(request: OrderIdRequest):
    """
    为指定邮箱生成一个新的TOTP密钥，并返回用于生成二维码的URI。
    客户端收到URI后，自行生成二维码。
    """
    order = await Order.get_or_none(id=request.order_id).prefetch_related("tool")

    secret = pyotp.random_base32()
    order.totp_secret = secret
    order.is_totp_enabled = False
    await order.save()

    uri = pyotp.totp.TOTP(secret).provisioning_uri(name=order.email, issuer_name=order.tool.name)

    # 返回包含URI的JSON响应
    return TOTPSetupResponse(uri=uri)


@router.post("/auth/confirm-totp", summary="第二步：验证并启用TOTP")
async def confirm_totp(request: TOTPConfirmRequest):
    """
    用户输入从验证器App上看到的第一个动态码，以完成绑定。
    """
    order = await Order.get_or_none(id=request.order_id)

    if not order.totp_secret:
        raise BadRequest("请先调用 setup-totp 接口")

    if not verify_totp_code(order.totp_secret, request.code):
        raise BadRequest("动态码错误")
    order.email = request.email
    order.is_totp_enabled = True

    await order.save()
    await send_email(order.email, "Top Utils 绑定成功", "您的身份验证器已成功绑定。")

    token_dict = {
        'tool_code': order.tool_id,
        'device_hash': order.device_info_hashed,
        'order_id': order.id,
        'email': order.email,
        'expire_time': order.expire_time,
    }
    encoded_jwt = jwt.encode(token_dict, '_'.join((order.tool_id, order.device_info_hashed, order.id, order.email)), algorithm=ALGORITHM)
    return DataResponse(data={'token': encoded_jwt})


@router.post("/auth/login", summary="软件客户端登录接口")
async def software_login(request: BindRequest):
    """
    软件每次启动时调用此接口进行验证。
    """
    order = await Order.get_or_none(id=request.order_id)

    if not order.is_totp_enabled:
        raise BadRequest("请先绑定身份验证器")

    if not order.is_active:
        raise BadRequest("订阅已过期或无效")

    if request.check_method == 1:
        if not verify_totp_code(order.totp_secret, request.code):
            raise BadRequest("验证码错误或失效")
    elif request.check_method == 2:
        request.code = request.code.strip().upper()  # 确保验证码是大写
        if order.email_verify_code != request.code or order.email_verify_expire < get_now_UTC_time():
            raise BadRequest("验证码错误或失效")
        order.email_verify_code = None  # 验证成功后清除验证码
        order.email_verify_expire = None
        await order.save()

    # 检查设备哈希是否匹配
    if order.device_info_hashed != request.device_hash:
        raise NoPermission("设备不匹配，如果更换了设备，请使用换绑接口。")

    token_dict = {
        'tool_code': order.tool_id,
        'device_hash': order.device_info_hashed,
        'order_id': order.id,
        'email': order.email,
        'expire_time': order.expire_time,
    }
    encoded_jwt = jwt.encode(token_dict, '_'.join((order.tool_id, order.device_info_hashed, order.id, order.email)), algorithm=ALGORITHM)
    return DataResponse(data={'token': encoded_jwt})


@router.post("/auth/send-email-code", summary="发送邮箱验证码接口")
async def send_email_code(request: OrderIdRequest):
    """
    发送邮箱验证码，用于验证用户身份。
    """
    order = await Order.get_or_none(id=request.order_id)
    if not order:
        raise BadRequest("订单不存在")

    if not order.is_totp_enabled:
        raise BadRequest("请先绑定身份验证器")

    if not order.is_active:
        raise BadRequest("订阅已过期或无效")

    code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))  # 生成6位随机大写字母验证码
    order.email_verify_code = code
    order.email_verify_expire = get_now_UTC_time() + timedelta(minutes=10)  # 验证码有效期为5分钟
    await order.save()

    await send_email(order.email, "Top Utils 验证码", f"您的验证码是：{code}，请在5分钟内使用。")

    return BaseResponse("验证码已发送，请查收您的邮箱。")


@router.post("/auth/rebind", summary="设备换绑接口")
async def rebind_device(request: ReBindRequest):
    """
    当用户在已绑定设备之外的电脑上登录时，调用此接口进行换绑。
    """
    old_order = await Order.get_or_none(email=request.email, tool_id=request.tool_code)
    if not old_order:
        raise BadRequest("用户或订单不存在")

    if not old_order.is_totp_enabled or not old_order.is_active:
        raise NoPermission("账户状态异常")

    # 检查换绑冷却时间
    if old_order.is_rebind_in_cooldown:
        raise TooManyRequest("换绑操作过于频繁，请24小时后再试")

    if request.check_method == 1:
        if not verify_totp_code(old_order.totp_secret, request.code):
            raise AuthorizationFailed("动态码错误")
    elif request.check_method == 2:
        request.code = request.code.strip().upper()  # 确保验证码是大写
        if old_order.email_verify_code != request.code or old_order.email_verify_expire < get_now_UTC_time():
            raise BadRequest("验证码错误或失效")
        old_order.email_verify_code = None  # 验证成功后清除验证码
        old_order.email_verify_expire = None
        await old_order.save()
    else:
        raise BadRequest("无效的验证方式")

    # 执行换绑
    await Order.filter(id=request.order_id).delete()  # 删除当前设备的订单记录
    old_order.device_info_hashed = request.device_hash
    old_order.last_rebind_time = get_now_UTC_time()
    await old_order.save()

    token_dict = {
        'tool_code': old_order.tool_id,
        'device_hash': old_order.device_info_hashed,
        'order_id': old_order.id,
        'email': old_order.email,
        'expire_time': old_order.expire_time,
    }
    encoded_jwt = jwt.encode(
        token_dict, '_'.join((old_order.tool_id, old_order.device_info_hashed, old_order.id, old_order.email)), algorithm=ALGORITHM
    )
    return DataResponse(data={'token': encoded_jwt})


@router.post("/bind", summary="设备工具绑定接口")
async def bind_device(request: ToolDeviceBindRequest):
    """
    当用户在已绑定设备之外的电脑上登录时，调用此接口进行换绑。
    """
    order = await Order.get_or_none(device_info_hashed=request.device_hash, tool_id=request.tool_code)
    if order:
        if not order.is_active:
            raise BadRequest("试用期已结束或订阅过期, 请先续费")
    else:
        order = await Order.create(device_info_hashed=request.device_hash, tool_id=request.tool_code)

    return DataResponse(data={'order_id': order.id})


@router.post("/is-valid", summary="设备工具绑定接口")
async def is_valid(request: OrderIdRequest):
    """
    当用户在已绑定设备之外的电脑上登录时，调用此接口进行换绑。
    """
    order = await Order.get_or_none(id=request.order_id)
    if not order:
        raise BadRequest("订单不存在")
    if order.is_active:
        token_dict = {
            'tool_code': order.tool_id,
            'device_hash': order.device_info_hashed,
            'order_id': order.id,
            'email': order.email,
            'expire_time': order.expire_time,
        }
        encoded_jwt = jwt.encode(token_dict, '_'.join((order.tool_id, order.device_info_hashed, order.id)), algorithm=ALGORITHM)
        return DataResponse(data={'token': encoded_jwt})
    else:
        raise BadRequest("试用期已结束或订阅过期, 请先续费")


@router.post("/check-order-exist", summary="检查邮箱状态接口")
async def check_order_exist(request: CheckOrderExistRequest):
    """
    检查用户邮箱状态，是否已绑定身份验证器。
    """
    org_order = await Order.get_or_none(email=request.email, tool_id=request.tool_code)
    if not org_order:
        return DataResponse(message="欢迎新用户", data={"status": "ok", "existing_order_id": None})

    new_order = await Order.get_or_none(
        device_info_hashed=request.current_device_hash, tool_id=request.tool_code, id=request.current_order_id
    )
    if not new_order:
        raise BadRequest("当前设备未绑定任何订单")

    if org_order.device_info_hashed != new_order.device_info_hashed:
        if org_order.last_rebind_time and org_order.last_rebind_time > get_now_UTC_time() - timedelta(days=1):
            raise TooManyRequest("24小时内已有换绑操作, 请稍后再试")
        return DataResponse(data={"status": "rebind_required", "existing_order_id": org_order.id})

    return DataResponse(message="邮箱状态正常，已绑定身份验证器。", data={"status": "ok", "existing_order_id": org_order.id})


@router.post('/sub-check', summary="启动脚本时检查订阅")
def check_subscription_status(request: OrderIdRequest):
    """
    运行脚本时检查订阅状态。
    """
    order = Order.get_or_none(id=request.order_id)
    utc_now = get_now_UTC_time()
    if not order:
        raise BadRequest("订单不存在")

    if not order.expire_time:
        order.expire_time = utc_now + timedelta(minutes=5)  # 5分钟试用期

    if not order.is_active:
        raise BadRequest("试用期已结束或订阅过期, 请先续费")
    token_dict = {
        'tool_code': order.tool_id,
        'device_hash': order.device_info_hashed,
        'order_id': order.id,
        'email': order.email,
        'expire_time': order.expire_time,
        'rest_time': order.expire_time - utc_now,
        'reminder': (order.expire_time - utc_now) <= timedelta(minutes=5),  # 是否需要提醒,
    }
    encoded_jwt = jwt.encode(token_dict, '_'.join((order.tool_id, order.device_info_hashed, order.id, order.email)), algorithm=ALGORITHM)
    return DataResponse(data={'token': encoded_jwt})
