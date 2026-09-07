from app.interfaces.worker.registry import HandlerRegistry
from app.runtime.container import ApplicationContainer


def build_worker_registry(container: ApplicationContainer) -> HandlerRegistry:
    """在这里显式绑定业务 Handler；发布类型由上下文/全局组合根注册到 queues.catalog。"""
    return HandlerRegistry()
