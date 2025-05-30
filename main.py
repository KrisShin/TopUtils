import uvicorn

from server.config.create_app import app
from server.config.middleware import LogMiddleware
from server.config.routers import register_router
from server.config.settings import DEBUG, HTTP_PORT

register_router(app)
if not DEBUG:
    app.add_middleware(LogMiddleware)

if __name__ == '__main__':
    uvicorn.run(app, port=HTTP_PORT)
