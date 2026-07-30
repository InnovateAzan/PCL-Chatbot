"""phase2 to phase5 support tables

Revision ID: 20260730_0002
Revises: 20260730_0001
Create Date: 2026-07-30
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "20260730_0002"
down_revision: str | None = "20260730_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "message_sources",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("assistant_message_id", sa.BigInteger(), nullable=False),
        sa.Column("document_name", sa.String(length=500), nullable=False),
        sa.Column("section_name", sa.String(length=500), nullable=True),
        sa.Column("page_number", sa.Integer(), nullable=True),
        sa.Column("chunk_id", sa.String(length=255), nullable=True),
        sa.Column("similarity_score", sa.Float(), nullable=True),
        sa.Column("source_order", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["assistant_message_id"],
            ["chat_messages.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_message_sources_assistant_message_id",
        "message_sources",
        ["assistant_message_id"],
    )

    op.create_table(
        "message_feedback",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("assistant_message_id", sa.BigInteger(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("rating", sa.Integer(), nullable=True),
        sa.Column("feedback_type", sa.String(length=30), nullable=False),
        sa.Column("comments", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "rating IS NULL OR rating BETWEEN 1 AND 5",
            name="ck_message_feedback_rating",
        ),
        sa.CheckConstraint(
            "feedback_type IN "
            "('HELPFUL', 'NOT_HELPFUL', 'INCORRECT', 'INCOMPLETE', "
            "'WRONG_POLICY', 'OTHER')",
            name="ck_message_feedback_type",
        ),
        sa.ForeignKeyConstraint(
            ["assistant_message_id"],
            ["chat_messages.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["chatbot_users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "assistant_message_id",
            "user_id",
            name="uq_message_feedback_message_user",
        ),
    )
    op.create_index(
        "ix_message_feedback_assistant_message_id",
        "message_feedback",
        ["assistant_message_id"],
    )
    op.create_index("ix_message_feedback_user_id", "message_feedback", ["user_id"])

    op.create_table(
        "unanswered_questions",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("user_message_id", sa.BigInteger(), nullable=False),
        sa.Column("normalized_question", sa.String(length=1000), nullable=False),
        sa.Column("detected_topic", sa.String(length=255), nullable=True),
        sa.Column("occurrence_count", sa.Integer(), server_default="1", nullable=False),
        sa.Column(
            "review_status",
            sa.String(length=20),
            server_default="PENDING",
            nullable=False,
        ),
        sa.Column("reviewed_by", sa.String(length=255), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("improvement_notes", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "review_status IN ('PENDING', 'REVIEWED', 'RESOLVED', 'IGNORED')",
            name="ck_unanswered_questions_review_status",
        ),
        sa.ForeignKeyConstraint(
            ["user_message_id"],
            ["chat_messages.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "normalized_question",
            name="uq_unanswered_questions_normalized_question",
        ),
    )
    op.create_index(
        "ix_unanswered_questions_review_status",
        "unanswered_questions",
        ["review_status"],
    )
    op.create_index(
        "ix_unanswered_questions_created_at",
        "unanswered_questions",
        ["created_at"],
    )

    op.create_table(
        "audit_logs",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=True),
        sa.Column("action", sa.String(length=100), nullable=False),
        sa.Column("resource_type", sa.String(length=100), nullable=False),
        sa.Column("resource_id", sa.String(length=255), nullable=True),
        sa.Column("result", sa.String(length=50), nullable=False),
        sa.Column("ip_address", sa.String(length=100), nullable=True),
        sa.Column("user_agent", sa.String(length=500), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["chatbot_users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_audit_logs_user_id", "audit_logs", ["user_id"])
    op.create_index("ix_audit_logs_created_at", "audit_logs", ["created_at"])
    op.create_index("ix_audit_logs_action", "audit_logs", ["action"])


def downgrade() -> None:
    op.drop_index("ix_audit_logs_action", table_name="audit_logs")
    op.drop_index("ix_audit_logs_created_at", table_name="audit_logs")
    op.drop_index("ix_audit_logs_user_id", table_name="audit_logs")
    op.drop_table("audit_logs")
    op.drop_index("ix_unanswered_questions_created_at", table_name="unanswered_questions")
    op.drop_index("ix_unanswered_questions_review_status", table_name="unanswered_questions")
    op.drop_table("unanswered_questions")
    op.drop_index("ix_message_feedback_user_id", table_name="message_feedback")
    op.drop_index(
        "ix_message_feedback_assistant_message_id",
        table_name="message_feedback",
    )
    op.drop_table("message_feedback")
    op.drop_index(
        "ix_message_sources_assistant_message_id",
        table_name="message_sources",
    )
    op.drop_table("message_sources")
