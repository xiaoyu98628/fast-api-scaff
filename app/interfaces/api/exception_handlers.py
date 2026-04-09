"""接口层异常处理入口（转发到 common/errors 统一实现）。"""

from app.common.errors.handler import register_exception_handlers

__all__ = ["register_exception_handlers"]
