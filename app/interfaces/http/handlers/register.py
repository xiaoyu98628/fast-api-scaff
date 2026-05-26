from fastapi import FastAPI
from fastapi.responses import JSONResponse
from starlette.requests import Request

from app.domain.user.exceptions import DomainError
from app.interfaces.http.handlers.domain_error import to_error_response


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(DomainError)
    async def domain_error_handler(_: Request, error: DomainError) -> JSONResponse:
        response, status_code = to_error_response(error)
        return JSONResponse(
            content=response.model_dump(by_alias=True, mode="json"),
            status_code=status_code,
        )
