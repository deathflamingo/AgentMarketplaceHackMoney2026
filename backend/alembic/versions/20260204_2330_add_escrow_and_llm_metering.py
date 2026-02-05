"""Add escrow balances, token pricing, and LLM metering tables.

Revision ID: 20260204_2330
Revises: 17636626f0c7
Create Date: 2026-02-04 23:30:00
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20260204_2330"
down_revision = "17636626f0c7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Agents: add escrow balance
    op.add_column("agents", sa.Column("escrow_balance", sa.Numeric(20, 8), nullable=False, server_default="0"))

    # Services: add token pricing fields
    op.add_column("services", sa.Column("price_per_1k_tokens_usd", sa.Numeric(10, 4), nullable=False, server_default="0"))
    op.add_column("services", sa.Column("worker_min_payout_usd", sa.Numeric(10, 2), nullable=False, server_default="0"))
    op.add_column("services", sa.Column("avg_tokens_per_job", sa.Integer(), nullable=False, server_default="0"))

    # Jobs: add escrow + usage fields
    op.add_column("jobs", sa.Column("price_per_1k_tokens_usd", sa.Numeric(10, 4), nullable=False, server_default="0"))
    op.add_column("jobs", sa.Column("worker_min_payout_usd", sa.Numeric(10, 2), nullable=False, server_default="0"))
    op.add_column("jobs", sa.Column("client_max_budget_usd", sa.Numeric(12, 2), nullable=False, server_default="0"))
    op.add_column("jobs", sa.Column("avg_tokens_per_job", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("jobs", sa.Column("escrow_status", sa.String(20), nullable=False, server_default="unfunded"))
    op.add_column("jobs", sa.Column("escrow_amount_usd", sa.Numeric(12, 2), nullable=False, server_default="0"))
    op.add_column("jobs", sa.Column("escrowed_at", sa.TIMESTAMP(), nullable=True))
    op.add_column("jobs", sa.Column("released_at", sa.TIMESTAMP(), nullable=True))
    op.add_column("jobs", sa.Column("refunded_at", sa.TIMESTAMP(), nullable=True))
    op.add_column("jobs", sa.Column("usage_prompt_tokens", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("jobs", sa.Column("usage_completion_tokens", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("jobs", sa.Column("usage_total_tokens", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("jobs", sa.Column("usage_cost_usd", sa.Numeric(12, 4), nullable=False, server_default="0"))
    op.add_column("jobs", sa.Column("settlement_amount_usd", sa.Numeric(12, 2), nullable=False, server_default="0"))
    op.create_index("ix_jobs_escrow_status", "jobs", ["escrow_status"])

    # LLM provider credentials
    op.create_table(
        "llm_provider_credentials",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("agent_id", sa.String(36), sa.ForeignKey("agents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("provider", sa.Enum("openai", "anthropic", name="llmprovider"), nullable=False),
        sa.Column("encrypted_api_key", sa.Text(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.TIMESTAMP(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("last_used_at", sa.TIMESTAMP(), nullable=True),
    )
    op.create_index("ix_llm_provider_credentials_agent_id", "llm_provider_credentials", ["agent_id"])
    op.create_index("ix_llm_provider_credentials_provider", "llm_provider_credentials", ["provider"])
    op.create_index("ix_llm_provider_credentials_is_active", "llm_provider_credentials", ["is_active"])

    # LLM usage events
    op.create_table(
        "llm_usage_events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("job_id", sa.String(36), sa.ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("worker_agent_id", sa.String(36), sa.ForeignKey("agents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("provider", sa.Enum("openai", "anthropic", name="llmprovider"), nullable=False),
        sa.Column("model", sa.String(100), nullable=False),
        sa.Column("prompt_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("completion_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("cost_usd", sa.Numeric(12, 4), nullable=False, server_default="0"),
        sa.Column("status", sa.String(20), nullable=False, server_default="success"),
        sa.Column("provider_request_id", sa.String(128), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    op.create_index("ix_llm_usage_events_job_id", "llm_usage_events", ["job_id"])
    op.create_index("ix_llm_usage_events_worker_agent_id", "llm_usage_events", ["worker_agent_id"])
    op.create_index("ix_llm_usage_events_provider", "llm_usage_events", ["provider"])
    op.create_index("ix_llm_usage_events_created_at", "llm_usage_events", ["created_at"])

    # Internal ledger transactions
    op.create_table(
        "ledger_transactions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("job_id", sa.String(36), nullable=False),
        sa.Column("agent_id", sa.String(36), nullable=False),
        sa.Column("counterparty_agent_id", sa.String(36), nullable=True),
        sa.Column("amount", sa.Numeric(20, 8), nullable=False),
        sa.Column("currency", sa.String(10), nullable=False, server_default="USDC"),
        sa.Column("transaction_type", sa.Enum("escrow_lock", "escrow_release", "escrow_refund", name="ledgertransactiontype"), nullable=False),
        sa.Column("transaction_metadata", sa.Text(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    op.create_index("ix_ledger_transactions_job_id", "ledger_transactions", ["job_id"])
    op.create_index("ix_ledger_transactions_agent_id", "ledger_transactions", ["agent_id"])
    op.create_index("ix_ledger_transactions_counterparty_agent_id", "ledger_transactions", ["counterparty_agent_id"])
    op.create_index("ix_ledger_transactions_transaction_type", "ledger_transactions", ["transaction_type"])


def downgrade() -> None:
    op.drop_index("ix_ledger_transactions_transaction_type", table_name="ledger_transactions")
    op.drop_index("ix_ledger_transactions_counterparty_agent_id", table_name="ledger_transactions")
    op.drop_index("ix_ledger_transactions_agent_id", table_name="ledger_transactions")
    op.drop_index("ix_ledger_transactions_job_id", table_name="ledger_transactions")
    op.drop_table("ledger_transactions")

    op.drop_index("ix_llm_usage_events_created_at", table_name="llm_usage_events")
    op.drop_index("ix_llm_usage_events_provider", table_name="llm_usage_events")
    op.drop_index("ix_llm_usage_events_worker_agent_id", table_name="llm_usage_events")
    op.drop_index("ix_llm_usage_events_job_id", table_name="llm_usage_events")
    op.drop_table("llm_usage_events")

    op.drop_index("ix_llm_provider_credentials_is_active", table_name="llm_provider_credentials")
    op.drop_index("ix_llm_provider_credentials_provider", table_name="llm_provider_credentials")
    op.drop_index("ix_llm_provider_credentials_agent_id", table_name="llm_provider_credentials")
    op.drop_table("llm_provider_credentials")

    op.drop_index("ix_jobs_escrow_status", table_name="jobs")
    op.drop_column("jobs", "settlement_amount_usd")
    op.drop_column("jobs", "usage_cost_usd")
    op.drop_column("jobs", "usage_total_tokens")
    op.drop_column("jobs", "usage_completion_tokens")
    op.drop_column("jobs", "usage_prompt_tokens")
    op.drop_column("jobs", "refunded_at")
    op.drop_column("jobs", "released_at")
    op.drop_column("jobs", "escrowed_at")
    op.drop_column("jobs", "escrow_amount_usd")
    op.drop_column("jobs", "escrow_status")
    op.drop_column("jobs", "avg_tokens_per_job")
    op.drop_column("jobs", "client_max_budget_usd")
    op.drop_column("jobs", "worker_min_payout_usd")
    op.drop_column("jobs", "price_per_1k_tokens_usd")

    op.drop_column("services", "avg_tokens_per_job")
    op.drop_column("services", "worker_min_payout_usd")
    op.drop_column("services", "price_per_1k_tokens_usd")

    op.drop_column("agents", "escrow_balance")

    # SQLite doesn't support DROP TYPE; enums are inlined.
    bind = op.get_bind()
    if bind.dialect.name != "sqlite":
        op.execute("DROP TYPE IF EXISTS llmprovider")
        op.execute("DROP TYPE IF EXISTS ledgertransactiontype")
