from server.config.settings import HTTP_HOST, HTTP_PORT


bind = f'{HTTP_HOST}:{HTTP_PORT}'
worker_class = 'uvicorn.workers.UvicornWorker'

# 设置 Gunicorn 的 worker 数量
workers = 2
