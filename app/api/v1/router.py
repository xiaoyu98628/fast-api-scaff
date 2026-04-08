from fastapi import APIRouter
from .endpoints import test

v1_router = APIRouter(prefix='/v1')

v1_router.include_router(test.router)