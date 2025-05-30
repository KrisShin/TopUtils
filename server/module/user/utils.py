from datetime import UTC, datetime, timedelta
from typing import Optional

from fastapi import Depends, Request
from jose import JWTError, jwt
from passlib.context import CryptContext

from config.settings import ACCESS_TOKEN_EXPIRE_DAYS, ALGORITHM, DEBUG, SECRET_KEY
from module.common.exceptions import AuthorizationFailed
from module.common.global_variable import oauth2_scheme
from module.common.redis_client import cache_client
from module.common.utils import get_now_UTC_time
from module.user.models import User

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
        check_token = False  # remove new login check: False if DEBUG else saved_token != token
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
    if not user or user.disabled:
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
