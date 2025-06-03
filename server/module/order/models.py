from datetime import timedelta
from enum import IntEnum
from tortoise import fields
from tortoise.contrib.pydantic import pydantic_model_creator

from server.module.common.models import BaseModel
from server.module.common.utils import get_now_UTC_time, get_uuid4_id


class OrderStatus(IntEnum):
    """订单状态"""

    TRY = 0  # 试用
    SUBSCRIBE = 1  # 订阅


class Order(BaseModel):
    """订单模型（优化后）"""

    id = fields.CharField(max_length=32, default=get_uuid4_id, primary_key=True)
    tool = fields.ForeignKeyField("models.Tool", related_name="orders", on_delete=fields.CASCADE)
    email = fields.CharField(max_length=255, index=True, null=True)  # 用户唯一标识

    # 订阅信息
    expire_time = fields.DatetimeField(null=True)  # 订阅过期时间
    paid_status = fields.IntEnumField(OrderStatus, default=OrderStatus.TRY)

    # TOTP (身份验证器) 相关字段
    totp_secret = fields.CharField(max_length=32, null=True)  # 加密存储的 TOTP 密钥
    is_totp_enabled = fields.BooleanField(default=False)  # TOTP 是否已验证并启用

    # 设备绑定相关字段
    device_info_hashed = fields.CharField(max_length=512, null=True)  # 当前绑定的设备哈希
    last_rebind_time = fields.DatetimeField(null=True)  # 上次换绑时间，用于冷却控制

    email_verify_code = fields.CharField(max_length=6, null=True)  # 邮箱验证码
    email_verify_expire = fields.DatetimeField(null=True)  # 邮箱验证码过期时间

    created_at = fields.DatetimeField(auto_now_add=True)

    # 检查订阅是否有效
    @property
    def is_active(self) -> bool:
        if self.expire_time and self.expire_time < get_now_UTC_time():
            return False
        return True

    # 检查换绑是否在冷却期
    @property
    def is_rebind_in_cooldown(self) -> bool:
        if not self.last_rebind_time:
            return False
        # 冷却时间设为24小时
        return self.last_rebind_time + timedelta(hours=24) > get_now_UTC_time()

    class Meta:
        table = "tb_order"
        # 强制约束：一个工具在一个机器上只能有一个订单
        unique_together = (("tool", "device_info_hashed"), ("tool", "email"))

    def __str__(self):
        return f"Order(id={self.id}, tool={self.tool.name}, status={self.paid_status.name})"


# 创建 Pydantic 模型用于 API 输出
Order_Pydantic = pydantic_model_creator(Order)
