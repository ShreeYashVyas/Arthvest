"""Add local development watchlists and ordered entries.

Revision ID: 0002_local_watchlists
Revises: 0001_additive_schema_baseline
Create Date: 2026-10-30
"""

from alembic import op

from app.services.market_store import MarketWatchlistEntryRecord, MarketWatchlistRecord


revision = "0002_local_watchlists"
down_revision = "0001_additive_schema_baseline"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    MarketWatchlistRecord.__table__.create(bind=bind, checkfirst=True)
    MarketWatchlistEntryRecord.__table__.create(bind=bind, checkfirst=True)


def downgrade() -> None:
    raise RuntimeError("Watchlist migration is intentionally non-destructive")
