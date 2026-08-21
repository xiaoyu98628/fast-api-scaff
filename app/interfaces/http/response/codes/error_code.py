from app.interfaces.http.response.codes.contract import CodeDefinition, CodedEnum


class ErrorCode(CodedEnum):
    """跨限界上下文共用的 HTTP 错误响应码。"""

    BAD_REQUEST = CodeDefinition(code="0101", message="请求失败", status_code=400)
    UNAUTHORIZED = CodeDefinition(code="0101", message="未授权，请先登录", status_code=401)
    FORBIDDEN = CodeDefinition(code="0101", message="无权限访问", status_code=403)
    NOT_FOUND = CodeDefinition(code="0101", message="请求的资源不存在", status_code=404)
    METHOD_NOT_ALLOWED = CodeDefinition(code="0101", message="请求方法不被允许", status_code=405)
    VALIDATION_ERROR = CodeDefinition(code="0101", message="请求参数不合法", status_code=422)
    TOO_MANY_REQUESTS = CodeDefinition(code="0101", message="操作过于频繁，请稍后重试", status_code=429)
    INTERNAL_ERROR = CodeDefinition(code="0101", message="服务器内部错误", status_code=500)
