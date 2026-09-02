from dataclasses import dataclass

from app.infrastructure.http.contracts.client import HttpClient
from app.infrastructure.http.contracts.driver import HttpDriver


@dataclass(frozen=True, slots=True)
class ManagedHttpResource:
    """组合底层驱动资源和应用公共客户端。"""

    driver: HttpDriver
    client: HttpClient

    async def aclose(self) -> None:
        await self.driver.aclose()
