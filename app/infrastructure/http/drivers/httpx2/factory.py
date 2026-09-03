import httpx2

from app.config.http import HttpPoolSettings, HttpSettings
from app.infrastructure.http.drivers.httpx2.resource import Httpx2Resource
from app.infrastructure.http.logging import HTTP_LOGGER, HttpLogEvent
from app.infrastructure.logging.record import log_extra


def create_httpx2_resource(settings: HttpSettings) -> Httpx2Resource:
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
    return httpx2.AsyncClient(
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
