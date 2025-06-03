from tortoise import fields, models

from server.module.common.utils import get_uuid4_id


class Tool(models.Model):
    """工具模型"""

    code = fields.CharField(max_length=32, default=get_uuid4_id, primary_key=True)  # 工具代码
    name = fields.CharField(max_length=128, unique=True)
    description = fields.CharField(max_length=512, null=True)  # 工具描述
    context = fields.TextField(null=True)  # 直接写markdown文本
    pics = fields.JSONField(default='[]', null=True)  # 工具图片列表，存储为JSON格式
    tags = fields.ManyToManyField("models.Tag", related_name="tool_tags", through="rs_tool_tag")
    link = fields.CharField(max_length=256, null=True)  # 下载链接
    passwd = fields.CharField(max_length=64, null=True)  # 下载密码
    create_time = fields.DatetimeField(auto_now_add=True)
    update_time = fields.DatetimeField(auto_now=True)
    price = fields.FloatField(default=0.0)  # 工具价格
    is_public = fields.BooleanField(default=True)  # 是否公开

    class Meta:
        table = 'tb_tool'
