from datetime import date, datetime
from enum import Enum, IntEnum
import json

from tortoise import fields, models


class PeriodEnum(Enum):
    DAY = 'day'
    WEEK = 'week'
    MONTH = 'month'
    SEASON = 'season'
    BIANNUAL = 'bi-annual'
    ANNUAL = 'annual'


class StatusEnum(IntEnum):
    ASSIGNING = 0
    WAITTING = 1
    PROCESSING = 2
    REPORTING = 3
    ALLOCATING = 4
    CONFIRMING = 5
    DONE = 98
    ARCHIVED = 99
    OVERTIME = -1


class DataTypeEnum(Enum):
    STRING = 'str'
    FLOAT = 'float'
    INTEGER = 'int'
    JSON = 'json'
    DATE = 'date'
    DATETIME = 'datetime'


class BaseModel(models.Model):
    # id = fields.CharField(pk=True, max_length=32, default=generate_random_id)
    id = fields.BigIntField(primary_key=True)
    create_time = fields.DatetimeField(auto_now_add=True)
    update_time = fields.DatetimeField(auto_now=True)

    class Meta:
        abstract = True


class PageMenu(BaseModel):
    title = fields.CharField(max_length=32, null=False)
    icon = fields.CharField(max_length=64, null=True)
    url = fields.CharField(max_length=128, null=False)
    parent = fields.BigIntField(null=True, db_index=True)
    desc = fields.CharField(max_length=128, null=True)
    sorts = fields.IntField(null=True, default=0)
    hidden = fields.BooleanField(default=False)

    class Meta:
        table = 'tb_page_menu'
        unique_together = ('parent', 'title')
        ordering = ('-parent', '-sorts')


class SystemParameter(BaseModel):
    """保存一些独立变量和选项"""

    name = fields.CharField(max_length=128, unique=True)
    description = fields.CharField(max_length=1024, null=True)
    data_type = fields.CharEnumField(DataTypeEnum, default=DataTypeEnum.STRING)
    data = fields.TextField(null=True)

    class Meta:
        table = 'tb_system_parameter'

    def get_data(self):
        match self.data_type:
            case DataTypeEnum.FLOAT:
                return float(self.data)
            case DataTypeEnum.INTEGER:
                return int(self.data)
            case DataTypeEnum.JSON:
                return json.loads(self.data)
            case DataTypeEnum.DATE:
                return datetime.strptime(self.data, '%Y-%m-%d').date()
            case DataTypeEnum.DATETIME:
                return datetime.strptime(self.data, '%Y-%m-%d %H:%M:%S')
            case _:
                return self.data
