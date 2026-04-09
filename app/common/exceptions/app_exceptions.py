"""兼容层：从 ``app.common.errors`` 转发异常类。"""

from app.common.errors import BizException, SystemException

__all__ = ["BizException", "SystemException"]
