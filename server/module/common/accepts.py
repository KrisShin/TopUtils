from typing import Any

from fastapi import status

from server.module.common.global_variable import BaseResponse


class SuccessResponse(BaseResponse):
    def __init__(self, message: str = 'Success!', data: Any = None) -> None:
        code: int = status.HTTP_200_OK
        super().__init__(code, message, data)


class CreatedResponse(BaseResponse):
    def __init__(self, message: str = 'Created!', data: Any = None) -> None:
        code: int = status.HTTP_201_CREATED
        super().__init__(code, message, data)


class AcceptedResponse(BaseResponse):
    def __init__(self, message: str = 'Accepted!', data: Any = None) -> None:
        code: int = status.HTTP_202_ACCEPTED
        super().__init__(code, message, data)
