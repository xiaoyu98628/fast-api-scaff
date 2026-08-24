from app.interfaces.http.response.codes.contract import CodeDefinition, CodedEnum


class ErrorCode(CodedEnum):
    """跨限界上下文共用的 HTTP 错误响应码。"""

    BAD_REQUEST = CodeDefinition(code="0101", message="请求内容有误，请检查后重试", status_code=400)
    UNAUTHORIZED = CodeDefinition(code="0101", message="未授权，请先登录", status_code=401)
    FORBIDDEN = CodeDefinition(code="0101", message="无权限访问", status_code=403)
    ROUTE_NOT_FOUND = CodeDefinition(code="0101", message="未定义路由", status_code=404)
    RESOURCE_NOT_FOUND = CodeDefinition(code="0102", message="请求的数据不存在或已被删除", status_code=404)
    METHOD_NOT_ALLOWED = CodeDefinition(code="0101", message="该接口不支持当前请求方式", status_code=405)
    CONFLICT = CodeDefinition(code="0101", message="当前数据状态已发生变化，请刷新后重试", status_code=409)
    VALIDATION_ERROR = CodeDefinition(code="0101", message="请求参数有误，请检查后重试", status_code=422)
    TOO_MANY_REQUESTS = CodeDefinition(code="0101", message="操作过于频繁，请稍后重试", status_code=429)
    INTERNAL_ERROR = CodeDefinition(code="0101", message="网络开小差了，请稍后重试", status_code=500)
