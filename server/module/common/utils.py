from enum import Enum

from datetime import UTC, datetime, timedelta
import uuid


def get_uuid4_id() -> str:
    return uuid.uuid4().hex


def get_now_UTC_time() -> datetime:
    return datetime.now(UTC)


def get_now_str() -> str:
    """获取当前时间格式化字符串 %Y-%m-%d %H:%M:%S"""
    return (get_now_UTC_time() + timedelta(hours=8)).strftime(r'%Y-%m-%d %H:%M:%S')


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
