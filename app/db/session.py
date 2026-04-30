from __future__ import annotations

from functools import lru_cache

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker

from app.core.config import get_settings
from app.db.base import Base
from app.db.models import collection, conversation, document, message, user  # noqa: F401


def _engine_kwargs(database_url: str) -> dict:
    if database_url.startswith("sqlite"):
        return {"connect_args": {"check_same_thread": False}}
    return {"pool_pre_ping": True}


@lru_cache
def get_engine() -> Engine:
    settings = get_settings()
    return create_engine(
        settings.sqlalchemy_database_uri,
        future=True,
        **_engine_kwargs(settings.sqlalchemy_database_uri),
    )


@lru_cache
def get_session_factory() -> sessionmaker:
    return sessionmaker(
        bind=get_engine(),
        autoflush=False,
        autocommit=False,
        expire_on_commit=False,
    )


def init_db() -> None:
    engine = get_engine()
    Base.metadata.create_all(bind=engine)
    _ensure_auth_columns(engine)
    _ensure_collection_name_scope(engine)


def _ensure_auth_columns(engine: Engine) -> None:
    inspector = inspect(engine)
    statements: list[str] = []

    collection_columns = {item["name"] for item in inspector.get_columns("collections")}
    if "owner_id" not in collection_columns:
        statements.append("ALTER TABLE collections ADD COLUMN owner_id VARCHAR(36)")

    document_columns = {item["name"] for item in inspector.get_columns("documents")}
    if "owner_id" not in document_columns:
        statements.append("ALTER TABLE documents ADD COLUMN owner_id VARCHAR(36)")

    conversation_columns = {item["name"] for item in inspector.get_columns("conversations")}
    if "owner_id" not in conversation_columns:
        statements.append("ALTER TABLE conversations ADD COLUMN owner_id VARCHAR(36)")

    if not statements:
        return

    with engine.begin() as connection:
        for statement in statements:
            connection.execute(text(statement))


def _ensure_collection_name_scope(engine: Engine) -> None:
    if engine.dialect.name != "postgresql":
        return

    inspector = inspect(engine)
    unique_constraints = inspector.get_unique_constraints("collections")

    has_owner_scoped_unique = False
    legacy_constraint_names: list[str] = []
    for constraint in unique_constraints:
        columns = constraint.get("column_names") or []
        if columns == ["owner_id", "name"]:
            has_owner_scoped_unique = True
        elif columns == ["name"] and constraint.get("name"):
            legacy_constraint_names.append(constraint["name"])

    if has_owner_scoped_unique and not legacy_constraint_names:
        return

    with engine.begin() as connection:
        for constraint_name in legacy_constraint_names:
            connection.execute(
                text(f'ALTER TABLE collections DROP CONSTRAINT IF EXISTS "{constraint_name}"')
            )
        if not has_owner_scoped_unique:
            connection.execute(
                text(
                    "ALTER TABLE collections "
                    "ADD CONSTRAINT uq_collections_owner_name UNIQUE (owner_id, name)"
                )
            )
