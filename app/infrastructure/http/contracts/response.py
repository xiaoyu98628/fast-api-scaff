import json
from dataclasses import dataclass

type HttpHeaders = tuple[tuple[str, str], ...]


@dataclass(frozen=True, slots=True)
class HttpResponse:
    """已经完整缓冲、可以脱离底层连接使用的 HTTP 响应。"""

    status_code: int
    headers: HttpHeaders
    content: bytes

    def json(self) -> object:
        return json.loads(self.content)

    def header(self, name: str) -> str | None:
        normalized_name = name.casefold()

        for header_name, value in self.headers:
            if header_name.casefold() == normalized_name:
                return value

        return None

    def header_values(self, name: str) -> tuple[str, ...]:
        normalized_name = name.casefold()
        return tuple(value for header_name, value in self.headers if header_name.casefold() == normalized_name)
