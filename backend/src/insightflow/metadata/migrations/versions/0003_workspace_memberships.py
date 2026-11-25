"""Add organization-scoped workspace memberships."""

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str = "0002"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "workspace_memberships",
        sa.Column("org_id", sa.Uuid(), nullable=False),
        sa.Column("issuer", sa.String(255), nullable=False),
        sa.Column("subject", sa.String(255), nullable=False),
        sa.Column("role", sa.String(16), nullable=False),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("org_id", "issuer", "subject"),
        sa.CheckConstraint(
            "role IN ('owner','editor','viewer')", name="ck_workspace_membership_role"
        ),
    )


def downgrade() -> None:
    op.drop_table("workspace_memberships")
