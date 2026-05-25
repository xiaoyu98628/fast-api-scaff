"""通用成功码低位定义。"""

from app.interfaces.http.support.response.code.contract import CodeDefinition, CodedEnum


class SuccessCode(CodedEnum):
    """成功响应低位编码（模块+具体，不含 HTTP 前缀与服务码）。"""

    SUCCESS_OK = CodeDefinition(code="0000", message="请求成功", status_code=200)
    SUCCESS_CREATED = CodeDefinition(code="0000", message="创建成功", status_code=201)
    SUCCESS_ACCEPTED = CodeDefinition(code="0000", message="请求已接受，正在处理中", status_code=202)
    SUCCESS_NO_CONTENT = CodeDefinition(code="0000", message="操作成功", status_code=204)
    SUCCESS_RESET_CONTENT = CodeDefinition(code="0000", message="操作成功，请刷新", status_code=205)
