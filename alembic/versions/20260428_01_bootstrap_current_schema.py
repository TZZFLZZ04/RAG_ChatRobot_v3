"""Bootstrap current schema and migrate legacy ownership fields."""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision = "20260428_01"
down_revision = None
branch_labels = None
depends_on = None


def _has_table(inspector: sa.Inspector, table_name: str) -> bool:
    return table_name in inspector.get_table_names()


def _has_column(inspector: sa.Inspector, table_name: str, column_name: str) -> bool:
    return column_name in {item["name"] for item in inspector.get_columns(table_name)}


def _has_index(inspector: sa.Inspector, table_name: str, index_name: str) -> bool:
    return index_name in {item["name"] for item in inspector.get_indexes(table_name)}


def _has_unique_constraint(
    inspector: sa.Inspector,
    table_name: str,
    *,
    constraint_name: str | None = None,
    columns: Sequence[str] | None = None,
) -> bool:
    for item in inspector.get_unique_constraints(table_name):
        if constraint_name and item.get("name") != constraint_name:
            continue
        if columns and tuple(item.get("column_names") or []) != tuple(columns):
            continue
        return True
    return False


def _has_foreign_key(
    inspector: sa.Inspector,
    table_name: str,
    *,
    columns: Sequence[str],
    referred_table: str,
) -> bool:
    for item in inspector.get_foreign_keys(table_name):
        if tuple(item.get("constrained_columns") or []) != tuple(columns):
            continue
        if item.get("referred_table") != referred_table:
            continue
        return True
    return False


def _ensure_index(table_name: str, index_name: str, columns: list[str], *, unique: bool = False) -> None:
    inspector = sa.inspect(op.get_bind())
    if not _has_index(inspector, table_name, index_name):
        op.create_index(index_name, table_name, columns, unique=unique)


def _create_users_table() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("username", sa.String(length=50), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("hashed_password", sa.String(length=255), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_users_username", "users", ["username"], unique=True)
    op.create_index("ix_users_email", "users", ["email"], unique=True)


def _create_collections_table() -> None:
    op.create_table(
        "collections",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("owner_id", sa.String(length=36), nullable=True),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("vector_backend", sa.String(length=50), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("owner_id", "name", name="uq_collections_owner_name"),
    )
    op.create_index("ix_collections_owner_id", "collections", ["owner_id"], unique=False)
    op.create_index("ix_collections_name", "collections", ["name"], unique=False)


def _create_documents_table() -> None:
    op.create_table(
        "documents",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("owner_id", sa.String(length=36), nullable=True),
        sa.Column("collection_id", sa.String(length=36), nullable=False),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("file_path", sa.Text(), nullable=False),
        sa.Column("file_type", sa.String(length=20), nullable=False),
        sa.Column("file_size", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("chunk_count", sa.Integer(), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["collection_id"], ["collections.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_documents_owner_id", "documents", ["owner_id"], unique=False)
    op.create_index("ix_documents_collection_id", "documents", ["collection_id"], unique=False)
    op.create_index("ix_documents_status", "documents", ["status"], unique=False)


def _create_conversations_table() -> None:
    op.create_table(
        "conversations",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("owner_id", sa.String(length=36), nullable=True),
        sa.Column("collection_id", sa.String(length=36), nullable=False),
        sa.Column("title", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["collection_id"], ["collections.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_conversations_owner_id", "conversations", ["owner_id"], unique=False)
    op.create_index("ix_conversations_collection_id", "conversations", ["collection_id"], unique=False)


def _create_messages_table() -> None:
    op.create_table(
        "messages",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("conversation_id", sa.String(length=36), nullable=False),
        sa.Column("role", sa.String(length=20), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("sources", sa.JSON(), nullable=False),
        sa.Column("token_usage", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["conversation_id"], ["conversations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_messages_conversation_id", "messages", ["conversation_id"], unique=False)
    op.create_index("ix_messages_role", "messages", ["role"], unique=False)


def _ensure_owner_column(
    table_name: str,
    *,
    index_name: str,
    fk_name: str,
) -> None:
    inspector = sa.inspect(op.get_bind())
    if not _has_column(inspector, table_name, "owner_id"):
        op.add_column(table_name, sa.Column("owner_id", sa.String(length=36), nullable=True))
        inspector = sa.inspect(op.get_bind())

    if not _has_index(inspector, table_name, index_name):
        op.create_index(index_name, table_name, ["owner_id"], unique=False)
        inspector = sa.inspect(op.get_bind())

    if not _has_foreign_key(inspector, table_name, columns=["owner_id"], referred_table="users"):
        op.create_foreign_key(fk_name, table_name, "users", ["owner_id"], ["id"], ondelete="SET NULL")


def _ensure_collection_name_scope() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    legacy_constraint_names = [
        item["name"]
        for item in inspector.get_unique_constraints("collections")
        if tuple(item.get("column_names") or []) == ("name",) and item.get("name")
    ]
    legacy_index_names = [
        item["name"]
        for item in inspector.get_indexes("collections")
        if item.get("unique") and tuple(item.get("column_names") or []) == ("name",)
    ]

    for constraint_name in legacy_constraint_names:
        op.drop_constraint(constraint_name, "collections", type_="unique")

    for index_name in legacy_index_names:
        op.drop_index(index_name, table_name="collections")

    inspector = sa.inspect(bind)
    if not _has_unique_constraint(
        inspector,
        "collections",
        constraint_name="uq_collections_owner_name",
        columns=["owner_id", "name"],
    ):
        op.create_unique_constraint("uq_collections_owner_name", "collections", ["owner_id", "name"])

    _ensure_index("collections", "ix_collections_name", ["name"])


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())

    if not _has_table(inspector, "users"):
        _create_users_table()
    else:
        _ensure_index("users", "ix_users_username", ["username"], unique=True)
        _ensure_index("users", "ix_users_email", ["email"], unique=True)

    inspector = sa.inspect(op.get_bind())
    if not _has_table(inspector, "collections"):
        _create_collections_table()
    else:
        _ensure_owner_column(
            "collections",
            index_name="ix_collections_owner_id",
            fk_name="fk_collections_owner_id_users",
        )
        _ensure_collection_name_scope()

    inspector = sa.inspect(op.get_bind())
    if not _has_table(inspector, "documents"):
        _create_documents_table()
    else:
        _ensure_owner_column(
            "documents",
            index_name="ix_documents_owner_id",
            fk_name="fk_documents_owner_id_users",
        )
        _ensure_index("documents", "ix_documents_collection_id", ["collection_id"])
        _ensure_index("documents", "ix_documents_status", ["status"])

    inspector = sa.inspect(op.get_bind())
    if not _has_table(inspector, "conversations"):
        _create_conversations_table()
    else:
        _ensure_owner_column(
            "conversations",
            index_name="ix_conversations_owner_id",
            fk_name="fk_conversations_owner_id_users",
        )
        _ensure_index("conversations", "ix_conversations_collection_id", ["collection_id"])

    inspector = sa.inspect(op.get_bind())
    if not _has_table(inspector, "messages"):
        _create_messages_table()
    else:
        _ensure_index("messages", "ix_messages_conversation_id", ["conversation_id"])
        _ensure_index("messages", "ix_messages_role", ["role"])


def downgrade() -> None:
    raise NotImplementedError("Downgrade is not supported for the bootstrap schema migration.")
