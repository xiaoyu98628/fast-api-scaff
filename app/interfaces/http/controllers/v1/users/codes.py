"""定义用户 HTTP API 专用的局部错误码。"""

from app.interfaces.http.shared.response.codes.contract import CodeDefinition, CodedEnum


class UserErrorCode(CodedEnum):
    """用户限界上下文的 HTTP 错误响应码。"""

    USER_NOT_FOUND = CodeDefinition(code="1001", message="用户不存在或已被删除", status_code=404)
    USERNAME_CONFLICT = CodeDefinition(code="1002", message="用户名已存在", status_code=409)
    EMAIL_CONFLICT = CodeDefinition(code="1003", message="邮箱已存在", status_code=409)
    CONCURRENT_UPDATE = CodeDefinition(code="1004", message="用户已被并发修改，请重新读取后重试", status_code=409)
    INVALID_USER_DATA = CodeDefinition(code="1005", message="用户资料不符合要求", status_code=422)
