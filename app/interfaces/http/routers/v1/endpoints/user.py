
from fastapi import APIRouter

from app.interfaces.http.response.json import JsonResponse

router = APIRouter(prefix="/users", tags=["users"])

@router.get("/user")
async def index():
    return JsonResponse.success()
