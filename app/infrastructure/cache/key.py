"""构造满足 Redis 与 Memcached 共同约束的缓存 key。"""

import re
from dataclasses import dataclass

from app.infrastructure.cache.errors import CacheConfigurationError, CacheKeyError

MAX_CACHE_KEY_BYTES = 250
INVALID_KEY_CHARACTER = re.compile(r"[\x00-\x20\x7f]")


@dataclass(frozen=True, slots=True)
class CacheKeyBuilder:
    """按 namespace、连接前缀和业务 key 生成最终 key。"""

    namespace: str
    prefix: str = ""

    def __post_init__(self) -> None:
        self._validate_config_segment(self.namespace, "namespace")
        if self.prefix:
            self._validate_config_segment(self.prefix, "key_prefix")

    def build(self, key: str) -> str:
        """校验业务 key 并生成以冒号分隔的最终 UTF-8 key。"""

        if not key:
            raise CacheKeyError("缓存 key 不能为空")

        if INVALID_KEY_CHARACTER.search(key):
            raise CacheKeyError("缓存 key 不能包含空白字符或控制字符")

        final_key = ":".join(part for part in (self.namespace, self.prefix, key) if part)
        # 使用最严格的 Memcached 250 字节上限，保证切换驱动后 key 仍然可用。
        if len(final_key.encode()) > MAX_CACHE_KEY_BYTES:
            raise CacheKeyError(f"缓存 key 的 UTF-8 长度不能超过 {MAX_CACHE_KEY_BYTES} 字节")

        return final_key

    @staticmethod
    def _validate_config_segment(value: str, name: str) -> None:
        if not value:
            raise CacheConfigurationError(f"{name} 不能为空")

        if value.startswith(":") or value.endswith(":"):
            raise CacheConfigurationError(f"{name} 不能以冒号开头或结尾")

        if INVALID_KEY_CHARACTER.search(value):
            raise CacheConfigurationError(f"{name} 不能包含空白字符或控制字符")
