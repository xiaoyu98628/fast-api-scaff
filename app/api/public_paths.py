"""公开路径常量：统一维护鉴权与文档可见性白名单。"""

PUBLIC_API_PATHS = {
    "/health",
    "/api/v1/auth/login",
    "/api/v1/test/health",
    "/api/v1/test/db-health",
    "/api/v1/test/redis-health",
}

PUBLIC_DOC_PATHS = {
    "/docs",
    "/openapi.json",
    "/redoc",
}

PUBLIC_AUTH_SKIP_PATHS = PUBLIC_API_PATHS | PUBLIC_DOC_PATHS
