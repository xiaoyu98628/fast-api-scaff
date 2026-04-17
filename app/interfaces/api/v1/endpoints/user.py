"""用户接口：保留用户域接口（登录迁移到 auth）。"""

from fastapi import APIRouter

router = APIRouter(prefix="/users", tags=["users"])
