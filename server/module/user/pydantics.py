from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, field_serializer, model_validator
from tortoise.contrib.pydantic import pydantic_model_creator

from server.module.common.constrants import DEFALT_PASSWORD
from server.module.user.models import User
from server.module.user.utils import get_password_hash

UserInfoORMPydantic = pydantic_model_creator(User, name='UserInfoORMPydantic', include=('id', 'nickname', 'phone', 'email', 'role', 'post'))
UserDetailORMPydantic = pydantic_model_creator(User, name='UserDetailORMPydantic', exclude=('password', 'last_login_ip', 'last_login_time'))


class UserCreatePydantic(BaseModel):
    username: str
    nickname: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    post: Optional[str] = None
    password: Optional[str] = None

    @model_validator(mode='after')
    def validate(cls, instance):
        instance.__dict__['password'] = get_password_hash(instance.password or DEFALT_PASSWORD)
        instance.__dict__['nickname'] = instance.nickname or instance.username
        return instance


class UserLoginPydantic(BaseModel):
    username: str
    password: str


class TokenPydantic(BaseModel):
    access_token: str
    token_type: str = 'Bearer'
    prompt_type: Optional[int]


class UserEditPydantic(BaseModel):
    id: Optional[int] = None
    nickname: Optional[str] = None
    avatar: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    post: Optional[str] = None
    username: Optional[str] = None
    standard_workday: Optional[float] = None
    join_date: Optional[date | datetime] = None
    leave_date: Optional[date | datetime] = None
    role_id: Optional[int] = None


class UserInfoPydantic(BaseModel):
    id: int
    key: Optional[int] = None
    nickname: str | None = None
    avatar: str | None = None
    role_id: int
    email: str | None = None
    phone: str | None = None
    post: str | None = None
    disabled: bool | None = False

    class Config:
        from_attributes = True

    @field_serializer('key')
    def serialize_key(self, _):
        return self.id


class UserPydantic(UserInfoPydantic):
    id: int
    username: str
    standard_workday: float
    join_date: date
    leave_date: date | None
    last_login_ip: Optional[str] = None
    last_login_time: Optional[datetime] = None

    class Config:
        from_attributes = True


class UserModifyPasswordPydantic(BaseModel):
    old_password: str
    new_password: str


class UserResetPasswordPydantic(BaseModel):
    user_id: int | str


class UserDisablePydantic(UserResetPasswordPydantic):
    disabled: bool
