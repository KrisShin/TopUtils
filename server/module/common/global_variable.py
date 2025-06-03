import json
import logging
from logging.handlers import TimedRotatingFileHandler
from typing import Any

from fastapi import Response, status
from fastapi.security.oauth2 import OAuth2PasswordBearer

# 配置日志级别
loglevel = 'info'

# 配置日志格式
log_format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'


# 基础日志文件路径（日期将自动添加到文件名中）
access_log_filename = './logs/access.log'
error_log_filename = './logs/error.log'

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/user/token/")

# 配置按天分割日志文件，并在文件名中加入日期
access_handler = TimedRotatingFileHandler(
    access_log_filename,
    when='D',
    interval=1,
    backupCount=30,
    encoding='utf-8',
    utc=False,
)
error_handler = TimedRotatingFileHandler(
    error_log_filename,
    when='D',
    interval=1,
    backupCount=30,
    encoding='utf-8',
    utc=False,
)

# 设置日志格式
formatter = logging.Formatter(log_format)
access_handler.setFormatter(formatter)
error_handler.setFormatter(formatter)

# 设置日志级别
access_handler.setLevel(logging.INFO)
error_handler.setLevel(logging.ERROR)

# 配置日志记录器
access_logger = logging.getLogger('gunicorn.access')
access_logger.addHandler(access_handler)
access_logger.setLevel(logging.INFO)

error_logger = logging.getLogger('gunicorn.error')
error_logger.addHandler(error_handler)
error_logger.setLevel(logging.ERROR)


class DataResponse(object):
    """Retrun default code 200 and data"""

    def __init__(
        self,
        message: str = 'success',
        data: Any = None,
    ) -> None:
        self.message = message
        self.data = data


class BaseResponse(Response):
    """Return with status code and response message, but no data"""

    def __init__(
        self,
        message: str = 'success',
        code: int = status.HTTP_200_OK,
        data: Any = None,
    ) -> None:
        self.message = message
        self.data = data
        content = {'message': message}
        if data:
            content['data'] = data
        super().__init__(status_code=code, content=json.dumps(content))
