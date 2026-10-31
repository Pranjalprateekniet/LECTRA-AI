"""phase2_discovery_fields

Revision ID: 963ded7cc98d
Revises: 590122cad880
Create Date: 2026-10-31

Adds Phase 2 discovery fields:
- playlists.status / playlists.discovery_error (durable discovery job state)
- videos.availability / videos.discovery_error (explicit exception records)
- unique (playlist_id, youtube_id) on videos (stable video IDs, no duplicates)
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "963ded7cc98d"
down_revision: Union[str, None] = "590122cad880"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("playlists") as batch_op:
        batch_op.add_column(
            sa.Column(
                "status", sa.String(length=50), nullable=False, server_default="DISCOVERY_QUEUED"
            )
        )
        batch_op.add_column(sa.Column("discovery_error", sa.Text(), nullable=True))
        batch_op.create_index(batch_op.f("ix_playlists_status"), ["status"], unique=False)

    with op.batch_alter_table("videos") as batch_op:
        batch_op.add_column(sa.Column("availability", sa.String(length=100), nullable=True))
        batch_op.add_column(sa.Column("discovery_error", sa.Text(), nullable=True))
        batch_op.create_unique_constraint(
            "uq_videos_playlist_youtube_id", ["playlist_id", "youtube_id"]
        )


def downgrade() -> None:
    with op.batch_alter_table("videos") as batch_op:
        batch_op.drop_constraint("uq_videos_playlist_youtube_id", type_="unique")
        batch_op.drop_column("discovery_error")
        batch_op.drop_column("availability")

    with op.batch_alter_table("playlists") as batch_op:
        batch_op.drop_index(batch_op.f("ix_playlists_status"))
        batch_op.drop_column("discovery_error")
        batch_op.drop_column("status")
