"""系统异常：用于系统内部错误或第三方依赖错误。"""

from enum import StrEnum

from app.common.errors.code_builder import get_error_code_builder


class SystemException(Exception):
    """系统/第三方异常。"""

    __slots__ = ("code", "message", "biz_code", "status_code")

    def __init__(self, code: StrEnum | int, message: str | None = None) -> None:
        self.biz_code = int(code)
        self.message = message if message is not None else getattr(code, "message", lambda: "系统异常")()
        self.status_code = int(getattr(code, "status_code", lambda: 500)())
        self.code = get_error_code_builder().build(
            http_status=self.status_code,
            partial=self.biz_code,
        )
        super().__init__(self.message)
