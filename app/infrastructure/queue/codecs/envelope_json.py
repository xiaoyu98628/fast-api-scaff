"""在队列传输字节和版本化 JSON 消息信封之间转换。"""

import base64
import json
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from app.infrastructure.queue.contracts.message import MessageEnvelope
from app.infrastructure.queue.errors import InvalidMessageError


class EnvelopeData(BaseModel):
    """使用严格字段约束验证外层消息协议。"""

    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)
    schema_version: int = Field(default=2, strict=True, ge=2, le=2)
    job_id: UUID
    job_type: str = Field(min_length=1, max_length=500)
    job_version: int = Field(strict=True, ge=1)
    payload: str
    enqueued_at: datetime
    correlation_id: str | None = Field(default=None, max_length=200)
    replay_of: UUID | None = None

    @field_validator("enqueued_at")
    @classmethod
    def local_time(cls, value: datetime) -> datetime:
        if value.tzinfo is not None:
            raise ValueError("队列时间必须为本地无时区时间")
        return value

    @field_validator("job_type")
    @classmethod
    def job_type_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("任务类路径不能为空")
        return value


class EnvelopeJsonCodec:
    """编码和校验完整消息信封，并限制传输消息大小。"""

    def __init__(self, max_bytes: int = 1_048_576) -> None:
        self.max_bytes = max_bytes

    def encode(self, message: MessageEnvelope) -> bytes:
        """把消息信封编码成后端可以直接传输的 JSON 字节。"""

        try:
            self._validate_payload(message.payload)
            # Job payload 保持原始字节语义，Base64 只负责嵌入外层 JSON。
            data = EnvelopeData(
                job_id=message.job_id,
                job_type=message.job_type,
                job_version=message.job_version,
                payload=base64.b64encode(message.payload).decode("ascii"),
                enqueued_at=message.enqueued_at,
                correlation_id=message.correlation_id,
                replay_of=message.replay_of,
            )
            raw = data.model_dump_json().encode()
            self._check_size(raw)
            return raw
        except (ValueError, TypeError) as error:
            raise InvalidMessageError("任务信封编码失败") from error

    def decode(self, raw: bytes) -> MessageEnvelope:
        """严格解码信封，拒绝未知版本、额外字段和非法 payload。"""

        try:
            self._check_size(raw)
            data = EnvelopeData.model_validate_json(raw)
            payload = base64.b64decode(data.payload, validate=True)
            self._validate_payload(payload)
            return MessageEnvelope(
                data.job_id,
                data.job_type,
                data.job_version,
                payload,
                data.enqueued_at,
                data.correlation_id,
                data.replay_of,
            )
        except (ValidationError, ValueError, TypeError, RecursionError) as error:
            raise InvalidMessageError("任务信封解码失败") from error

    def _check_size(self, raw: bytes) -> None:
        if len(raw) > self.max_bytes:
            raise InvalidMessageError("任务信封超过大小限制")

    @staticmethod
    def _validate_payload(payload: bytes) -> None:
        """确保业务 payload 是标准 JSON，不接受 NaN 和 Infinity。"""

        def reject_constant(value: str) -> None:
            raise ValueError(f"非法 JSON 常量: {value}")

        json.loads(payload, parse_constant=reject_constant)
