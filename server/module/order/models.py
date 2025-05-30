from tortoise import fields

from server.module.common.models import BaseModel
from server.module.common.utils import get_uuid4_id


class Order(BaseModel):
    """订单模型"""

    id = fields.CharField(max_length=32, default=get_uuid4_id, primary_key=True)  # 工具代码
    tool = fields.ForeignKeyField("module.tool.models.Tool", related_name="orders", on_delete=fields.CASCADE)
    access_key = fields.CharField(max_length=64, null=True, default=get_uuid4_id)  # 访问密钥
    secret_key = fields.CharField(max_length=64, null=True, default=get_uuid4_id)  # 密钥
    expire_time = fields.DatetimeField(null=True)  # 过期时间
    user_info = fields.JSONField(null=False)  # 用户信息
    user_info_hashed = fields.CharField(max_length=512, null=True)  # 哈希后的用户信息
    request_ip = fields.CharField(max_length=32, null=True)  # 请求IP
    last_request_time = fields.DatetimeField(auto_now_add=True)  # 请求时间
