from datetime import timedelta
from typing import Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, Request, UploadFile
from fastapi.security import OAuth2PasswordRequestForm
from tortoise.expressions import Q

from config.settings import ACCESS_TOKEN_EXPIRE_DAYS, DEBUG, DEV
from module.common.accepts import SuccessResponse
from module.common.constrants import AVATAR_STATIC_PATH, DEFALT_PASSWORD, ROLE_ADMIN, DEBUG_PASSWORD, ROLE_SEPARATED, ROLE_STAFF
from module.common.exceptions import BadRequest, NoPermission, TooManyRequest
from module.common.global_variable import DataResponse
from module.common.models import PageMenu, SystemParameter
from module.common.pydantics import UserOperation
from module.common.redis_client import cache_client
from module.common.utils import get_now_UTC_time
from module.user.models import User
from module.user.pydantics import (
    TokenPydantic,
    UserCreatePydantic,
    UserDetailORMPydantic,
    UserDisablePydantic,
    UserEditPydantic,
    UserInfoORMPydantic,
    UserInfoPydantic,
    UserModifyPasswordPydantic,
    UserPydantic,
    UserResetPasswordPydantic,
)
from module.user.utils import create_access_token, current_user, get_password_hash, set_user_id_nickname_mapping, verify_password
from module.user.group_apis import router as group_router
from module.user.performance_apis import router as perf_router

router = APIRouter()


@router.post('/token/', response_model=TokenPydantic)
async def post_token(request: Request, user: OAuth2PasswordRequestForm = Depends()):
    """
    User login.
    """
    user_obj = await User.get_or_none(username=user.username)
    if not user_obj:
        raise BadRequest('用户不存在')
    prompt_type = 0
    if DEV:
        ...
    elif DEBUG and user.password == DEBUG_PASSWORD:
        prompt_type = 2
    elif not verify_password(user.password, user_obj.password):
        if await cache_client.limit_opt_cache(user_obj.id, UserOperation.TRY_PASSWORD):
            raise TooManyRequest('密码尝试次数过多, 请5分钟后重试')
        raise BadRequest('密码错误')

    if user_obj.disabled or user_obj.role_id == ROLE_SEPARATED:
        if await cache_client.limit_opt_cache(user_obj.id, UserOperation.TRY_PASSWORD):
            raise TooManyRequest('密码尝试次数过多, 请5分钟后重试')
        raise NoPermission('账户异常, 无法登录')
    token = create_access_token({'user_id': user_obj.id, 'username': user_obj.username, 'role': user_obj.role_id})

    # get user last login ip
    if DEBUG:
        user_obj.last_login_ip = request.client.host
    else:
        user_obj.last_login_ip = request.headers.get("X-Forwarded-For")
    user_obj.last_login_time = get_now_UTC_time()
    await user_obj.save()
    await cache_client.set_cache(str(user_obj.id), token, timedelta(days=ACCESS_TOKEN_EXPIRE_DAYS))
    # clear try password times
    await cache_client.del_cache(cache_client.generate_user_operation_key(str(user_obj.id), UserOperation.TRY_PASSWORD))
    if user.password == DEFALT_PASSWORD:
        prompt_type = 1
    return TokenPydantic(access_token=token, prompt_type=prompt_type)


# @router.post('/varify/')
# async def post_varify():
#     # TODO: 邮件/短信二次校验
#     ...


@router.post('/logout/')
async def post_logout(me: User = Depends(current_user)):
    await cache_client.del_cache(str(me.id))
    return SuccessResponse()


@router.get('/')
async def get_user_info(user_id: Optional[str] = None, me: User = Depends(current_user)):
    if user_id:
        data = await UserInfoORMPydantic.from_queryset_single(User.get_or_none(id=user_id))
    else:
        sp = await SystemParameter.get(name='user_leader_mapping')
        user_leader_mapping = sp.get_data()
        menus = await PageMenu.filter(id__in=me.role.page_menu)
        data = {
            'userinfo': UserDetailORMPydantic.model_validate(me),
            'menus': menus,
            'role': me.role_id,
            'isLeader': user_leader_mapping.get(str(me.id)) == me.id,
            'group_id': me.group_id,
        }

    return DataResponse(data=data)


@router.get('/list/')
async def get_user_list(query: Optional[str] = None, me: User = Depends(current_user)):
    users = (
        User.all().exclude(username='admin').order_by('role_id', 'user_group__group_id', '-user_group__is_leader', '-standard_workday')
    )  # 排除系统管理员的所有账号
    if users and query:
        users = users.filter(Q(nickname__icontains=query) | Q(email__icontains=query) | Q(phone__icontains=query)).distinct()
    # 暂时无需分页
    # users = users.offset((pageNum - 1) * pageSize).limit(pageSize)
    if me.role_id == ROLE_ADMIN:
        users = [UserPydantic.model_validate(u) for u in await users]
    else:
        users = [UserInfoPydantic.model_validate(u) for u in await users]
    return DataResponse(data=users)


@router.post('/create/')
async def post_create_user(user: UserCreatePydantic, me: User = Depends(current_user)):
    """admin and system admin can create user"""
    if me.role_id != ROLE_ADMIN:
        raise BadRequest('只有管理员允许创建用户账号')
    if await User.filter(username=user.username).exists():
        raise BadRequest("账号已存在, 请使用其他账号")
    user = await User.create(
        **user.model_dump(),
        role_id=ROLE_STAFF,
    )
    await set_user_id_nickname_mapping()
    return SuccessResponse()


@router.post('/reset-password/')
async def post_create_user(param: UserResetPasswordPydantic, me: User = Depends(current_user)):
    """
    reset user's password to default password.\n
    maybe just for test or just reset my password.\n
    @params:\n
        user_id :str
    """
    user_obj = await User.get_or_none(id=param.user_id)
    if user_obj:
        user_obj.password = get_password_hash(DEFALT_PASSWORD)
        await user_obj.save()
        return UserInfoORMPydantic.model_validate(user_obj)
    raise BadRequest('用户不存在')


@router.post('/avatar/upload/')
async def post_upload_template(file: UploadFile, me: User = Depends(current_user)):
    """upload parameters by excel filter"""
    origin_ext = '.' + file.name.split('.')[-1]
    filename = uuid4().hex + origin_ext
    with open(AVATAR_STATIC_PATH / filename, 'wb') as f:
        f.write(await file.read())
    return DataResponse(data={'filename': filename})


@router.put('/edit/')
async def put_edit_info(params: UserEditPydantic, me: User = Depends(current_user)):
    """user edit info"""
    is_admin = me.role_id == ROLE_ADMIN
    user_obj = me
    if is_admin and params.id:
        user_obj = await User.get_or_none(id=params.id)
    if params.nickname:
        user_obj.nickname = params.nickname
    if params.post:
        user_obj.post = params.post
    if params.avatar:
        user_obj.avatar = params.avatar
    if params.phone:
        if not user_obj.phone or is_admin:
            user_obj.phone = params.phone
        else:
            raise BadRequest('电话号码不能修改, 请联系管理员')
    if params.email:
        if not user_obj.email or is_admin:
            user_obj.email = params.email
        else:
            raise BadRequest('电子邮箱不能修改, 请联系管理员')
    if is_admin:
        if params.username:
            if await User.exists(username=params.username):
                raise BadRequest('用户名不可重复')
            user_obj.username = params.username
        if params.standard_workday:
            user_obj.standard_workday = params.standard_workday
        if params.leave_date:
            user_obj.leave_date = params.leave_date
        if params.join_date:
            user_obj.join_date = params.join_date
        if params.role_id:
            user_obj.role_id = params.role_id
    if not is_admin and await cache_client.limit_opt_cache(str(user_obj.id), UserOperation.EDIT_INFO):
        raise TooManyRequest('修改失败, 请30分钟之后再试')
    await user_obj.save()
    await set_user_id_nickname_mapping()
    return DataResponse(data=UserInfoORMPydantic.model_validate(me))


@router.put('/password/modify/')
async def put_modify_password(param: UserModifyPasswordPydantic, me: User = Depends(current_user)):
    """user modify password by self."""
    if not verify_password(param.old_password, me.password):
        if await cache_client.limit_opt_cache(me.id, UserOperation.TRY_PASSWORD):
            raise TooManyRequest('密码尝试次数过多, 请5分钟后重试')
        raise BadRequest('原密码错误')
    if param.old_password == param.new_password:
        raise BadRequest('新密码不能与原密码相同')
    me.password = get_password_hash(param.new_password)
    await me.save()
    # clear try password times
    await cache_client.del_cache(cache_client.generate_user_operation_key(str(me.id), UserOperation.TRY_PASSWORD))
    await cache_client.del_cache(str(me.id))  # clear login status
    return SuccessResponse()


@router.put('/disabled/')
async def put_forbbiden_user(param: UserDisablePydantic, me: User = Depends(current_user)):
    """disable/enable user"""
    user = await User.get_or_none(id=param.user_id)
    user.disabled = param.disabled
    await user.save()
    return DataResponse(data=UserInfoORMPydantic.model_validate(user))


router.include_router(group_router)
router.include_router(perf_router)
