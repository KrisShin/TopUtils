from calendar import monthrange
import json
from collections import defaultdict
from datetime import UTC, date, datetime, timedelta
from typing import Optional, List

from chinese_calendar import get_workdays
from fastapi import Depends, Request
from jose import JWTError, jwt
from passlib.context import CryptContext

from config.settings import ACCESS_TOKEN_EXPIRE_DAYS, ALGORITHM, DEBUG, SECRET_KEY
from module.common.constrants import ROLE_SEPARATED
from module.common.exceptions import AuthorizationFailed
from module.common.global_variable import oauth2_scheme
from module.common.models import SystemParameter
from module.common.redis_client import cache_client
from module.common.utils import get_now_UTC_time
from module.user.models import Group, User, UserGroup

pwd_context = CryptContext(schemes=["argon2"], deprecated="auto")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Check plain password whether right or not"""
    try:
        return pwd_context.verify(plain_password, hashed_password)
    except:
        return False


def get_password_hash(password: str) -> str:
    """Generate password hashed value."""
    return pwd_context.hash(password)


def create_access_token(user_base_info: dict, expires_delta: Optional[timedelta] = None) -> str:
    """create user access token"""
    if expires_delta:
        expire = get_now_UTC_time() + expires_delta
    else:
        expire = get_now_UTC_time() + timedelta(days=ACCESS_TOKEN_EXPIRE_DAYS)
    user_base_info.update({"exp": expire})
    encoded_jwt = jwt.encode(user_base_info, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


# async def check_api_rights(right: RightConfig, api: str):
#     """check user whether have right to call this api or not."""
#     if right and right.apis:
#         if right.whitelist:
#             if ('*' in right.apis or api in right.apis) :
#                 return True
#         else:
#             if not ('*' in right.apis or api in right.apis) :
#                 return True
#     return False


async def validate_token(token: str = Depends(oauth2_scheme)) -> str | bool:
    """if validate return user_id otherwise return False"""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id: str = payload.get("user_id")
        expire_time: float = payload.get('exp')
        saved_token = await cache_client.get_cache(user_id)
        check_token = False # remove new login check: False if DEBUG else saved_token != token
        if (user_id is None) or (datetime.fromtimestamp(expire_time, tz=UTC) < get_now_UTC_time()) or (check_token):
            return False
    except JWTError:
        return False
    return payload


async def current_user(request: Request, user_base_info: bool | dict = Depends(validate_token)) -> User:
    """return user orm"""
    if user_base_info is False:
        raise AuthorizationFailed()
    user_id = user_base_info['user_id']
    await cache_client.expire_cache(user_id, ex=timedelta(days=ACCESS_TOKEN_EXPIRE_DAYS))

    user = await User.get_or_none(id=user_id, disabled=False).prefetch_related('role', 'user_group')
    group = await Group.get_or_none(group_user__user=user)
    user.group_id = group and group.id
    user.group = group
    if not user or user.role_id == ROLE_SEPARATED or user.disabled:
        raise AuthorizationFailed()

    # right = await RightConfig.get_or_none(right_level=user.role)
    # is_allow = await check_api_rights(right, request.url.path)
    # if not is_allow:
    #     raise NoPermission('You are forbbiden.')

    if DEBUG:
        user.last_login_ip = request.client.host
    else:
        user.last_login_ip = request.headers.get("X-Forwarded-For")
    await user.save()
    return user


async def set_user_leader_mapping():
    """更新用户分组与用户及主管关系映射"""
    group_user_leader_mapping = defaultdict(dict)
    user_group_list = await UserGroup.all()
    for ug in user_group_list:
        mapping = group_user_leader_mapping[ug.group_id]
        members = mapping.get('members', [])
        members.append(ug.user_id)
        mapping.update({'members': members})
        ug.is_leader and mapping.update({'leader': ug.user_id})
        group_user_leader_mapping[ug.group_id] = mapping
    user_leader_mapping = {}
    for content in group_user_leader_mapping.values():
        for user_id in content['members']:
            user_leader_mapping[user_id] = content['leader']

    await SystemParameter.update_or_create(
        name='group_user_leader_mapping',
        description='分组与用户及主管映射关系',
        data_type='json',
        defaults={'data': json.dumps(group_user_leader_mapping)},
    )
    await SystemParameter.update_or_create(
        name='user_leader_mapping',
        description='用户与主管映射关系',
        data_type='json',
        defaults={'data': json.dumps(user_leader_mapping)},
    )


async def set_user_id_nickname_mapping():
    """更新用户的id和昵称的映射"""
    data = {u.id: u.nickname for u in await User.all()}
    await SystemParameter.update_or_create(
        name='user_id_nickname_mapping',
        description='用户id与昵称映射关系',
        data_type='json',
        defaults={'data': json.dumps(data)},
    )


def get_user_group_option_id_param(id_list: List[str|int]) -> bool | list:
    """get user or group id of id_list"""
    id_list = set(id_list)
    None in id_list and id_list.remove(None)
    if not id_list:
        return False
    resp = []
    for id_str in id_list:
        if isinstance(id_str, str):
            id_int = int(id_str.split('_')[-1])
        elif isinstance(id_str, int):
            id_int = id_str
        resp.append(id_int)
    return resp


def calc_user_standard_workday_in_period(start_date: date, end_date: date, user: User):
    """get user standard workday in month nodes,
    if node of month user not join yet or user already leave, standard workday should be 0,
    join month: workday after join of month/month workday(get by system parameter) * user standard workday
    leave month: workday before join of month/month workday(get by system parameter) * user standard workday
    """
    start_date = max(start_date, user.join_date)
    if user.leave_date:
        end_date = min(end_date, user.leave_date)

    if end_date < start_date:
        return 0

    workday = 0
    for year in range(start_date.year, end_date.year + 1):
        start_month, end_month = 1, 12
        if year == start_date.year:
            start_month = start_date.month
        if year == end_date.year:
            end_month = end_date.month
        workday = user.standard_workday * (end_month - start_month + 1)
    if start_date.day != 1:
        # last day of the month
        end_day = monthrange(start_date.year, start_date.month)[-1]
        # all workdays of the month
        month_workday = len(get_workdays(start_date.replace(day=1), start_date.replace(day=end_day), True))
        # not join yet workdays of the month
        unjoin_workday = len(get_workdays(start_date.replace(day=1), start_date - timedelta(days=1), True))
        workday -= unjoin_workday / month_workday * user.standard_workday

    last_day = monthrange(end_date.year, end_date.month)[-1]
    if end_date.day != last_day:
        month_workday = len(get_workdays(end_date.replace(day=1), end_date.replace(day=last_day), True))
        leaved_workday = len(get_workdays(end_date + timedelta(days=1), end_date.replace(day=last_day), True))
        workday -= leaved_workday / month_workday * user.standard_workday
    return workday
