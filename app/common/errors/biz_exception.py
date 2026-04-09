"""业务异常：接收业务码枚举，自动构造完整错误码与 HTTP 状态码。"""

from enum import IntEnum

from app.common.errors.code_builder import get_error_code_builder
from app.common.errors.error_types import ErrorType


class BizException(Exception):
    """业务异常（AA=10）。"""

    __slots__ = ("code", "message", "biz_code", "status_code")

    def __init__(self, code: IntEnum, message: str | None = None) -> None:
        self.biz_code = int(code)
        self.message = message if message is not None else getattr(code, "message", lambda: "业务异常")()
        self.status_code = int(getattr(code, "status_code", lambda: 400)())
        self.code = get_error_code_builder().build(
            code=self.biz_code,
            error_type=ErrorType.BIZ,
        )
        super().__init__(self.message)
