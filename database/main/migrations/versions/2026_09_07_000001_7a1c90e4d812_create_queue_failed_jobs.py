"""Create queue failed job storage."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.mysql import LONGBLOB

revision: str = "7a1c90e4d812"
down_revision: str | Sequence[str] | None = "4c7ca5ba7a1d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "queue_failed_jobs",
        sa.Column("failure_id", sa.String(36), nullable=False),
        sa.Column("job_id", sa.String(36), nullable=True),
        sa.Column("payload", sa.LargeBinary().with_variant(LONGBLOB(), "mysql"), nullable=False),
        sa.Column("connection", sa.String(200), nullable=False),
        sa.Column("queue", sa.String(200), nullable=False),
        sa.Column("failed_at", sa.DateTime(), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("reason", sa.String(200), nullable=False),
        sa.PrimaryKeyConstraint("failure_id", name=op.f("pk_queue_failed_jobs")),
    )
    op.create_index(op.f("ix_queue_failed_jobs_failed_at"), "queue_failed_jobs", ["failed_at"])


def downgrade() -> None:
    op.drop_table("queue_failed_jobs")
