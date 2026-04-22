"""兼容层：从 ``app.common.errors`` 转发异常类。"""

from app.common.errors.biz_exception import BizException
from app.common.errors.system_exception import SystemException

__all__ = ["BizException", "SystemException"]
