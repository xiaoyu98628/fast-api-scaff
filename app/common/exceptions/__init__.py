"""兼容层：统一错误体系已迁移到 ``app.common.errors``。"""

from app.common.errors import BizException, ErrorCodeBuilder, SystemException, get_error_code_builder

__all__ = [
    "BizException",
    "ErrorCodeBuilder",
    "SystemException",
    "get_error_code_builder",
]
