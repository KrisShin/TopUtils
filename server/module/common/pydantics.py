from datetime import timedelta
from enum import Enum
from typing import Optional

from pydantic import BaseModel
from tortoise.contrib.pydantic import pydantic_model_creator

from module.common.models import DataTypeEnum, PageMenu


class _OptionType:
    code: int
    limit: int  # limit times
    expire: timedelta  # seconds

    def __init__(self, code, limit, expire) -> None:
        super().__init__()
        self.code = code
        self.limit = limit
        self.expire = timedelta(seconds=expire)


class UserOperation(Enum):
    TRY_PASSWORD: _OptionType = _OptionType(1, 3, 5 * 60)
    EDIT_INFO: _OptionType = _OptionType(2, 1, 30 * 60)
    EDIT_PASSWORD: _OptionType = _OptionType(3, 1, 60 * 60 * 24)
    EDIT_AVATAR: _OptionType = _OptionType(4, 1, 30 * 60)
    # ADD_CONTACT: _OptionType = _OptionType(5, 50, 60 * 60 * 24)
    # SEND_MESSAGE: _OptionType = _OptionType(6, 100, 5 * 60)


PageMenuPydantic = pydantic_model_creator(PageMenu, name='PageMenuPydantic')


class SystemParameterCreatePydantic(BaseModel):
    name: str
    description: Optional[str | None]
    data_type: DataTypeEnum
    data: str


class SystemParameterUpdatePydantic(BaseModel):
    description: Optional[str | None]
    data_type: DataTypeEnum
    data: str
