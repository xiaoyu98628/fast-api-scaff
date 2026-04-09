"""兼容层：从 ``app.common.errors.code_builder`` 转发。"""

from app.common.errors.code_builder import ErrorCodeBuilder, get_error_code_builder

__all__ = ["ErrorCodeBuilder", "get_error_code_builder"]
