from fastapi import FastAPI

from app.interfaces.http.api.router import api_router
from app.interfaces.http.ws.router import ws_router


def register_route(app: FastAPI) -> None:
    app.include_router(api_router)
    app.include_router(ws_router)
