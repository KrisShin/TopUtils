from fastapi import APIRouter, Depends
from tortoise.expressions import Q

from module.common.accepts import SuccessResponse
from module.common.constrants import ROLE_ADMIN
from module.common.exceptions import NoPermission
from module.common.global_variable import DataResponse
from module.common.models import PeriodEnum
from module.common.utils import format_date_to_period, get_thursday
from module.user.models import User, UserWeekPerformance
from module.user.pydantics import CreateWeekPerfParamPydantic, EditWeekPerfParamPydantic, WeekPerfParamPydantic
from module.user.utils import current_user


router = APIRouter(prefix='/performance')


@router.post('/')
async def post_user_week_performance(params: WeekPerfParamPydantic, user: User = Depends(current_user)):
    """search user week performance"""

    week_perf_queryset = (
        UserWeekPerformance.filter(thursday__gte=params.date_range[0], thursday__lte=params.date_range[1], user_id__in=params.user_ids)
        .prefetch_related('user')
        .order_by('thursday', 'user_id')
    )
    if user.role_id != ROLE_ADMIN:
        week_perf_queryset = week_perf_queryset.filter(user=user)

    table_columns = {}
    data = {}
    for perf in await week_perf_queryset:
        key_str = perf.thursday.strftime('%Y-%m-%d')
        table_columns[key_str] = {'title': format_date_to_period(perf.thursday, period_type=PeriodEnum.WEEK), 'dataIndex': key_str}
        s_row = data.get(
            f's-{perf.user_id}',
            {
                'nickname': perf.user.nickname,
                'user_id': perf.user_id,
                'category': '周评价',
                'key': perf.id,
                'id': perf.id,
            },
        )
        e_row = data.get(
            f'e-{perf.user_id}',
            {
                'nickname': perf.user.nickname,
                'user_id': perf.user_id,
                'category': '额外人天',
                'key': perf.id + 1e6,
                'id': perf.id,
                'desc_mapping': {},
            },
        )
        s_row[key_str] = perf.score
        e_row[key_str] = perf.extra_workday
        e_row['desc_mapping'][key_str] = perf.description
        data[f's-{perf.user_id}'] = s_row
        data[f'e-{perf.user_id}'] = e_row
    response = {'data': list(data.values()), 'columns': list(table_columns.values())}
    return DataResponse(data=response)


@router.put('/')
async def put_edit_current_user_week_performance(params: EditWeekPerfParamPydantic, user: User = Depends(current_user)):
    """edit this week performance"""
    if user.role_id != ROLE_ADMIN:
        return NoPermission('你无权执行此操作')
    perf_obj = await UserWeekPerformance.get_or_none(user_id=params.user_id, thursday=params.thursday)
    if params.score is not None:
        perf_obj.score = params.score
    if params.extra_workday is not None:
        perf_obj.extra_workday = params.extra_workday
    if params.description is not None:
        perf_obj.description = params.description
    await perf_obj.save()
    return SuccessResponse()


@router.post('/create/')
async def post_create_current_user_week_performance(params: CreateWeekPerfParamPydantic, user: User = Depends(current_user)):
    """create this week performance"""
    if user.role_id != ROLE_ADMIN:
        return NoPermission('你无权执行此操作')
    staff_user = await User.filter(
        Q(disabled=False) & Q(Q(leave_date__isnull=True) | Q(leave_date__gte=params.thursday)) & Q(role_id__lte=ROLE_ADMIN)
    ).exclude(
        id__in=(1, 2, 29, 30)
    )  # exclude admin 李立理 test1 test2

    for staff in staff_user:
        await UserWeekPerformance.get_or_create(user=staff, thursday=params.thursday, defaults={'score': 100})
    return SuccessResponse()
