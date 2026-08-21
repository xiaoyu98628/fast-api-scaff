from app.interfaces.http.response.codes.contract import CodeContract


class ResponseCodeBuilder:
    """构造 ``HTTP(3) + 服务编码(3) + 局部码(4)``。"""

    __slots__ = ("_service_code",)

    def __init__(self, service_code: str) -> None:
        if len(service_code) != 3 or not service_code.isdigit():
            raise ValueError("服务编码必须是三位数字")

        self._service_code = service_code

    @property
    def service_code(self) -> str:
        return self._service_code

    def build(self, code: CodeContract) -> str:
        return f"{code.status_code:03d}{self._service_code}{code.code}"
