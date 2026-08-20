class BaseCache:
    """缓存实现共享的 key 前缀和 TTL 规则。"""

    def __init__(self, key_prefix: str = "") -> None:
        self._key_prefix = key_prefix

    def _prefixed_key(self, key: str) -> str:
        return f"{self._key_prefix}{key}"

    @staticmethod
    def _validate_ttl(ttl: int | None) -> None:
        if ttl is not None and ttl <= 0:
            raise ValueError("ttl 必须为正整数或 None")
