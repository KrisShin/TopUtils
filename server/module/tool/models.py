import os

from tortoise import fields

from config.settings import DEFAULT_AVATAR_PATH, HTTP_ADDR
from module.common.models import BaseModel


class Role(BaseModel):
    name = fields.CharField(max_length=128, unique=True)
    description = fields.CharField(max_length=512, null=True)
    is_system_role = fields.BooleanField(default=False, db_index=True)
    page_menu = fields.JSONField(default=[])

    class Meta:
        table = 'tb_pfev_role'


class User(BaseModel):
    nickname = fields.CharField(max_length=64)
    username = fields.CharField(max_length=256, unique=True)
    role = fields.ForeignKeyField("models.Role", related_name="role_users")
    phone = fields.CharField(max_length=15, null=True)
    email = fields.CharField(max_length=128, null=True)
    post = fields.CharField(max_length=64, null=True, db_index=True)  # user post, fill by user.
    password = fields.CharField(max_length=256)
    avatar = fields.CharField(max_length=256, null=True)
    standard_workday = fields.FloatField(null=True, default=22)  # should devote workday per month.
    last_login_ip = fields.CharField(max_length=32, null=True)
    last_login_time = fields.DatetimeField(null=True)
    join_date = fields.DateField(null=True)
    leave_date = fields.DateField(null=True)
    disabled = fields.BooleanField(default=False, db_index=True)

    class Meta:
        table = 'tb_pfev_user'
        ordering = ('nickname',)

    @property
    def avatar_url(self):
        return os.path.join(os.path.join(HTTP_ADDR, DEFAULT_AVATAR_PATH), self.avatar)


class Group(BaseModel):
    name = fields.CharField(max_length=128, null=True)

    class Meta:
        table = 'tb_group'


class UserGroup(BaseModel):
    group = fields.ForeignKeyField("models.Group", related_name="group_user")
    user = fields.ForeignKeyField("models.User", related_name="user_group")
    is_leader = fields.BooleanField(default=False)

    class Meta:
        table = 'rs_user_group'


class UserWeekPerformance(BaseModel):
    user = fields.ForeignKeyField("models.User", related_name="performans")
    thursday = fields.DateField(null=False, db_index=True)  # Determine which month the current week belongs to by Thursday's date
    score = fields.FloatField(null=True, defalt=100)
    extra_workday = fields.FloatField(null=True)
    description = fields.CharField(max_length=512, null=True)

    class Meta:
        table = 'tb_user_week_perfomance'
        ordering = ('thursday',)
        unique_together = ('user', 'thursday')
