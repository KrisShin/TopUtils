import time
from contextlib import contextmanager
from enum import Enum

import calendar
import math
from datetime import UTC, date, datetime, timedelta
from typing import List

from config.settings import DEBUG
from module.common.models import PeriodEnum
from module.common.global_variable import access_logger


def get_thursday(date: date = None) -> date:
    # 获取当前日期
    if not date:
        date = datetime.today()

    # 计算当前周的周一（ISO周从周一开始）
    current_monday = date - timedelta(days=date.isoweekday() - 1)

    # 当前周的周四是周一 + 3天
    current_thursday = current_monday + timedelta(days=3)
    return current_thursday


def get_week_of_month(date: date):
    """get the week of month"""
    first_day = date.replace(day=1)
    first_day_weekday = first_day.weekday()

    day_of_month = date.day
    adjusted_day_of_month = day_of_month + first_day_weekday

    week_of_month = (adjusted_day_of_month - 1) // 7 + 1

    return week_of_month


def format_date_to_period(item: date | datetime, period_type: PeriodEnum):
    match period_type:
        case PeriodEnum.DAY:
            return item.strftime('%Y-%m-%d')
        case PeriodEnum.WEEK:
            return item.strftime('%Y年%m月') + f'第{get_week_of_month(item)}周'
        case PeriodEnum.MONTH:
            return item.strftime('%Y-%m')
        case PeriodEnum.SEASON:
            return f'{item.year}-Q{math.ceil(item.month/3)}'
        case PeriodEnum.BIANNUAL:
            return f'{item.year}-Q{math.ceil(item.month/6)}'
        case PeriodEnum.ANNUAL:
            return str(item.year)
        case _:
            return


def sum_with_None(num_list: list, default_res=None) -> float | None:
    """排除列表中的None求和, 如果全是None 则返回None"""
    num_list = [float(n) for n in num_list if n is not None]
    if len(num_list) == 0:
        return default_res
    return round(sum(num_list), 8)


def get_period_nodes(start_date: date, end_date: date, period_type: PeriodEnum = PeriodEnum.MONTH, past_now: bool = True) -> List[str]:
    today = date.today()
    """根据起始时间和结束时间计算中间的时间点"""
    if period_type != PeriodEnum.MONTH:
        raise Exception('暂不支持的时间点计算')
    period_node = []
    for year in range(start_date.year, end_date.year + 1):
        if not past_now and (year > today.year):
            break
        if year == start_date.year:
            start_month = start_date.month
        else:
            start_month = 1
        if year == end_date.year:
            end_month = end_date.month
        else:
            end_month = 12
        for month in range(start_month, end_month + 1):
            period_node.append(f"{year}-{str(month).rjust(2,'0')}")
    return period_node


def get_now_UTC_time() -> datetime:
    return datetime.now(UTC)


def get_now_str() -> str:
    """获取当前时间格式化字符串 %Y-%m-%d %H:%M:%S"""
    return (get_now_UTC_time() + timedelta(hours=8)).strftime(r'%Y-%m-%d %H:%M:%S')


def get_last_second_of_month(year: int = None, month: int = None, date_obj: date | datetime = None):
    if date_obj:
        year, month = date_obj.year, date_obj.month
    # 获取指定月份的最后一天
    last_day = calendar.monthrange(year, month)[1]
    # 返回该月的最后一秒
    return datetime(year, month, last_day, 23, 59, 59)


def get_next_month(now: date = None) -> date:
    """获取下个月最后一天的最后一秒"""
    # 获取当前时间
    now = now or get_now_UTC_time()

    # 计算月份和年份
    year = now.year + ((now.month + 1) // 12)
    month = now.month % 12 + 1
    # 获取该月的最后一秒
    return get_last_second_of_month(year, month)


def get_next_3_month() -> date:
    """获取后三个月后的当月最后一秒"""
    # 获取当前时间
    now = get_now_UTC_time()

    year = now.year + ((now.month + 3) // 12)
    month = (now.month + 3 - 1) % 12 + 1
    return get_last_second_of_month(year, month)


@contextmanager
def time_logger(label):
    if not DEBUG:
        return
    start_time = time.perf_counter()
    yield
    end_time = time.perf_counter()
    print(f"{label}: {end_time - start_time:.4f} seconds")


def none_or_false_in_args(*args: list, mode: str = 'all') -> bool:
    """
    all mode[default]: if None or False in args, return False otherwise True
    any mode[optional]: if any elements is not None or False return True
    """
    if mode == 'all':
        for x in args:
            if x is None or x is False:
                return True
        else:
            return False
    elif mode == 'any':
        for x in args:
            if x is not False and x is not None:
                return False
        else:
            return True
    else:
        raise Exception('Unsupported mode')


def logger_async_task_start(msg):
    access_logger.info(f'>>>> async task: {msg} START')
    print(f'>>>> async task: {msg} START')


def logger_async_task_process(msg):
    access_logger.info(f'---- {msg}: DONE')
    print(f'---- {msg}: DONE')


def logger_async_task_done(msg):
    access_logger.info(f'>>>> async task: {msg} ALL DONE!!!')
    print(f'>>>> async task: {msg} ALL DONE!!!')


def json_encoder(item):
    if isinstance(item, Enum):
        return item.value
    return str(item)


def calc_division(dividend: float, divisor: float, percentage: float = 1):
    if dividend is None or divisor is None:
        return None
    elif dividend == 0 or divisor == 0:
        return 0
    else:
        return dividend / divisor * percentage
