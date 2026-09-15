"""把状态分类、服务编码和局部码组合为完整响应码。"""

from app.interfaces.http.shared.response.codes.contract import CodeContract


class ResponseCodeBuilder:
    """构造 ``状态分类(3) + 服务编码(3) + 局部码(4)``。

    普通响应以实际 HTTP 状态作为分类；SSE 流内错误以错误定义
    对应的 HTTP 状态作为分类，因为连接状态已经无法修改。
    """

    __slots__ = ("_service_code",)

    def __init__(self, service_code: str) -> None:
        """校验并保存当前应用的三位服务编码。"""

        if len(service_code) != 3 or not service_code.isdigit():
            raise ValueError("服务编码必须是三位数字")

        self._service_code = service_code

    @property
    def service_code(self) -> str:
        """返回当前响应工厂使用的服务编码。"""

        return self._service_code

    def build(self, code: CodeContract) -> str:
        """构造十位完整响应码。"""

        return f"{code.status_code:03d}{self._service_code}{code.code}"
