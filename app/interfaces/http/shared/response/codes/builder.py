from app.interfaces.http.shared.response.codes.contract import CodeContract


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


_response_code_builder: ResponseCodeBuilder | None = None


def configure_response_code_builder(service_code: str) -> None:
    """配置当前进程使用的响应码构造器。"""
    global _response_code_builder

    builder = ResponseCodeBuilder(service_code)
    if _response_code_builder is not None and _response_code_builder.service_code != service_code:
        raise RuntimeError("同一进程不能配置多个服务编码")

    _response_code_builder = builder


def get_response_code_builder() -> ResponseCodeBuilder:
    """获取当前进程已经配置的响应码构造器。"""
    if _response_code_builder is None:
        raise RuntimeError("统一响应尚未完成初始化")

    return _response_code_builder
