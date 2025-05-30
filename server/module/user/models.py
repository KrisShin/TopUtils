import os

from tortoise import fields

from server.config.settings import DEFAULT_AVATAR_PATH, HTTP_ADDR
from server.module.common.models import BaseModel


class User(BaseModel):
    nickname = fields.CharField(max_length=64)
    username = fields.CharField(max_length=256, unique=True)
    phone = fields.CharField(max_length=15, null=True)
    email = fields.CharField(max_length=128, null=True)
    password = fields.CharField(max_length=256)
    avatar = fields.CharField(max_length=256, null=True)
    last_login_ip = fields.CharField(max_length=32, null=True)
    last_login_time = fields.DatetimeField(null=True)
    disabled = fields.BooleanField(default=False, db_index=True)

    class Meta:
        table = 'tb_user'
        ordering = ('nickname',)

    @property
    def avatar_url(self):
        return os.path.join(os.path.join(HTTP_ADDR, DEFAULT_AVATAR_PATH), self.avatar)
