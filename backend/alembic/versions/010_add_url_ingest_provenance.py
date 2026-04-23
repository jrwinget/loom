"""Add URL ingestion provenance columns to assets

Nine nullable columns capture admissibility-grade provenance for
URL-sourced assets: the submitted URL, extractor-canonical URL,
source method, downloader + version, retrieval UTC, response
headers (HTTP fallback only), Wayback snapshot URL, and an
extractor-specific info blob. All are nullable so legacy
upload-sourced rows remain untouched.

Chains off 009 (correlation candidates, #55 merged 2026-04-22).

Revision ID: 010
Revises: 009
Create Date: 2026-04-22

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "010"
down_revision: Union[str, None] = "009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "assets",
        sa.Column("source_uri", sa.String(), nullable=True),
    )
    op.add_column(
        "assets",
        sa.Column(
            "source_canonical_uri",
            sa.String(),
            nullable=True,
        ),
    )
    op.add_column(
        "assets",
        sa.Column("source_method", sa.String(), nullable=True),
    )
    op.add_column(
        "assets",
        sa.Column(
            "source_downloader",
            sa.String(),
            nullable=True,
        ),
    )
    op.add_column(
        "assets",
        sa.Column(
            "source_downloader_version",
            sa.String(),
            nullable=True,
        ),
    )
    op.add_column(
        "assets",
        sa.Column(
            "source_retrieved_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )
    op.add_column(
        "assets",
        sa.Column(
            "source_response_headers",
            sa.JSON(),
            nullable=True,
        ),
    )
    op.add_column(
        "assets",
        sa.Column(
            "source_wayback_url",
            sa.String(),
            nullable=True,
        ),
    )
    op.add_column(
        "assets",
        sa.Column(
            "source_extractor_info",
            sa.JSON(),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("assets", "source_extractor_info")
    op.drop_column("assets", "source_wayback_url")
    op.drop_column("assets", "source_response_headers")
    op.drop_column("assets", "source_retrieved_at")
    op.drop_column("assets", "source_downloader_version")
    op.drop_column("assets", "source_downloader")
    op.drop_column("assets", "source_method")
    op.drop_column("assets", "source_canonical_uri")
    op.drop_column("assets", "source_uri")
