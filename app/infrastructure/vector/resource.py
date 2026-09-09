"""组合统一向量客户端及其异步关闭入口。"""

from dataclasses import dataclass

from app.infrastructure.vector.contracts.client import VectorClient


@dataclass(frozen=True, slots=True)
class VectorResource:
    """保存一个已经创建且生命周期受控的向量客户端。"""

    client: VectorClient

    async def aclose(self) -> None:
        """关闭底层客户端。"""

        await self.client.aclose()
