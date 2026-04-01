from fastapi import FastAPI

from app.api.v1 import api_router
from app import (
    api,
    middleware,
)
app = FastAPI(
    title='Fast-Api-Scaff'
)

# 中间件注册
middleware.register_middleware(app)

# 路由注册
app.include_router(api_router)

# 健康检测路由
@app.get(path="/health", summary="健康检测", description="健康检测接口")
async def root():
    return {"message": "ok"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run('app.main:app', host="127.0.0.1", port=8000, reload=True)