"""声明跨向量驱动统一的异步操作协议。"""

from typing import Protocol

from app.infrastructure.vector.models import (
    VectorCollectionInfo,
    VectorCollectionSpec,
    VectorFilters,
    VectorMatch,
    VectorPoint,
)


class VectorClient(Protocol):
    """提供 Collection 管理、向量 CRUD、检索和健康检查。"""

    async def ping(self) -> bool:
        """验证底层向量资源当前是否可访问。"""

        ...

    async def create_collection(self, spec: VectorCollectionSpec) -> None:
        """创建 Collection，并在名称冲突时抛出稳定异常。"""

        ...

    async def has_collection(self, name: str) -> bool:
        """判断指定 Collection 是否存在。"""

        ...

    async def describe_collection(self, name: str) -> VectorCollectionInfo:
        """读取 Collection 的公共结构信息。"""

        ...

    async def delete_collection(self, name: str) -> None:
        """删除指定 Collection，不存在时抛出稳定异常。"""

        ...

    async def upsert(self, collection: str, points: tuple[VectorPoint, ...]) -> None:
        """按 ID 插入或覆盖一批向量。"""

        ...

    async def get(self, collection: str, ids: tuple[str, ...]) -> tuple[VectorPoint, ...]:
        """按调用方 ID 顺序读取存在的向量。"""

        ...

    async def delete(self, collection: str, ids: tuple[str, ...]) -> None:
        """删除一批向量 ID；缺失 ID 视为幂等成功。"""

        ...

    async def search(
        self,
        collection: str,
        vector: tuple[float, ...],
        *,
        limit: int,
        filters: VectorFilters | None = None,
    ) -> tuple[VectorMatch, ...]:
        """返回相关度降序的近邻，并支持顶层标量等值过滤。"""

        ...

    async def aclose(self) -> None:
        """释放客户端持有的连接或本地资源。"""

        ...
