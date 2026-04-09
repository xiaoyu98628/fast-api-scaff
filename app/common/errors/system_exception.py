"""系统异常：用于系统内部错误或第三方依赖错误。"""

from enum import IntEnum

from app.common.errors.code_builder import get_error_code_builder
from app.common.errors.error_types import ErrorType


class SystemException(Exception):
    """系统/第三方异常。"""

    __slots__ = ("code", "message", "biz_code", "status_code")

    def __init__(
        self,
        code: IntEnum | int,
        message: str | None = None,
        *,
        error_type: ErrorType | int = ErrorType.SYSTEM,
    ) -> None:
        aa = int(error_type)
        if aa not in (ErrorType.SYSTEM, ErrorType.THIRD):
            raise ValueError("SystemException 仅支持 SYSTEM(20) 或 THIRD(30)")
        self.biz_code = int(code)
        self.message = message if message is not None else getattr(code, "message", lambda: "系统异常")()
        self.status_code = int(getattr(code, "status_code", lambda: 500)())
        self.code = get_error_code_builder().build(
            code=self.biz_code,
            error_type=aa,
        )
        super().__init__(self.message)
