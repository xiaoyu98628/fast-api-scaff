"""根据全局设置构造普通与流式 HTTPX2 客户端资源。"""

from http.cookiejar import Cookie, CookieJar, DefaultCookiePolicy
from urllib.request import Request

import httpx2

from app.config.http import HttpPoolSettings, HttpSettings
from app.infrastructure.http.drivers.httpx2.resource import Httpx2Resource
from app.infrastructure.http.logging import HTTP_LOGGER, HttpLogEvent
from app.infrastructure.logging.record import log_extra


def create_httpx2_resource(settings: HttpSettings) -> Httpx2Resource:
    """创建相互隔离的普通请求和流式请求连接池。"""

    resource = Httpx2Resource(
        standard_client=_create_client(settings, settings.pool),
        stream_client=_create_client(settings, settings.stream_pool),
        standard_pool_limit=settings.pool.max_connections,
        stream_pool_limit=settings.stream_pool.max_connections,
        pool_warning_ratio=settings.pool_warning_ratio,
        max_response_bytes=settings.max_response_bytes,
    )
    HTTP_LOGGER.info(
        "Outbound HTTP resource created",
        extra=log_extra(HttpLogEvent.RESOURCE_CREATED),
    )
    return resource


def _create_client(settings: HttpSettings, pool: HttpPoolSettings) -> httpx2.AsyncClient:
    """把公共超时、连接池和 TLS 策略映射为 HTTPX2 配置。"""

    return httpx2.AsyncClient(
        cookies=CookieJar(policy=_RejectCookies()),
        timeout=httpx2.Timeout(
            connect=settings.timeout.connect,
            read=settings.timeout.read,
            write=settings.timeout.write,
            pool=pool.timeout,
        ),
        limits=httpx2.Limits(
            max_connections=pool.max_connections,
            max_keepalive_connections=pool.max_keepalive_connections,
            keepalive_expiry=pool.keepalive_expiry,
        ),
        verify=settings.verify,
        follow_redirects=settings.follow_redirects,
        trust_env=settings.trust_env,
    )


class _RejectCookies(DefaultCookiePolicy):
    """共享连接池不保存上游会话；显式 Cookie 请求头仍由调用方控制。"""

    def set_ok(self, cookie: Cookie, request: Request) -> bool:
        """拒绝所有响应 Cookie，避免跨用户和任务继承上游身份。"""

        return False
