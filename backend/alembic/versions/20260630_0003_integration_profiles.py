"""Add shared integration credential profiles."""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "20260630_0003"
down_revision = "20260630_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "integration_credential_profiles",
        sa.Column("provider_key", sa.String(length=64), nullable=False),
        sa.Column("label", sa.String(length=120), nullable=False),
        sa.Column("encrypted_credentials", sa.Text(), nullable=False),
        sa.Column("updated_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.ForeignKeyConstraint(["updated_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "provider_key",
            "label",
            name="uq_integration_credential_profiles_provider_label",
        ),
    )
    op.create_index(
        "ix_integration_credential_profiles_provider_key",
        "integration_credential_profiles",
        ["provider_key"],
    )

    op.add_column(
        "platform_integrations",
        sa.Column("credential_profile_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_index(
        "ix_platform_integrations_credential_profile_id",
        "platform_integrations",
        ["credential_profile_id"],
    )
    op.create_foreign_key(
        "fk_platform_integrations_credential_profile_id_profiles",
        "platform_integrations",
        "integration_credential_profiles",
        ["credential_profile_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_platform_integrations_credential_profile_id_profiles",
        "platform_integrations",
        type_="foreignkey",
    )
    op.drop_index(
        "ix_platform_integrations_credential_profile_id",
        table_name="platform_integrations",
    )
    op.drop_column("platform_integrations", "credential_profile_id")

    op.drop_index(
        "ix_integration_credential_profiles_provider_key",
        table_name="integration_credential_profiles",
    )
    op.drop_table("integration_credential_profiles")
