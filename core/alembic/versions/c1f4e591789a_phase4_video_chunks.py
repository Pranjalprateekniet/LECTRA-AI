"""phase4_video_chunks

Revision ID: c1f4e591789a
Revises: a3b8eb57791e
Create Date: 2026-10-31 21:15:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c1f4e591789a"
down_revision: Union[str, None] = "a3b8eb57791e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "video_chunks",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("video_id", sa.String(length=36), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("start_seconds", sa.Float(), nullable=False),
        sa.Column("end_seconds", sa.Float(), nullable=False),
        sa.Column("duration_seconds", sa.Float(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("token_count", sa.Integer(), nullable=False),
        sa.Column("source_segment_start_index", sa.Integer(), nullable=False),
        sa.Column("source_segment_end_index", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["video_id"], ["videos.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("video_id", "chunk_index", name="uq_video_chunks_video_index"),
    )
    op.create_index(
        op.f("ix_video_chunks_video_id"), "video_chunks", ["video_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_video_chunks_video_id"), table_name="video_chunks")
    op.drop_table("video_chunks")

