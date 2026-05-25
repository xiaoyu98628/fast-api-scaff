"""通用错误码低位定义。"""

from app.interfaces.http.support.response.code.contract import CodeDefinition, CodedEnum


class ErrorCode(CodedEnum):
    """通用错误低位（模块+具体，不含 HTTP 前缀与服务码）。"""

    # 400 - 错误的请求
    REQUEST_ERROR = CodeDefinition(code="0101", message="请求失败", status_code=400)
    CREATED_ERROR = CodeDefinition(code="0102", message="数据已存在", status_code=400)
    DELETED_ERROR = CodeDefinition(code="0103", message="数据不存在", status_code=400)
    RESOURCE_TYPE_ERROR = CodeDefinition(code="0104", message="响应字段类型未定义", status_code=400)

    # 401 - 访问被拒绝
    UNAUTHORIZED_ERROR = CodeDefinition(code="0101", message="未授权，请先登录", status_code=401)
    UNAUTHORIZED_EXPIRED_ERROR = CodeDefinition(code="0102", message="账号信息已过期，请重新登录", status_code=401)
    UNAUTHORIZED_BLACKLISTED_ERROR = CodeDefinition(code="0103", message="账号在其他设备登录，请重新登录", status_code=401)

    # 403 - 禁止访问
    FORBIDDEN_ERROR = CodeDefinition(code="0101", message="无权限访问", status_code=403)

    # 404 - 没有找到文件或目录
    NOT_FOUND = CodeDefinition(code="0101", message="未定义路由", status_code=404)
    NOT_FOUND_ERROR = CodeDefinition(code="0102", message="数据不存在", status_code=404)

    # 405 - HTTP 方法不允许
    METHOD_NOT_ALLOWED_ERROR = CodeDefinition(code="0101", message="HTTP 请求类型错误", status_code=405)

    # 422 - 参数验证失败
    PARAMETER_ERROR = CodeDefinition(code="0101", message="参数错误", status_code=422)

    # 429 - 请求频繁
    TOO_MANY_REQUESTS = CodeDefinition(code="0101", message="操作过于频繁，请稍后重试", status_code=429)

    # 500 - 网络开小差
    INTERNAL_ERROR = CodeDefinition(code="0101", message="网络开小差", status_code=500)
