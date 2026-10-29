"""Alembic environment for additive Arthvest schema migrations."""

from alembic import context

from app.services.observation_store import Base
from app.services import market_store  # noqa: F401 - load all model metadata


config = context.config
target_metadata = Base.metadata


def run_migrations_online() -> None:
    connection = config.attributes.get("connection")
    if connection is None:
        raise RuntimeError("A managed SQLAlchemy connection is required for migrations")
    context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()


run_migrations_online()
