"""Alembic env. Owns volley_domain.models' and volley_domain.ontology's
tables -- never Better Auth's own tables (see CLAUDE.md's auth ownership
rule). Uses a sync psycopg driver for migrations even though the app runs
asyncpg at request time; that's a normal, deliberate split (Alembic's
autogenerate/offline tooling assumes sync).
"""

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool
from volley_api.core.config import get_settings

# Importing volley_domain (not just volley_domain.models) registers every
# table -- both models.py and ontology.py -- on the shared Base before
# target_metadata is read below. See volley_domain/__init__.py's docstring.
from volley_domain import Base

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

_MANAGED_TABLE_NAMES = frozenset(target_metadata.tables.keys())


def include_object(object, name, type_, reflected, compare_to) -> bool:
    """Excludes Better Auth's own tables (user/session/account/organization/
    member/invitation/verification/jwks) from autogenerate/`alembic check`
    comparisons. Without this, every check against a database where Better
    Auth's own migrations have already run reports every one of its tables
    as spurious drift (`reflected=True` and `compare_to=None` since they
    were never registered on `target_metadata`) -- noise that would mask a
    genuine drift signal in real volley_domain tables the day one actually
    appears. Never filters anything this project's own Base.metadata does
    know about, so a real gap in an owned table still surfaces normally."""
    return not (
        type_ == "table" and reflected and compare_to is None and name not in _MANAGED_TABLE_NAMES
    )


def _sync_url() -> str:
    url = get_settings().database_url
    if url.startswith("postgresql+asyncpg://"):
        return url.replace("postgresql+asyncpg://", "postgresql+psycopg://", 1)
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+psycopg://", 1)
    return url


config.set_main_option("sqlalchemy.url", _sync_url())


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        include_object=include_object,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection, target_metadata=target_metadata, include_object=include_object
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
