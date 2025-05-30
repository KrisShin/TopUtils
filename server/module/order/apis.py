import io
from fastapi import APIRouter
from fastapi.responses import StreamingResponse
import pyotp
import qrcode

from server.module.common.exceptions import AuthorizationFailed, BadRequest, NoPermission, TooManyRequest
from server.module.common.global_variable import BaseResponse
from server.module.common.utils import get_now_UTC_time
from server.module.order.schemas import AuthRequest, EmailRequest, RebindRequest, TOTPConfirmRequest
from server.module.order.utils import get_order_by_email, verify_totp_code

router = APIRouter()


@router.post("/auth/setup-totp", summary="第一步：为用户设置TOTP")
async def setup_totp(request: EmailRequest):
    """
    为指定邮箱生成一个新的TOTP密钥和对应的二维码。
    用户需要扫描这个二维码来绑定他们的身份验证器应用。
    """
    order = await get_order_by_email(request.email)

    # 如果已启用，需要先走解绑流程（此处简化，直接重新生成）
    # if order.is_totp_enabled:
    #     raise HTTPException(status_code=400, detail="TOTP is already enabled.")

    # 生成一个32位的Base32密钥
    secret = pyotp.random_base32()
    order.totp_secret = secret
    order.is_totp_enabled = False  # 等待用户验证后才正式启用
    await order.save()

    # 生成URI，格式为：otpauth://totp/YourAppName:user@email.com?secret=...&issuer=YourAppName
    uri = pyotp.totp.TOTP(secret).provisioning_uri(name=order.email, issuer_name="您的软件名称")

    # 使用qrcode库生成二维码图片
    img = qrcode.make(uri)
    buf = io.BytesIO()
    img.save(buf, "PNG")
    buf.seek(0)

    # 以图片流的形式返回二维码
    return StreamingResponse(buf, media_type="image/png")


@router.post("/auth/confirm-totp", summary="第二步：验证并启用TOTP")
async def confirm_totp(request: TOTPConfirmRequest):
    """
    用户输入从验证器App上看到的第一个动态码，以完成绑定。
    """
    order = await get_order_by_email(request.email)

    if not order.totp_secret:
        raise BadRequest("请先调用 setup-totp 接口")

    if not verify_totp_code(order.totp_secret, request.code):
        raise BadRequest("动态码错误")

    order.is_totp_enabled = True

    # 首次绑定时，将当前设备哈希也记录下来
    # 在实际应用中，这个哈希应该在调用此接口时由客户端传来
    # 此处为演示，我们先置空
    if not order.device_info_hashed:
        # 提示用户下一步需要登录来绑定第一个设备
        pass

    await order.save()

    return BaseResponse("身份验证器绑定成功！")


@router.post("/auth/login", summary="软件客户端登录接口")
async def software_login(request: AuthRequest):
    """
    软件每次启动时调用此接口进行验证。
    """
    order = await get_order_by_email(request.email)

    if not order.is_totp_enabled:
        raise NoPermission("请先绑定身份验证器")

    if not order.is_active:
        raise NoPermission("订阅已过期或无效")

    if not verify_totp_code(order.totp_secret, request.code):
        raise NoPermission("动态码错误")

    # 如果是首次登录，或者数据库中没有设备信息，则将当前设备绑定
    if not order.device_info_hashed:
        order.device_info_hashed = request.device_hash
        await order.save()
        return BaseResponse("首次登录成功，设备已绑定！")

    # 检查设备哈希是否匹配
    if order.device_info_hashed != request.device_hash:
        raise NoPermission("设备不匹配，如果更换了设备，请使用换绑接口。")

    return BaseResponse()


@router.post("/auth/rebind", response_model=BaseResponse, summary="设备换绑接口")
async def rebind_device(request: RebindRequest):
    """
    当用户在已绑定设备之外的电脑上登录时，调用此接口进行换绑。
    """
    order = await get_order_by_email(request.email)

    if not order.is_totp_enabled or not order.is_active:
        raise NoPermission("账户状态异常")

    if not verify_totp_code(order.totp_secret, request.code):
        raise AuthorizationFailed("动态码错误")

    # 检查换绑冷却时间
    if order.is_rebind_in_cooldown:
        raise TooManyRequest("换绑操作过于频繁，请24小时后再试")

    # 执行换绑
    order.device_info_hashed = request.new_device_hash
    order.last_rebind_time = get_now_UTC_time()
    await order.save()

    return BaseResponse("设备换绑成功！")
