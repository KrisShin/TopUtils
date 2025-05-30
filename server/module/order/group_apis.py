from typing import Optional

from fastapi import APIRouter, Depends
from tortoise.expressions import Q

from module.common.accepts import CreatedResponse, SuccessResponse
from module.common.constrants import ROLE_ADMIN, ROLE_SEPARATED
from module.common.exceptions import BadRequest, NoPermission
from module.common.global_variable import DataResponse
from module.common.utils import calc_division, sum_with_None
from module.project.models import Project, TaskGroup, TaskGroupMember
from module.user.models import Group, User, UserGroup
from module.user.pydantics import (
    GroupCreatePydantic,
    GroupIDParamPydantic,
    GroupListPydantic,
    GroupUpdatePydantic,
    MemberTransferParamPydantic,
    UserInfoORMPydantic,
)
from module.user.utils import current_user, set_user_leader_mapping

router = APIRouter(prefix='/group')


@router.get('/')
async def get_group_list(query: Optional[str] = None, me: User = Depends(current_user)):
    """获取用户分组列表"""
    if not me.role_id == ROLE_ADMIN:
        raise NoPermission("你没有权限执行此操作")
    group_list = Group.all()
    if query:
        group_list = group_list.filter(
            Q(Q(name__icontains=query), Q(group_user__user__nickname__icontains=query), join_type=Q.OR)
        ).distinct()
    group_list = await group_list.order_by('name').prefetch_related("group_user__user")
    response = GroupListPydantic(data=group_list)

    return DataResponse(data=response.data)


@router.post('/')
async def post_create_group(param: GroupCreatePydantic, me: User = Depends(current_user)):
    """创建分组"""
    if not me.role_id == ROLE_ADMIN:
        raise NoPermission("你没有权限执行此操作")
    user_in_group = await User.exclude(user_group=None).filter(id__in=param.members + [param.leader])
    if user_in_group:
        raise BadRequest(f"{', '.join([u.nickname for u in user_in_group])}已经在其他分组中, 请先把用户移出分组再重新分配")

    group_obj = await Group.create(name=param.name)
    user_list = await User.filter(user_group=None, id__in=param.members + [param.leader])
    user_group = []
    for user in user_list:
        user_group.append(UserGroup(user=user, group=group_obj, is_leader=(user.id == param.leader)))
    await UserGroup.bulk_create(user_group)
    await set_user_leader_mapping()
    return CreatedResponse()


@router.put('/')
async def put_update_group(param: GroupUpdatePydantic, me: User = Depends(current_user)):
    """更新分组"""
    if not me.role_id == ROLE_ADMIN:
        raise NoPermission("你没有权限执行此操作")

    group_obj = await Group.get_or_none(id=param.id)
    all_member_id_set = set(param.members + [param.leader])
    user_in_other_group = await UserGroup.exclude(group=group_obj).filter(user_id__in=all_member_id_set).prefetch_related('user')
    if user_in_other_group:
        raise BadRequest(f"{', '.join([ug.user.nickname for ug in user_in_other_group])}已经在其他分组中, 请先把用户移出分组再重新分配")

    new_member_list = await User.filter(id__in=all_member_id_set).prefetch_related('user_group')
    origin_member_mapping = {ug.id: ug for ug in await UserGroup.filter(group=group_obj)}
    user_group = []
    for user in new_member_list:
        # if already in this group, update is_leader, else add to group
        if user.user_group:
            ug = user.user_group.related_objects[0]
            ug.is_leader = user.id == param.leader
            await ug.save()
            origin_member_mapping.pop(ug.id)
            continue
        user_group.append(UserGroup(user=user, group=group_obj, is_leader=(user.id == param.leader)))

    await UserGroup.bulk_create(user_group)
    for tg in await TaskGroup.filter(group=group_obj):
        [tg.reviewer.remove(reviewer_id) for reviewer_id in tg.reviewer if reviewer_id not in all_member_id_set]
        if not tg.reviewer:
            tg.reviewer = [param.leader]
        await tg.save()

    # if user with task, cannot remove from group
    user_id_with_task = await TaskGroupMember.filter(executor_id__in=[ug.user_id for ug in origin_member_mapping.values()]).values_list(
        'executor_id', flat=True
    )
    if origin_member_mapping:
        await UserGroup.filter(
            id__in=[ug_id for ug_id, ug_obj in origin_member_mapping.items() if ug_obj.user_id not in user_id_with_task]
        ).delete()
        if user_id_with_task:
            raise BadRequest('该成员有执行任务数据, 如果删除会导致得分权限错乱, 请联系开发妥善处理数据')
    if param.name:
        group_obj.name = param.name
        await group_obj.save()

    await set_user_leader_mapping()

    return SuccessResponse()


@router.delete('/')
async def delete_group(param: GroupIDParamPydantic, me: User = Depends(current_user)):
    """删除分组"""
    if not me.role_id == ROLE_ADMIN:
        raise NoPermission("你没有权限执行此操作")
    tgm_id_list = await TaskGroupMember.filter(task_group__group_id=param.id).values_list('id', flat=True)
    await TaskGroupMember.filter(id__in=tgm_id_list).delete()
    await TaskGroup.filter(group_id=param.id).delete()
    await UserGroup.filter(group_id=param.id).delete()
    await Group.filter(id=param.id).delete()
    await set_user_leader_mapping()
    return SuccessResponse()


@router.get('/out-users/')
async def get_group_out_users(query: Optional[str] = None, me: User = Depends(current_user)):
    """获取还未分组的用户"""
    if not me.role_id == ROLE_ADMIN:
        raise NoPermission("你没有权限执行此操作")
    user_list = User.filter(user_group=None).exclude(username='admin')
    if query:
        user_list = user_list.filter(
            Q(Q(nickname__icontains=query), Q(phone__icontains=query), Q(email__icontains=query), join_type=Q.OR)
        ).distinct()
    users = await UserInfoORMPydantic.from_queryset(user_list)
    return DataResponse(data=users)


@router.get('/user-options/')
async def get_group_user_options(
    group_id: int | str = None, project_id: int | str = None, need_group: bool = False, me: User = Depends(current_user)
):
    """
    获取可选择用户选项
    ```
    group_id: 非必传, 只获取单个组成员时传入group_id
    project_id: 非必传, 只获取单个项目成员时传入project_id
    同时传入只获取这个参与到这个项目中的这个组的成员
    不传为获取所有组的所有成员, 按组级联
    """
    is_admin = me.role_id == ROLE_ADMIN
    conditions = Q(id__in=(1, 2))
    if not is_admin:
        conditions = conditions | Q(disabled=True) | Q(role_id=ROLE_SEPARATED)
    user_queryset = User.exclude(conditions).all()
    if group_id:
        user_queryset = user_queryset.filter(user_group__group_id=group_id)
    if project_id:
        user_queryset = user_queryset.filter(project_managers__project_id=project_id)

    user_list = await user_queryset.exclude(user_group=None).prefetch_related('user_group__group').order_by('user_group__group_id')
    response_mapping = {}  # {'all': {'label': '全选', 'value': []}}  TODO: 全选暂时没处理好
    for user_obj in user_list:
        # response_mapping['all']['value'].append(f'u_{user_obj.id}')
        user_dict = {
            'label': user_obj.nickname,
            'value': f'u_{user_obj.id}',
            'key': f'u_{user_obj.id}',
            'is_leader': user_obj.user_group.related_objects[0].is_leader,
            'disabled': ((user_obj.role_id == ROLE_SEPARATED) or user_obj.disabled) if not is_admin else False,
        }
        if user_obj.user_group.related_objects:
            if group_id:
                response_mapping[f'u_{user_obj.id}'] = user_dict
            else:
                group_obj = user_obj.user_group.related_objects[0].group
                group_mapping = response_mapping.get(
                    group_obj.id,
                    {'label': group_obj.name, 'value': f'g_{group_obj.id}', 'key': f'g_{group_obj.id}', 'children': []},
                )
                group_mapping['children'].append(user_dict)
                response_mapping[group_obj.id] = group_mapping
        # else:
        #     response_mapping[f'u_{user_obj.id}'] = user_dict
    if not is_admin and need_group and group_id:
        response_mapping.update(
            {
                group_obj.id: {'label': group_obj.name, 'value': f'g_{group_obj.id}', 'key': f'g_{group_obj.id}'}
                for group_obj in await Group.exclude(id=group_id)
            }
        )

    return DataResponse(data=list(response_mapping.values()))


@router.put('/transfer/')
async def put_transfer_group_member(params: MemberTransferParamPydantic, me: User = Depends(current_user)):
    """转移小组成员到新的小组:
    1. 相关成员复制到新分组
    2. 检查目标小组是否已参与任务原小组的任务
        - 未参加: 新键任务执行小组, 人天等于人员的人天(人天比例100)
        - 已参加: 该成员的人天增加到新小组的人天(重新计算人天比例)
    3. 原执行组是否还有人存在(是否需要解散小组)
        - 有组长: 无需操作
        - 无组长: 删除小组以及所有关联的任务的执行组--待讨论
    4. 删除原本小组的成员
    """
    if me.role_id != ROLE_ADMIN:
        return NoPermission('你没有权限执行此操作')

    ug_list = [UserGroup(user_id=uid, group_id=params.target_id) for uid in params.id_list]
    await UserGroup.bulk_create(ug_list)
    target_leader = await UserGroup.get(group_id=params.target_id, is_leader=True)
    tg_list = await TaskGroup.filter(members__executor_id__in=params.id_list).order_by('id').distinct().prefetch_related('task', 'members')
    tgm_mapping = {tg.id: [tgm for tgm in tg.members if tgm.executor_id in params.id_list] for tg in tg_list}
    target_tg_mapping = {tg.task_id: tg for tg in await TaskGroup.filter(group_id=params.target_id).prefetch_related('members')}
    project_mapping = {
        proj.id: {pm.manager_id for pm in proj.project_managers}
        for proj in await Project.filter(task_executors__executor_id__in=params.id_list).prefetch_related('project_managers')
    }
    for tg in tg_list:
        target_tg = target_tg_mapping.get(tg.task_id)
        tgm_list = tgm_mapping[tg.id]
        if not target_tg:
            project_mapping[tg.project_id].add(target_leader.user_id)
            target_tg = await TaskGroup.create(
                task_id=tg.task_id, group_id=params.target_id, project_id=tg.project_id, reviewer=list(project_mapping[tg.project_id])
            )
            target_tg_mapping[tg.task_id] = target_tg
            await target_tg.fetch_related('members')
        for tgm in tgm_list:
            tg.target_workday = (tg.target_workday or 0) - (tgm.target_workday or 0)
            tg.actual_workday = (tg.actual_workday or 0) - (tgm.actual_workday or 0)
            target_tg.target_workday = sum_with_None((target_tg.target_workday, tgm.target_workday))
            target_tg.actual_workday = sum_with_None((target_tg.actual_workday, tgm.actual_workday))
            tgm.task_group = target_tg
            await tgm.save()
        # task group 和 task group member的所有人天比例都需要重新计算, 当有多人移动时比例会出问题
        tg.target_workday_rate = calc_division(tg.target_workday, tg.task.target_workday)
        tg.actual_workday_rate = calc_division(tg.actual_workday, tg.task.actual_workday)
        await tg.save()
        target_tg.target_workday_rate = calc_division(target_tg.target_workday, tg.task.target_workday)
        target_tg.actual_workday_rate = calc_division(target_tg.actual_workday, tg.task.actual_workday)
        await target_tg.save()

        tg = await TaskGroup.get(id=tg.id).prefetch_related('members')
        target_tg = await TaskGroup.get(id=target_tg.id).prefetch_related('members')
        if not tg.members.related_objects:
            await tg.delete()
        else:
            for tgm in tg.members:
                tgm.target_workday_rate = calc_division(tgm.target_workday, tg.target_workday)
                tgm.actual_workday_rate = calc_division(tgm.actual_workday, tg.actual_workday)
        for tgm in target_tg.members:
            tgm.target_workday_rate = calc_division(tgm.target_workday, target_tg.target_workday)
            tgm.actual_workday_rate = calc_division(tgm.actual_workday, target_tg.actual_workday)

    # TODO: 讨论确定没有人的小组是否需要保留
    # await Group.filter(group_user__isnull=True).delete()

    await UserGroup.filter(user_id__in=params.id_list, group_id__not=params.target_id).delete()

    return SuccessResponse()
