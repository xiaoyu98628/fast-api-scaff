from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


@dataclass(frozen=True, slots=True)
class MessageEnvelope:
    job_id: UUID
    job_type: str
    job_version: int
    payload: bytes
    enqueued_at: datetime
    correlation_id: str | None = None
    replay_of: UUID | None = None
