"""统一错误体系入口。"""

from app.common.errors.biz_exception import BizException
from app.common.errors.code_builder import ErrorCodeBuilder, get_error_code_builder
from app.common.errors.error_types import ErrorType
from app.common.errors.handler import register_exception_handlers
from app.common.errors.system_exception import SystemException

__all__ = [
    "BizException",
    "ErrorCodeBuilder",
    "ErrorType",
    "SystemException",
    "get_error_code_builder",
    "register_exception_handlers",
]
