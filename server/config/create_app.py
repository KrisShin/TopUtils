import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from tortoise.contrib.fastapi import register_tortoise

from config.settings import BASE_DIR, DEBUG, TORTOISE_ORM


def create_app():
    if DEBUG:
        app = FastAPI()
    else:
        app = FastAPI(docs_url=None, redoc_url=None)

    app.mount(
        "/static",
        StaticFiles(directory=os.path.join(BASE_DIR, "statics")),
        name="static",
    )
    origins = [
        # "http://localhost:5173",
        # "http://127.0.0.1:5173",
        "*"
    ]

    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        # expose_headers=["*"],
    )

    register_tortoise(
        app,
        config=TORTOISE_ORM,
        # generate_schemas=True,
        add_exception_handlers=True,
    )

    return app


app = create_app()
