"""为数据库持久化适配器提供 ULID 和 UUID 主键生成工具。"""

from secrets import token_bytes
from time import time_ns
from uuid import UUID, uuid4, uuid7

_CROCKFORD_BASE32 = "0123456789abcdefghjkmnpqrstvwxyz"
_ULID_RANDOM_BYTES = 10
_ULID_LENGTH = 26
_MAX_ULID_TIMESTAMP = (1 << 48) - 1


def new_ulid() -> str:
    """生成可保存为 CHAR(26) 的小写 Crockford Base32 ULID 主键。

    前 48 位保存 Unix 毫秒时间戳，后 80 位来自密码学安全随机数；时间超出
    48 位无符号范围时抛出 OverflowError。同一毫秒内不保证按生成顺序单调。
    """

    timestamp_ms = time_ns() // 1_000_000
    if not 0 <= timestamp_ms <= _MAX_ULID_TIMESTAMP:
        raise OverflowError("当前时间超出 ULID 48 位时间戳范围")

    # ULID 共 128 位；26 个 Base32 字符的最高两位补零，首字符不会超过 7。
    value = (timestamp_ms << 80) | int.from_bytes(token_bytes(_ULID_RANDOM_BYTES), "big")
    encoded = ["0"] * _ULID_LENGTH
    for index in range(_ULID_LENGTH - 1, -1, -1):
        encoded[index] = _CROCKFORD_BASE32[value & 0b11111]
        value >>= 5
    return "".join(encoded)


def new_uuid4() -> UUID:
    """生成随机 UUID4 主键；持久化适配器按列约定选择 str(value) 或 value.hex。"""

    return uuid4()


def new_uuid7() -> UUID:
    """生成带 Unix 毫秒时间戳的 UUID7 主键，保持标准库 UUID 类型及生成语义。"""

    return uuid7()
