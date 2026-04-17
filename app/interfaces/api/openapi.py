"""OpenAPI 文档定制（鉴权方案、公开接口标记）。"""

from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi

from app.interfaces.api.public_paths import PUBLIC_API_PATHS


def setup_openapi_security(app: FastAPI) -> None:
    """为 Swagger/OpenAPI 注入 Bearer 鉴权定义并标记受保护接口。"""

    def custom_openapi():
        if app.openapi_schema:
            return app.openapi_schema
        schema = get_openapi(
            title=app.title,
            version="1.0.0",
            description="API 文档",
            routes=app.routes,
        )
        components = schema.setdefault("components", {})
        security_schemes = components.setdefault("securitySchemes", {})
        security_schemes["BearerAuth"] = {
            "type": "http",
            "scheme": "bearer",
            "bearerFormat": "JWT",
            "description": "在此输入登录接口返回的 access_token。",
        }
        for path, methods in schema.get("paths", {}).items():
            for _, operation in methods.items():
                if path not in PUBLIC_API_PATHS:
                    operation["security"] = [{"BearerAuth": []}]
        app.openapi_schema = schema
        return app.openapi_schema

    app.openapi = custom_openapi
