from fastapi import FastAPI
from tortoise import Tortoise

from config.settings import DEBUG
from module.common.apis import router as common_router
from module.common.debug_apis import router as debug_router
from module.user.apis import router as user_router


def register_router(app: FastAPI):
    """
    register router to app
    """

    Tortoise.init_models(
        [
            'module.common.models',
            'module.user.models',
            'module.project.models',
            'module.permission.models',
            'module.vetting.models',
        ],
        'models',
    )

    if DEBUG:
        app.include_router(
            debug_router,
            tags=['debug'],
            responses={404: {'description': 'Not Found'}},
            prefix="/api/debug",
        )
    app.include_router(
        common_router,
        tags=['common'],
        responses={404: {'description': 'Not Found'}},
        prefix='/api/common',
    )
    app.include_router(
        user_router,
        tags=['user'],
        responses={404: {'description': 'Not Found'}},
        prefix='/api/user',
    )
