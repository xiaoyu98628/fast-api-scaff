from app.interfaces.http.shared.response.codes.contract import CodeDefinition, CodedEnum


class SuccessCode(CodedEnum):
    """跨限界上下文共用的成功响应码。"""

    OK = CodeDefinition(code="0000", message="请求成功", status_code=200)
    CREATED = CodeDefinition(code="0000", message="创建成功", status_code=201)
    ACCEPTED = CodeDefinition(code="0000", message="请求已接受", status_code=202)
