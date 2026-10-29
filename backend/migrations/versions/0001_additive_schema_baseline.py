"""Create any missing Arthvest tables without replacing existing data.

Revision ID: 0001_additive_schema_baseline
Revises:
Create Date: 2026-10-30
"""

from alembic import op

from app.services.observation_store import Base
from app.services import market_store  # noqa: F401 - register market models


revision = "0001_additive_schema_baseline"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Adoption migration: checkfirst creates missing tables and preserves existing tables/rows.
    initial_tables = [
        table for table in Base.metadata.sorted_tables
        if table.name not in {"market_watchlists", "market_watchlist_entries"}
    ]
    Base.metadata.create_all(bind=op.get_bind(), tables=initial_tables, checkfirst=True)


def downgrade() -> None:
    raise RuntimeError("The baseline migration is intentionally non-destructive and cannot be downgraded")
