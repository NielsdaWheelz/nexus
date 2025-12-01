"""Make embedding_model nullable in content_chunks for PR 6.2 chunking

Revision ID: 9a3b7d2c1e5f
Revises: 828847eeffa7
Create Date: 2025-12-01 10:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "9a3b7d2c1e5f"
down_revision: Union[str, Sequence[str], None] = "828847eeffa7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema: make embedding_model nullable in content_chunks."""
    op.alter_column(
        "content_chunks",
        "embedding_model",
        existing_type=sa.String(length=100),
        nullable=True,
    )


def downgrade() -> None:
    """Downgrade schema: make embedding_model NOT NULL in content_chunks."""
    op.alter_column(
        "content_chunks",
        "embedding_model",
        existing_type=sa.String(length=100),
        nullable=False,
    )
