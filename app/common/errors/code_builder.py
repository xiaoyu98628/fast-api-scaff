"""统一错误码构造器：完整码 = HTTP(3) + 服务码(3) + 模块(2) + 具体(2)（10 位整型）。"""

from functools import lru_cache

from config.setting import settings


class ErrorCodeBuilder:
    """统一构造完整错误码，禁止业务代码手动拼接。"""

    __slots__ = ("_service_code",)

    def __init__(self, service_code: str) -> None:
        if not service_code.isdigit() or len(service_code) not in (2, 3):
            raise ValueError(f"SERVICE_CODE 须为两位或三位数字，收到: {service_code}")
        self._service_code = int(service_code.zfill(3))

    @staticmethod
    def compose_partial(module: int, detail: int) -> int:
        """由模块号与具体序号合成 Enum 低位（BB×100+CC，0～9999）。"""
        if not 0 <= module <= 99:
            raise ValueError(f"module 必须在 0～99，收到: {module}")
        if not 0 <= detail <= 99:
            raise ValueError(f"detail 必须在 0～99，收到: {detail}")
        return module * 100 + detail

    def build(self, http_status: int, partial: int) -> int:
        """构造完整错误码。

        partial 为 IntEnum 成员值：模块(两位)×100 + 具体(两位)，与 compose_partial 一致。
        """
        if not 100 <= int(http_status) <= 599:
            raise ValueError(f"http_status 须在 100～599（标准 HTTP），收到: {http_status}")
        if not 0 <= int(partial) <= 9999:
            raise ValueError(f"partial 须在 0～9999，收到: {partial}")
        return int(http_status) * 10**7 + self._service_code * 10**4 + int(partial)

    def format_code(self, http_status: int, partial: int) -> str:
        """输出 10 位字符串（左补零）。"""
        return f"{self.build(http_status=http_status, partial=partial):010d}"


@lru_cache
def get_error_code_builder() -> ErrorCodeBuilder:
    """进程内单例构造器，SERVICE_CODE 来自环境配置。"""
    return ErrorCodeBuilder(settings().service.service_code)
