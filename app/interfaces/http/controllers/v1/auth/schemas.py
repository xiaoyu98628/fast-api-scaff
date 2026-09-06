from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.contexts.user.application.auth_dto import TokenDTO


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    username: str = Field(min_length=1, max_length=128)
    password: str = Field(min_length=1, max_length=1024, repr=False, json_schema_extra={"writeOnly": True})


class TokenResponse(BaseModel):
    access_token: str = Field(repr=False)
    token_type: Literal["bearer"] = "bearer"
    expires_in: int

    @classmethod
    def from_dto(cls, token: TokenDTO) -> TokenResponse:
        return cls(access_token=token.access_token, expires_in=token.expires_in)
