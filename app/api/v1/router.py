from fastapi import APIRouter

from app.api.v1.endpoints import auth, test, user

v1_router = APIRouter(prefix="/v1")

v1_router.include_router(auth.router)
v1_router.include_router(user.router)
v1_router.include_router(test.router)