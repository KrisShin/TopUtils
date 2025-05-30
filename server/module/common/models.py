from datetime import datetime
from enum import Enum
import json

from tortoise import fields, models


class DataTypeEnum(Enum):
    STRING = 'str'
    FLOAT = 'float'
    INTEGER = 'int'
    JSON = 'json'
    DATE = 'date'
    DATETIME = 'datetime'


class TagCategoryEnum(Enum):
    UTIL = 'util'
    ORDER = 'order'


class BaseModel(models.Model):
    # id = fields.CharField(pk=True, max_length=32, default=generate_random_id)
    id = fields.BigIntField(primary_key=True)
    create_time = fields.DatetimeField(auto_now_add=True)
    update_time = fields.DatetimeField(auto_now=True)

    class Meta:
        abstract = True


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


class Tag(BaseModel):
    """标签模型"""

    name = fields.CharField(max_length=128, unique=True)
    description = fields.CharField(max_length=512, null=True)
    color = fields.CharField(max_length=32, null=True)  # 标签颜色
    category = fields.CharEnumField(TagCategoryEnum, default=TagCategoryEnum.UTIL, db_index=True)  # 标签分类

    class Meta:
        table = 'tb_tag'
        ordering = ('name',)

    def __str__(self):
        return self.name
