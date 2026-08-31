from typing import Annotated

from fastapi import Depends, Request

from app.interfaces.http.shared.response.factory import JsonResponseFactory


def provide_json_response_factory(request: Request) -> JsonResponseFactory:
    """提供当前 FastAPI 应用持有的统一 JSON 响应工厂。"""
    factory: JsonResponseFactory = request.app.state.json_response_factory
    return factory


type JsonResponseFactoryDependency = Annotated[JsonResponseFactory, Depends(provide_json_response_factory)]
