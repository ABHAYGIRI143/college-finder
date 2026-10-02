"""initial empty schema

Revision ID: 7940ea356979
Revises: 
Create Date: 2026-09-30 16:16:34.227301

"""
from typing import Sequence, Union

# revision identifiers, used by Alembic.
revision: str = '7940ea356979'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
