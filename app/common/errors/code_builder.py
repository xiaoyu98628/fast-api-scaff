"""统一错误码构造器：完整码 = SS + AA + XXXXX（9 位整型）。"""

from functools import lru_cache

from app.common.errors.error_types import ErrorType
from config.config import get_config


class ErrorCodeBuilder:
    """统一构造完整错误码，禁止业务代码手动拼接。"""

    __slots__ = ("_service_code",)

    def __init__(self, service_code: str) -> None:
        if not service_code.isdigit() or len(service_code) != 2:
            raise ValueError(f"SERVICE_CODE 必须是两位数字，收到: {service_code}")
        self._service_code = int(service_code)

    def build(self, code: int, error_type: ErrorType | int) -> int:
        """构造完整错误码（SSAAxxxxx）。"""
        aa = int(error_type)
        if aa not in (ErrorType.BIZ, ErrorType.SYSTEM, ErrorType.THIRD):
            raise ValueError(f"error_type 仅支持 10/20/30，收到: {aa}")
        if not 0 <= int(code) <= 99_999:
            raise ValueError(f"业务码必须是 0~99999 的整数，收到: {code}")
        return self._service_code * 10**7 + aa * 10**5 + int(code)

    def format_code(self, code: int, error_type: ErrorType | int) -> str:
        """输出 9 位字符串（左补零）。"""
        return f"{self.build(code=code, error_type=error_type):09d}"


@lru_cache
def get_error_code_builder() -> ErrorCodeBuilder:
    """进程内单例构造器，SERVICE_CODE 来自环境配置。"""
    return ErrorCodeBuilder(get_config().service.service_code)
