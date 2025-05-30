from collections import defaultdict
from datetime import datetime
import json
import random
import re
import string

from fastapi import APIRouter, Response
from tortoise.expressions import Q

from module.common.accepts import SuccessResponse
from module.common.constrants import DEFALT_PASSWORD
from module.common.models import PageMenu, StatusEnum, SystemParameter
from module.common.utils import calc_division, none_or_false_in_args, get_last_second_of_month, sum_with_None
from module.project.models import (
    Project,
    ProjectManager,
    ProjectManager,
    ProjectPeriodEvaluation,
    Task,
    TaskCategoryEnum,
    TaskGroup,
    TaskGroupMember,
    TaskLevelEnum,
)
from module.project.utils import recurse_task_id, update_project_members_mapping, update_project_progress, update_task3_status
from module.user.models import Role, User, UserGroup, UserWeekPerformance
from module.user.utils import get_password_hash
from module.vetting.models import Vetting, VettingModelEnum

router = APIRouter()


# @router.get("/init")
# async def debug_init():
#     """
#     Add default rights.
#     """
#     menus_data = [
#         {
#             "id": 1,
#             "title": "看板",
#             "icon": "icon-dashboard",
#             "url": "/dashboard",
#             "parent": None,
#             "desc": "看板",
#             "sorts": 0,
#         },
#         {
#             'id': 2,
#             'title': "审批通知",
#             'icon': "icon-eye",
#             'url': "/vetting",
#             'parent': None,
#             'desc': "审批通知",
#             'sorts': 1,
#         },
#         {
#             'id': 3,
#             'title': "项目管理",
#             'icon': "icon-project",
#             'url': "/project",
#             'parent': None,
#             'desc': "项目管理",
#             'sorts': 2,
#         },
#         {
#             'id': 31,
#             'title': "项目列表",
#             'icon': "icon-detail",
#             'url': "/project/list",
#             'parent': 3,
#             'desc': "项目管理/项目列表",
#             'sorts': 0,
#         },
#         {
#             'id': 32,
#             'title': "新建项目",
#             'icon': "icon-save",
#             'url': "/project/create",
#             'parent': 3,
#             'desc': "项目管理/新建项目",
#             'sorts': 1,
#         },
#         {
#             'id': 9,
#             'title': "系统管理",
#             'icon': "icon-setting",
#             'url': "/system",
#             'parent': None,
#             'desc': "任务管理目录分支",
#             'sorts': 4,
#         },
#         {
#             'id': 91,
#             'title': "用户管理",
#             'icon': "icon-team",
#             'url': "/system/useradmin",
#             'parent': 9,
#             'desc': "系统管理/用户管理",
#             'sorts': 0,
#         },
#         {
#             'id': 92,
#             'title': "角色管理",
#             'icon': "icon-user",
#             'url': "/system/roleadmin",
#             'parent': 9,
#             'desc': "系统管理/角色管理",
#             'sorts': 1,
#         },
#         {
#             'id': 93,
#             'title': "权限管理",
#             'icon': "icon-safetycertificate",
#             'url': "/system/poweradmin",
#             'parent': 9,
#             'desc': "系统管理/权限管理",
#             'sorts': 2,
#         },
#         {
#             'id': 94,
#             'title': "菜单管理",
#             'icon': "icon-appstore",
#             'url': "/system/menuadmin",
#             'parent': 9,
#             'desc': "系统管理/菜单管理",
#             'sorts': 3,
#         },
#     ]

#     menus = []

#     for m in menus_data:
#         menus.append(PageMenu(**m))
#     await PageMenu.bulk_create(menus)

#     all_menu_id = await PageMenu.all().values_list('id', flat=True)

#     roles = []
#     for r in ['user', 'admin']:
#         roles.append(Role(name=r, description=f'system default {r} role.', is_system_role=True, page_menu=all_menu_id))
#     await Role.bulk_create(roles)

#     # TODO: add base permission
#     # for p in []:

#     # add users
#     users = [
#         User(
#             username='admin',
#             nickname='管理员',
#             password=get_password_hash(DEFALT_PASSWORD),
#             phone='131234' + ''.join(random.choices(string.digits, k=5)),
#             email='admin@test.com',
#             role_id=2,
#         )
#     ]
#     # add users
#     for nickname, username in {
#         '李立理': 'lilili',
#         '李树军': 'lishujun',
#         '郭文琳': 'guowenlin',
#         '向亚轩': 'xiangyaxuan',
#         '刘雨薇': 'liuyuwei',
#         '尹卿宇': 'yinqingyu',
#         '陈锐锐': 'chenruirui',
#         '冯佳辉': 'fengjiahui',
#         '陈星筑': 'chenxingzhu',
#         '钟丹婷': 'zhongdanting',
#         '吕宏宇': 'lvhongyu',
#         '蔡静茹': 'caijingru',
#         '特格西': 'tegexi',
#         '邓思维': 'dengsiwei',
#         '孙思': 'sunsi',
#     }.items():
#         s = ''.join(random.choices(string.digits, k=9))
#         users.append(
#             User(
#                 nickname=nickname,
#                 username=username,
#                 password=get_password_hash(DEFALT_PASSWORD),
#                 phone='13' + s,
#                 email=username + '@test.com',
#                 role_id=1,
#             )
#         )
#     await User.bulk_create(users)

#     return Response()


@router.get('/gen_project_member_mapping')
async def debug_gen_project_member_mapping():
    await update_project_members_mapping()
    return SuccessResponse()


# @router.get('/update_task_member_workday_rate/')
# async def debug_update_task_member_workday_rate():
#     all_task = await Task.all().order_by('-level')
#     for task in all_task:
#         task = await Task.get(id=task.id).prefetch_related("members")
#         if task.level == TaskLevelEnum.LEVEL_3:
#             for tm in await task.members.all():
#                 if tm.target_workday and task.target_workday:
#                     tm.target_workday_rate = tm.target_workday / task.target_workday
#                 if tm.actual_workday and task.actual_workday:
#                     tm.actual_workday_rate = tm.actual_workday / task.actual_workday
#                 await tm.save()
#         await task.save()
#     return SuccessResponse()


@router.get('/update_task_period/')
async def debug_update_task_period():
    tt = await Task.all()
    for t in tt:
        t.period = get_last_second_of_month(date_obj=t.period).date()
        await t.save()
    return SuccessResponse()


# @router.get('/update_project_progress/')
# async def debug_update_project_progress():
#     pp = await Project.all()
#     for p in pp:
#         await update_project_progress(p.id)
#     return SuccessResponse()


# @router.get('/update_period_evaluation/')
# async def debug_update_period_evaluation():
#     tt3 = Task.filter(level=TaskLevelEnum.LEVEL_3, period_evaluation__isnull=True).prefetch_related("parent")
#     print(await tt3.count())
#     await tt3.update(period_evaluation=75)
#     parent_ids = await tt3.values_list('parent_id', flat=True)
#     tt2 = await Task.filter(id__in=parent_ids)
#     for t in tt2:
#         t.period_evaluation = 75
#         await t.save()
#     return SuccessResponse()


@router.get('/remove_task_archived/')
async def debug_remove_task_archived():
    await Task.all().update(archived=None)
    return SuccessResponse()


# @router.get('/update_level3_task_workday/')
# async def debug_update_level3_task_workday():
#     task_list = await Task.filter(level=TaskLevelEnum.LEVEL_3).prefetch_related('parent')
#     for task in task_list:
#         task.period_evaluation = task.parent.period_evaluation and task.period_evaluation
#         ev = await ProjectPeriodEvaluation.get_or_none(period=task.period, project_id=task.project_id)
#         task.week_avg_evaluation = ev.score if ev else task.week_avg_evaluation
#         if not none_or_false_in_args(task.target_workday, task.progress, task.period_evaluation, task.week_avg_evaluation):
#             task.progress_workday = task.target_workday * task.progress / 100
#             task.actual_workday = task.progress_workday * (task.period_evaluation + task.week_avg_evaluation) / 200
#         await task.save()

#     return SuccessResponse()


# @router.get('/update_level3_task_status/')
# async def debug_update_level3_task_status():
#     await update_task3_status()
#     return SuccessResponse()


# @router.get('/reverse_log/')
# async def debug_reverse_log():
#     for tm in await TaskMember.filter(log__isnull=False):
#         tm.log.reverse()
#         await tm.save()

#     for ev in await ProjectPeriodEvaluation.filter(log__isnull=False):
#         ev.log.reverse()
#         await ev.save()
#     return SuccessResponse()


# @router.get('/migrate_project_member/')
# async def debug_migrate_project_member():
#     for p in await Project.all().prefetch_related("members__member"):
#         for pm in p.members:
#             if pm.is_leader:
#                 await ProjectManager.create(project=p, leader=pm.member)
#     return SuccessResponse()


# @router.get('/migrate_task_member/')
# async def debug_migrate_task_member():
#     group_member_mapping = defaultdict(list)
#     user_group_mapping = {}
#     group_mapping = {}
#     user_mapping = {}
#     for ug in await UserGroup.all().prefetch_related('group', 'user'):
#         group_member_mapping[ug.group_id].append(ug.user_id)
#         user_group_mapping[ug.user_id] = ug.group_id
#         group_mapping[ug.group_id] = ug.group
#         user_mapping[ug.user_id] = ug.user
#     sp = await SystemParameter.get(name='user_leader_mapping')
#     user_leader_mapping = sp.get_data()

#     for t in await Task.all().prefetch_related('members__relation__member', 'project'):
#         for tm in t.members:
#             user_id = tm.relation.member_id
#             tg, _ = await TaskGroup.get_or_create(task=t, group_id=user_group_mapping[user_id], defaults={'log': [], 'reviewer': [user_leader_mapping[str(user_id)]]})
#             tg.target_workday = (tg.target_workday or 0) + (tm.target_workday or 0)
#             tg.target_workday_rate = tg.target_workday / (t.target_workday or 1)
#             tg.actual_workday = (tg.actual_workday or 0) + (tm.actual_workday or 0)
#             tg.actual_workday_rate = tg.actual_workday / (t.actual_workday or 1)
#             await tg.save()
#             t_rate = None
#             if tm.target_workday is not None:
#                 if tm.target_workday == 0:
#                     t_rate = 0
#                 else:
#                     t_rate = tm.target_workday / tg.target_workday
#             a_rate = None
#             if tm.actual_workday is not None:
#                 if tm.actual_workday == 0:
#                     a_rate = 0
#                 else:
#                     a_rate = tm.actual_workday / tg.actual_workday

#             await TaskGroupMember.create(
#                 task_group=tg,
#                 project=t.project,
#                 executor=user_mapping[user_id],
#                 target_workday=tm.target_workday,
#                 target_workday_rate=t_rate,
#                 actual_workday=tm.actual_workday,
#                 actual_workday_rate=a_rate,
#                 confirmed=tm.confirmed,
#                 reason=tm.reason,
#                 log=tm.log,
#             )
#     return SuccessResponse()


# @router.get('/migrate_vetting/')
# async def debug_migrate_vetting():
#     await Vetting.filter(model=VettingModelEnum.TM).update(model=VettingModelEnum.TASK_GROUP)
#     await Vetting.filter(model=VettingModelEnum.PM).update(model=VettingModelEnum.PROJECT_LEADER)
#     return SuccessResponse()


# @router.get('/migrate_all/')
# async def debug_migrate_all():
#     await debug_migrate_project_member()
#     await debug_migrate_task_member()
#     await debug_migrate_vetting()
#     return SuccessResponse()


# @router.get('/update_task_group_project/')
# async def debug_update_task_group_project():
#     tg_list = []
#     for tg in await TaskGroup.all().prefetch_related('task'):
#         tg.project_id = tg.task.project_id
#         tg_list.append(tg)
#     await TaskGroup.bulk_update(tg_list, fields=('project_id',))
#     return SuccessResponse()


# @router.get('/update_task_group_workday/')
# async def debug_update_task_group_workday():
#     for tg in await TaskGroup.filter(Q(target_workday=None) | Q(actual_workday=None)).prefetch_related('task', 'members'):
#         tw_list = []
#         aw_list = []
#         for m in tg.members:
#             tw_list.append(m.target_workday)
#             aw_list.append(m.actual_workday)
#         tg.target_workday = sum_with_None(tw_list)
#         tg.target_workday_rate = calc_division(tg.target_workday, tg.task.target_workday)
#         tg.actual_workday = sum_with_None(aw_list)
#         tg.actual_workday_rate = calc_division(tg.actual_workday, tg.task.actual_workday)
#         await tg.save()
#     return SuccessResponse()


# @router.get('/recalc_workday/')
# async def debug_recalc_workday():
#     for t in await Task.filter(level=TaskLevelEnum.LEVEL_3).prefetch_related('task_groups__members'):
#         tg_target_workday_mapping = {tg.id: {'t': tg.target_workday, 'tr': tg.target_workday_rate} for tg in t.task_groups}
#         tg_actual_workday_mapping = {tg.id: {'a': tg.actual_workday, 'ar': tg.actual_workday_rate} for tg in t.task_groups}
#         sum_tg_target_workday = sum_with_None([tg['t'] for tg in tg_target_workday_mapping.values()])
#         sum_tg_actual_workday = sum_with_None([tg['a'] for tg in tg_actual_workday_mapping.values()])
#         if sum_tg_target_workday and t.target_workday and sum_tg_target_workday > t.target_workday:
#             for tg in t.task_groups:
#                 if tg.target_workday:
#                     tg.target_workday = calc_division(tg.target_workday * t.target_workday, sum_tg_target_workday)
#                     tg.target_workday_rate = calc_division(tg.target_workday, t.target_workday)
#                     await tg.save()
#                     tgm_target_workday_mapping = {tgm.id: {'t': tgm.target_workday, 'tr': tgm.target_workday_rate} for tgm in tg.members}
#                     sum_tgm_target_workday = sum_with_None([tgm['t'] for tgm in tgm_target_workday_mapping.values()])
#                     if sum_tgm_target_workday and tg.target_workday and sum_tgm_target_workday > tg.target_workday:
#                         for tgm in tg.members:
#                             if tgm.target_workday:
#                                 tgm.target_workday = calc_division(tgm.target_workday * tg.target_workday, sum_tgm_target_workday)
#                                 tgm.target_workday_rate = calc_division(tgm.target_workday, tg.target_workday)
#                                 await tgm.save()
#         if sum_tg_actual_workday and t.actual_workday and sum_tg_actual_workday > t.actual_workday:
#             for tg in t.task_groups:
#                 if tg.actual_workday:
#                     tg.actual_workday = calc_division(tg.actual_workday * t.actual_workday, sum_tg_actual_workday)
#                     tg.actual_workday_rate = calc_division(tg.actual_workday, t.actual_workday)
#                     await tg.save()
#                     tgm_actual_workday_mapping = {tgm.id: {'a': tgm.actual_workday, 'ar': tgm.actual_workday_rate} for tgm in tg.members}
#                     sum_tgm_actual_workday = sum_with_None([tgm['a'] for tgm in tgm_actual_workday_mapping.values()])
#                     if sum_tgm_actual_workday and tg.actual_workday and sum_tgm_actual_workday > tg.actual_workday:
#                         for tgm in tg.members:
#                             if tgm.actual_workday:
#                                 tgm.actual_workday = calc_division(tgm.actual_workday * tg.actual_workday, sum_tgm_actual_workday)
#                                 tgm.actual_workday_rate = calc_division(tgm.actual_workday, tg.actual_workday)
#                                 await tgm.save()
#     return SuccessResponse()


# @router.get('/recalc_workday/done/')
# async def debug_recalc_workday_done():
#     for t in await Task.filter(level=TaskLevelEnum.LEVEL_3, status__in=(StatusEnum.DONE, StatusEnum.CONFIRMING)).prefetch_related('task_groups__members'):
#         tg_target_workday_mapping = {tg.id: {'t': tg.target_workday, 'tr': tg.target_workday_rate} for tg in t.task_groups}
#         tg_actual_workday_mapping = {tg.id: {'a': tg.actual_workday, 'ar': tg.actual_workday_rate} for tg in t.task_groups}
#         sum_tg_target_workday = sum_with_None([tg['tr'] for tg in tg_target_workday_mapping.values()])
#         sum_tg_actual_workday = sum_with_None([tg['ar'] for tg in tg_actual_workday_mapping.values()])

#         for tg in t.task_groups:
#             tg.target_workday_rate = calc_division(tg.target_workday_rate, sum_tg_target_workday)
#             tg.target_workday = tg.target_workday_rate * t.target_workday
#             await tg.save()
#             tgm_target_workday_mapping = {tgm.id: {'t': tgm.target_workday, 'tr': tgm.target_workday_rate} for tgm in tg.members}
#             sum_tgm_target_workday = sum_with_None([tgm['tr'] for tgm in tgm_target_workday_mapping.values()])

#             for tgm in tg.members:
#                 tgm.target_workday_rate = calc_division(tgm.target_workday_rate, sum_tgm_target_workday)
#                 tgm.target_workday = tg.target_workday * tgm.target_workday_rate
#                 await tgm.save()

#         for tg in t.task_groups:
#             tg.actual_workday_rate = calc_division(tg.actual_workday_rate, sum_tg_actual_workday)
#             tg.actual_workday = tg.actual_workday_rate * t.actual_workday
#             await tg.save()
#             tgm_actual_workday_mapping = {tgm.id: {'a': tgm.actual_workday, 'ar': tgm.actual_workday_rate} for tgm in tg.members}
#             sum_tgm_actual_workday = sum_with_None([tgm['ar'] for tgm in tgm_actual_workday_mapping.values()])

#             for tgm in tg.members:
#                 tgm.actual_workday_rate = calc_division(tgm.actual_workday_rate, sum_tgm_actual_workday)
#                 tgm.actual_workday = tgm.actual_workday_rate * tg.actual_workday
#                 await tgm.save()
#     return SuccessResponse()


# @router.get('/workday_recalc/')
# async def debug_workday_recalc():
#     '''
#     1. 根据log恢复tgm人天
#     2. 根据tgm人天重新计算tg人天
#     3. 根据tg人天重新计算tgm人天占比和tg人天占比
#     '''
#     pattern = r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}).*?计划人天: (None|[\d.]+).*?结算人天: (None|[\d.]+)"

#     tg_set = set()
#     for tgm in await TaskGroupMember.exclude(log=[]).filter(Q(target_workday_rate=None) | Q(actual_workday_rate=None)).prefetch_related('task_group'):
#         log_index = 0
#         latest_log = tgm.log[log_index]
#         while '确认' in latest_log or '拒绝' in latest_log:
#             log_index += 1
#             latest_log = tgm.log[log_index]
#         try:
#             _, target_workday, actual_workday = re.findall(pattern, latest_log)[0]
#         except IndexError:
#             print(latest_log)
#         target_workday = None if target_workday == 'None' else float(target_workday)
#         actual_workday = None if actual_workday == 'None' else float(actual_workday)
#         if target_workday:
#             tgm.target_workday = target_workday
#         if actual_workday:
#             tgm.actual_workday = actual_workday
#         await tgm.save()
#         tg_set.add(tgm.task_group_id)

#     for tg in await TaskGroup.filter(id__in=tg_set).prefetch_related('members', 'task'):
#         tg_target_workday_mapping = {}
#         tg_actual_workday_mapping = {}
#         for tgm in tg.members:
#             tg_target_workday_mapping[tgm.id] = {'t': tgm.target_workday, 'tr': tgm.target_workday_rate}
#             tg_actual_workday_mapping[tgm.id] = {'a': tgm.actual_workday, 'ar': tgm.actual_workday_rate}
#         tg.target_workday = sum_with_None([tgm['t'] for tgm in tg_target_workday_mapping.values()])
#         if tg.target_workday:
#             tg.target_workday_rate = calc_division(tg.target_workday, tg.task.target_workday)

#         tg.actual_workday = sum_with_None([tgm['a'] for tgm in tg_actual_workday_mapping.values()])
#         if tg.actual_workday and tg.task.actual_workday:
#             tg.actual_workday_rate = calc_division(tg.actual_workday, tg.task.actual_workday)
#         for tgm in tg.members:
#             if tgm.target_workday:
#                 tgm.target_workday_rate = calc_division(tgm.target_workday, tg.target_workday)
#             if tgm.actual_workday:
#                 tgm.actual_workday_rate = calc_division(tgm.actual_workday, tg.actual_workday)
#             await tgm.save()
#         await tg.save()


# @router.get('/workday_recalc/0/')
# async def debug_workday_recalc0():
#     '''
#     1. 根据log恢复tgm人天
#     2. 根据tgm人天重新计算tg人天
#     3. 根据tg人天重新计算tgm人天占比和tg人天占比
#     '''
#     pattern = r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}).*?计划人天: (None|[\d.]+).*?结算人天: (None|[\d.]+)"

#     tg_set = set()
#     for tgm in (
#         await TaskGroupMember.exclude(log=[])
#         .filter(Q(target_workday=0, target_workday_rate__not=0) | Q(actual_workday=0, actual_workday_rate__not=0))
#         .prefetch_related('task_group')
#     ):
#         log_index = 0
#         latest_log = tgm.log[log_index]
#         while '确认' in latest_log or '拒绝' in latest_log:
#             log_index += 1
#             latest_log = tgm.log[log_index]
#         try:
#             _, target_workday, actual_workday = re.findall(pattern, latest_log)[0]
#         except IndexError:
#             print(latest_log)
#         target_workday = None if target_workday == 'None' else float(target_workday)
#         actual_workday = None if actual_workday == 'None' else float(actual_workday)
#         if target_workday:
#             tgm.target_workday = target_workday
#         if actual_workday:
#             tgm.actual_workday = actual_workday
#         await tgm.save()
#         tg_set.add(tgm.task_group_id)

#     for tg in await TaskGroup.filter(id__in=tg_set).prefetch_related('members', 'task'):
#         tg_target_workday_mapping = {}
#         tg_actual_workday_mapping = {}
#         for tgm in tg.members:
#             tg_target_workday_mapping[tgm.id] = {'t': tgm.target_workday, 'tr': tgm.target_workday_rate}
#             tg_actual_workday_mapping[tgm.id] = {'a': tgm.actual_workday, 'ar': tgm.actual_workday_rate}
#         tg.target_workday = sum_with_None([tgm['t'] for tgm in tg_target_workday_mapping.values()])
#         tg.target_workday_rate = calc_division(tg.target_workday, tg.task.target_workday)
#         tg.actual_workday = sum_with_None([tgm['a'] for tgm in tg_actual_workday_mapping.values()])
#         tg.actual_workday_rate = calc_division(tg.actual_workday, tg.task.actual_workday)
#         for tgm in tg.members:
#             tgm.target_workday_rate = calc_division(tgm.target_workday, tg.target_workday)
#             tgm.actual_workday_rate = calc_division(tgm.actual_workday, tg.actual_workday)
#             await tgm.save()
#         await tg.save()
#     return SuccessResponse()


# @router.get('/update_task_category/')
# async def debug_update_task_category():
#     task_tech_query = Task.filter(name__contains='技术服务', level=TaskLevelEnum.LEVEL_1).prefetch_related('subs__subs')
#     task_id_list = await task_tech_query.values_list('id', flat=True)
#     for t in await task_tech_query:
#         task_id_list = await recurse_task_id(t.subs, task_id_list)
#     await Task.filter(id__in=task_id_list).update(category=TaskCategoryEnum.TECH)
#     return SuccessResponse()


# @router.get('/extra_page')
# async def debug_add_extra_page():
#     await PageMenu.create(
#         id=38, title='项目奖惩', icon='icon-money', url='/project/extra', parent=3, desc='项目管理/项目奖惩', sorts=7, hidden=False
#     )
#     roles = await Role.filter(name__in=('admin', 'staff'))
#     for r in roles:
#         r.page_menu.append(38)
#         await r.save()
#     return SuccessResponse()


@router.get('/user-performance')
async def migragte_user_performance():
    sys_page = await PageMenu.get_or_none(id=9)
    sys_page.sorts = 99
    await sys_page.save()
    page, _ = await PageMenu.get_or_create(
        id=5,
        defaults={
            'title': '员工周评价',
            'icon': 'icon-team',
            'url': '/user-performance',
            'parent': None,
            'desc': '员工周评价',
            'sorts': 4,
            'hidden': False,
        },
    )
    roles = await Role.filter(name__in=('admin', 'staff'))
    for r in roles:
        if page.id not in r.page_menu:
            r.page_menu.append(page.id)
            await r.save()
    return SuccessResponse()
