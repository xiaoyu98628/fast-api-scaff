
from fastapi import FastAPI

from app.interfaces.http.routers.router import api_router


def register_route(app: FastAPI) -> None:

    app.include_router(api_router)
