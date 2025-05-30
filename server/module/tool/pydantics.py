from datetime import date, datetime
from typing import List, Optional

from pydantic import BaseModel, field_serializer, field_validator, model_validator
from tortoise.contrib.pydantic import pydantic_model_creator

from module.common.constrants import DEFALT_PASSWORD
from module.common.utils import get_thursday
from module.user.models import User
from module.user.utils import get_password_hash, get_user_group_option_id_param

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


class GroupPydantic(BaseModel):
    id: int
    name: str
    leader: Optional[UserInfoPydantic] = None
    members: Optional[List[UserInfoPydantic]] = []
    group_user: Optional[list] = None

    class Config:
        from_attributes = True

    @model_validator(mode='after')
    def validate(cls, instance):
        for rs_user in instance.group_user:
            user_info = UserInfoPydantic.model_validate(rs_user.user)
            if rs_user.is_leader:
                instance.__dict__['leader'] = user_info
            else:
                instance.__dict__['members'].append(user_info)
        instance.__dict__.pop('group_user')
        return instance


class GroupListPydantic(BaseModel):
    data: List[GroupPydantic]


class GroupCreatePydantic(BaseModel):
    name: str
    leader: Optional[int] = None
    members: Optional[List[int]] = []


class GroupIDParamPydantic(BaseModel):
    id: int


class GroupUpdatePydantic(GroupIDParamPydantic):
    name: Optional[str] = None
    leader: Optional[int] = None
    members: Optional[List[int]] = []


class MemberTransferParamPydantic(BaseModel):
    id_list: List[int]
    target_id: int


class WeekPerfParamPydantic(BaseModel):
    date_range: Optional[List[date]] = []
    user_ids: Optional[List[str]] = []

    @field_validator('date_range')
    def validate_date_range(cls, date_range: list) -> list:
        start, end = None, None
        if not date_range:
            start = get_thursday()
            end = start
        else:
            start = get_thursday(date_range[0])
            end = get_thursday(date_range[1])
        date_range = [start, end]
        return date_range

    @field_validator('user_ids')
    def validate_user_ids(cls, user_ids: list) -> set:
        data = get_user_group_option_id_param(user_ids)
        if data is False:
            return []
        return data


class CreateWeekPerfParamPydantic(BaseModel):
    thursday: Optional[date] = None

    @field_validator('thursday')
    def validate_thursday(cls, thursday: date) -> date:
        return get_thursday(thursday)


class EditWeekPerfParamPydantic(BaseModel):
    user_id: int
    thursday: date
    score: Optional[float] = None
    extra_workday: Optional[float] = None
    description: Optional[str] = None
