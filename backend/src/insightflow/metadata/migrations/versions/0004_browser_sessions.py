"""Add revocable browser sessions."""

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: str = "0003"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "browser_sessions",
        sa.Column("token_hash", sa.String(64), primary_key=True),
        sa.Column("org_id", sa.Uuid(), nullable=False),
        sa.Column("issuer", sa.String(255), nullable=False),
        sa.Column("subject", sa.String(255), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["org_id", "issuer", "subject"],
            [
                "workspace_memberships.org_id",
                "workspace_memberships.issuer",
                "workspace_memberships.subject",
            ],
            name="fk_browser_session_membership",
            ondelete="CASCADE",
        ),
    )
    op.create_index("ix_browser_session_expiry", "browser_sessions", ["expires_at"])
    op.create_index(
        "ix_browser_session_membership", "browser_sessions", ["org_id", "issuer", "subject"]
    )


def downgrade() -> None:
    op.drop_table("browser_sessions")
