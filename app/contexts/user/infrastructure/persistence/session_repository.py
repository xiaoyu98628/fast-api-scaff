from uuid import UUID

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.contexts.user.domain.session import UserSession
from app.contexts.user.domain.values import UserId
from app.contexts.user.infrastructure.persistence.models.session import UserSessionModel


class SqlAlchemySessionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def find(self, token_digest: str) -> UserSession | None:
        model = await self._session.get(UserSessionModel, token_digest)
        if model is None:
            return None
        return UserSession(
            token_digest=model.token_digest,
            user_id=UserId(UUID(model.user_id)),
            issued_at=model.issued_at,
            expires_at=model.expires_at,
        )

    async def add(self, session: UserSession) -> None:
        self._session.add(
            UserSessionModel(
                token_digest=session.token_digest,
                user_id=str(session.user_id.value),
                issued_at=session.issued_at,
                expires_at=session.expires_at,
            )
        )

    async def remove(self, token_digest: str) -> None:
        await self._session.execute(delete(UserSessionModel).where(UserSessionModel.token_digest == token_digest))
