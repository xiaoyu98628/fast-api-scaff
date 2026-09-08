"""创建携带完整响应码和 Request ID 的统一 JSON 载荷。"""

from dataclasses import dataclass

from starlette_context import context
from starlette_context.header_keys import HeaderKeys

from app.interfaces.http.shared.response.codes.builder import ResponseCodeBuilder
from app.interfaces.http.shared.response.codes.contract import CodeContract
from app.interfaces.http.shared.response.codes.error_code import ErrorCode
from app.interfaces.http.shared.response.codes.success_code import SuccessCode
from app.interfaces.http.shared.response.json import JsonResponse


@dataclass(frozen=True, slots=True)
class JsonResponseFactory:
    """使用当前 HTTP 应用的服务编码构造统一 JSON 响应。"""

    code_builder: ResponseCodeBuilder

    def success[DataT](
        self,
        data: DataT,
        *,
        code: CodeContract = SuccessCode.OK,
        message: str | None = None,
        request_id: str | None = None,
    ) -> JsonResponse[DataT]:
        """构建使用 2xx 状态定义的成功响应载荷。"""

        if not 200 <= code.status_code < 300:
            raise ValueError("成功响应必须使用 2xx 响应码")

        return JsonResponse(
            code=self.code_builder.build(code),
            success=True,
            message=message if message is not None else code.message,
            data=data,
            request_id=_resolve_request_id(request_id),
        )

    def error(
        self,
        code: CodeContract = ErrorCode.BAD_REQUEST,
        *,
        message: str | None = None,
        data: object | None = None,
        request_id: str | None = None,
    ) -> JsonResponse[object]:
        """构建使用 4xx 或 5xx 状态定义的错误响应载荷。"""

        if code.status_code < 400:
            raise ValueError("错误响应必须使用 4xx 或 5xx 响应码")

        return JsonResponse(
            code=self.code_builder.build(code),
            success=False,
            message=message if message is not None else code.message,
            data=data,
            request_id=_resolve_request_id(request_id),
        )


def _resolve_request_id(explicit: str | None) -> str | None:
    """优先使用显式 ID，否则读取当前 Starlette 请求上下文。"""

    # 显式空字符串也属于调用方选择，只有 None 才触发上下文回退。
    if explicit is not None:
        return explicit

    if not context.exists():
        return None

    request_id = context.get(HeaderKeys.request_id)
    return str(request_id) if request_id is not None else None
