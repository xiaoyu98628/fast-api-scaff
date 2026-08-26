import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError

from app.bootstrap.app import create_app
from app.config.app import AppSettings
from app.config.cache import CacheSettings
from app.config.cors import CorsSettings
from app.config.database import DatabaseSettings
from app.config.settings import Settings
from app.interfaces.http.shared.response.codes.builder import (
    ResponseCodeBuilder,
    configure_response_code_builder,
)
from app.interfaces.http.shared.response.codes.contract import CodeDefinition
from app.interfaces.http.shared.response.codes.error_code import ErrorCode
from app.interfaces.http.shared.response.codes.success_code import SuccessCode
from app.interfaces.http.shared.response.json import JsonResponse


def build_settings(service_code: str = "001") -> Settings:
    return Settings(
        app=AppSettings(service_code=service_code, _env_file=None),
        database=DatabaseSettings(_env_file=None),
        cache=CacheSettings(_env_file=None),
        cors=CorsSettings(_env_file=None),
    )


def test_app_settings_loads_and_validates_service_code(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_SERVICE_CODE", "321")

    assert AppSettings(_env_file=None).service_code == "321"

    with pytest.raises(ValidationError):
        AppSettings(service_code="01", _env_file=None)


def test_response_code_definition_and_builder() -> None:
    builder = ResponseCodeBuilder("001")

    assert builder.build(SuccessCode.OK) == "2000010000"
    assert builder.build(ErrorCode.ROUTE_NOT_FOUND) == "4040010101"
    assert builder.build(ErrorCode.RESOURCE_NOT_FOUND) == "4040010102"
    assert builder.build(ErrorCode.CONFLICT) == "4090010101"
    assert builder.service_code == "001"

    with pytest.raises(ValueError, match="四位数字"):
        CodeDefinition(code="001", message="invalid", status_code=400)

    with pytest.raises(ValueError, match="三位数字"):
        ResponseCodeBuilder("01")


def test_json_response_requires_configuration() -> None:
    with pytest.raises(RuntimeError, match="尚未完成初始化"):
        JsonResponse.success(data={"value": 1})


def test_json_response_builds_success_and_error() -> None:
    configure_response_code_builder("123")

    success = JsonResponse.success(data={"value": 1}, request_id="request-success")
    error = JsonResponse.error(
        ErrorCode.VALIDATION_ERROR,
        data={"field": "name"},
        request_id="request-error",
    )

    assert success.model_dump() == {
        "code": "2001230000",
        "success": True,
        "message": "请求成功",
        "data": {"value": 1},
        "request_id": "request-success",
    }
    assert error.model_dump() == {
        "code": "4221230101",
        "success": False,
        "message": "请求参数有误，请检查后重试",
        "data": {"field": "name"},
        "request_id": "request-error",
    }

    with pytest.raises(ValueError, match="2xx"):
        JsonResponse.success(data=None, code=ErrorCode.BAD_REQUEST)

    with pytest.raises(ValueError, match="4xx 或 5xx"):
        JsonResponse.error(SuccessCode.OK)


def test_response_code_builder_rejects_conflicting_service_code() -> None:
    configure_response_code_builder("001")

    with pytest.raises(RuntimeError, match="同一进程不能配置多个服务编码"):
        configure_response_code_builder("002")


@pytest.mark.asyncio
async def test_health_uses_unified_response() -> None:
    app = create_app(build_settings(service_code="321"))

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
        response = await client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "code": "2003210000",
        "success": True,
        "message": "请求成功",
        "data": {"message": "ok"},
        "request_id": response.headers["X-Request-ID"],
    }


@pytest.mark.parametrize("success_code", [SuccessCode.CREATED, SuccessCode.ACCEPTED])
@pytest.mark.asyncio
async def test_non_ok_success_keeps_http_status_and_response_code_consistent(success_code: SuccessCode) -> None:
    app = create_app(build_settings(service_code="321"))

    @app.post(
        "/items",
        status_code=success_code.status_code,
        response_model=JsonResponse[dict[str, int]],
    )
    async def create_item() -> JsonResponse[dict[str, int]]:
        return JsonResponse.success(data={"id": 1}, code=success_code)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
        response = await client.post("/items")

    body = response.json()

    assert response.status_code == success_code.status_code
    assert body["code"] == f"{success_code.status_code:03d}321{success_code.code}"
    assert body["success"] is True
    assert body["request_id"] == response.headers["X-Request-ID"]
