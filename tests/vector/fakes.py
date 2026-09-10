"""提供不依赖具体 SDK 的向量客户端和 Provider 测试替身。"""

from app.infrastructure.vector.contracts.provider import VectorResourceDefinition
from app.infrastructure.vector.errors import VectorCollectionConflictError, VectorCollectionNotFoundError
from app.infrastructure.vector.models import (
    VectorCollectionInfo,
    VectorCollectionSpec,
    VectorFilters,
    VectorMatch,
    VectorPoint,
)
from app.infrastructure.vector.resource import VectorResource


class FakeVectorClient:
    """在内存中实现公共向量协议，供生命周期测试使用。"""

    def __init__(self) -> None:
        self.closed = False
        self.collections: dict[str, VectorCollectionSpec] = {}
        self.points: dict[str, dict[str, VectorPoint]] = {}

    async def ping(self) -> bool:
        return not self.closed

    async def create_collection(self, spec: VectorCollectionSpec) -> None:
        if spec.name in self.collections:
            raise VectorCollectionConflictError(spec.name)
        self.collections[spec.name] = spec
        self.points[spec.name] = {}

    async def has_collection(self, name: str) -> bool:
        return name in self.collections

    async def describe_collection(self, name: str) -> VectorCollectionInfo:
        try:
            spec = self.collections[name]
        except KeyError as error:
            raise VectorCollectionNotFoundError(name) from error
        return VectorCollectionInfo(name=spec.name, dimension=spec.dimension, metric=spec.metric)

    async def delete_collection(self, name: str) -> None:
        if name not in self.collections:
            raise VectorCollectionNotFoundError(name)
        del self.collections[name]
        del self.points[name]

    async def upsert(self, collection: str, points: tuple[VectorPoint, ...]) -> None:
        self.points[collection].update({point.id: point for point in points})

    async def get(self, collection: str, ids: tuple[str, ...]) -> tuple[VectorPoint, ...]:
        values = self.points[collection]
        return tuple(values[point_id] for point_id in ids if point_id in values)

    async def delete(self, collection: str, ids: tuple[str, ...]) -> None:
        for point_id in ids:
            self.points[collection].pop(point_id, None)

    async def search(
        self,
        collection: str,
        vector: tuple[float, ...],
        *,
        limit: int,
        filters: VectorFilters | None = None,
    ) -> tuple[VectorMatch, ...]:
        del vector
        matches = []
        for point in self.points[collection].values():
            if filters and any(point.metadata.get(key) != value for key, value in filters.items()):
                continue
            matches.append(VectorMatch(id=point.id, score=1.0, metadata=point.metadata))
        return tuple(matches[:limit])

    async def aclose(self) -> None:
        self.closed = True


class FakeVectorProvider:
    """创建可观察的独立 FakeVectorClient。"""

    def __init__(self, driver: str = "fake") -> None:
        self.driver = driver
        self.clients: list[FakeVectorClient] = []

    def prepare(self, raw_config: dict[str, object]) -> VectorResourceDefinition:
        if set(raw_config) != {"driver"}:
            raise ValueError("Fake 向量连接配置不合法")
        return VectorResourceDefinition(factory=self._create)

    async def _create(self) -> VectorResource:
        client = FakeVectorClient()
        self.clients.append(client)
        return VectorResource(client)
