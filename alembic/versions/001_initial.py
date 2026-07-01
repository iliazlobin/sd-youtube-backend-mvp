"""001_initial — create videos, view_events, window_aggregates tables.

Revision ID: 001
Revises: None
Create Date: 2026-06-30
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "videos",
        sa.Column("video_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("category", sa.String(255), nullable=True),
        sa.Column("region", sa.String(100), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("video_id"),
    )
    op.create_index("ix_videos_created_at", "videos", ["created_at"])

    op.create_table(
        "view_events",
        sa.Column("event_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("video_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("viewer_id", sa.Text(), nullable=False),
        sa.Column("event_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("event_id"),
        sa.ForeignKeyConstraint(["video_id"], ["videos.video_id"]),
        sa.UniqueConstraint("event_id"),
    )
    op.create_index("ix_view_events_video_event_time", "view_events", ["video_id", "event_time"])

    op.create_table(
        "window_aggregates",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("video_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("window_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("window_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("view_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["video_id"], ["videos.video_id"]),
        sa.UniqueConstraint("video_id", "window_start"),
    )
    op.create_index(
        "ix_window_aggregates_start_count",
        "window_aggregates",
        ["window_start", sa.text("view_count DESC")],
    )


def downgrade() -> None:
    op.drop_table("window_aggregates")
    op.drop_table("view_events")
    op.drop_table("videos")
