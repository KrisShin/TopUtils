from fastapi import HTTPException, status


class BadRequest(HTTPException):
    def __init__(self, detail):
        super().__init__(status_code=status.HTTP_400_BAD_REQUEST, detail=[{'msg': detail}])


class NotFound(HTTPException):
    def __init__(self, detail):
        super().__init__(status_code=status.HTTP_404_NOT_FOUND, detail=[{'msg': detail}])


class TooManyRequest(HTTPException):
    def __init__(self, detail):
        super().__init__(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=[{'msg': detail}])


class AuthorizationFailed(HTTPException):
    def __init__(self, detail="Could not validate credentials"):
        super().__init__(
            status_code=status.HTTP_401_UNAUTHORIZED, headers={"WWW-Authenticate": "Bearer"}, detail=[{'msg': detail}]
        )


class NoPermission(HTTPException):
    def __init__(self, detail):
        super().__init__(status_code=status.HTTP_403_FORBIDDEN, detail=[{'msg': detail}])
