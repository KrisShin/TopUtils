import time
from fastapi import Request, Response, status
from starlette.middleware.base import BaseHTTPMiddleware
from server.config.settings import DEBUG, DEV
from server.module.common.global_variable import access_logger, error_logger
from server.module.user.utils import validate_token


class LogMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        start_time = time.time()

        # 获取请求的 IP 地址
        client_ip = request.client.host

        # 获取当前用户信息（假设已经通过依赖注入获取了用户）
        token = request.headers.get('authorization')
        try:
            user = await validate_token(token.split()[-1])
            username = user['username']
        except Exception:
            # from traceback import print_exc
            # print_exc()
            username = "anonymous"
            role = 'unknown'

        # access_logger.info(f"Incoming request from user: {username}[{role}] at {client_ip} - {request.method} {request.url.path}")

        try:
            response = await call_next(request)
        except Exception as e:
            from traceback import format_exc, print_exc

            err_msg = f"Error handling request from user: {username}[{role}] at {client_ip} - {request.method} {request.url.path} - {format_exc()}"
            if DEBUG or DEV:
                print_exc()
                print(err_msg, e)

            error_logger.error(err_msg)
            return Response("Internal Server Error", status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)

        access_logger.info(
            f"Completed request from user: {username}[{role}] at {client_ip} - {request.method} {request.url.path} in {time.time() - start_time:.4f} seconds code: {response.status_code}"
        )

        return response
