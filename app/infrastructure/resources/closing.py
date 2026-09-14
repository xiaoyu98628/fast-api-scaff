"""统一关闭一组命名管理器持有的异步懒加载资源。"""

from collections.abc import Iterable

from anyio import CancelScope

from app.infrastructure.resources.lazy import AsyncLazy


async def close_lazy_resources[T](resources: Iterable[AsyncLazy[T]], *, error_message: str) -> None:
    """先封锁全部资源，再逆序释放并聚合错误；失败资源保留供重试。

    调用方应先停止借用并封闭 Manager 入口。本函数不会初始化未使用资源，
    且在首次挂起前封锁所有句柄；释放序列屏蔽外层 AnyIO 取消作用域。
    """

    snapshot = tuple(resources)
    # 必须先封锁整组，再等待任何资源，防止后续句柄的初始化结果逃逸。
    for resource in snapshot:
        resource.begin_close()

    errors: list[BaseException] = []
    with CancelScope(shield=True):
        for resource in reversed(snapshot):
            try:
                await resource.aclose()
            except BaseException as error:
                errors.append(error)

    if errors:
        raise BaseExceptionGroup(error_message, errors)
