"""add agentcoin transaction and quote tables

Revision ID: 2a3b4c5d6e7f
Revises: 7a8b9c0d1e2f
Create Date: 2026-02-05 00:01:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '2a3b4c5d6e7f'
down_revision = '17636626f0c7'  # Points to add_payment_transactions_table
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create deposit_transactions table
    op.create_table(
        'deposit_transactions',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('agent_id', sa.String(36), sa.ForeignKey('agents.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('swap_tx_hash', sa.String(66), nullable=False, unique=True, index=True),
        sa.Column('usdc_amount_in', sa.Numeric(20, 8), nullable=False),
        sa.Column('agnt_amount_out', sa.Numeric(20, 8), nullable=False),
        sa.Column('exchange_rate', sa.Numeric(20, 8), nullable=False),
        sa.Column('status', sa.String(20), nullable=False, server_default='pending', index=True),
        sa.Column('created_at', sa.TIMESTAMP, nullable=False, server_default=sa.func.now()),
        sa.Column('verified_at', sa.TIMESTAMP, nullable=True),
    )

    # Create withdrawal_transactions table
    op.create_table(
        'withdrawal_transactions',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('agent_id', sa.String(36), sa.ForeignKey('agents.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('agnt_amount_in', sa.Numeric(20, 8), nullable=False),
        sa.Column('usdc_amount_out', sa.Numeric(20, 8), nullable=False),
        sa.Column('fee_agnt', sa.Numeric(20, 8), nullable=False),
        sa.Column('exchange_rate', sa.Numeric(20, 8), nullable=False),
        sa.Column('recipient_address', sa.String(42), nullable=False),
        sa.Column('swap_tx_hash', sa.String(66), nullable=True),
        sa.Column('transfer_tx_hash', sa.String(66), nullable=True),
        sa.Column('status', sa.String(20), nullable=False, server_default='pending', index=True),
        sa.Column('error_message', sa.String(500), nullable=True),
        sa.Column('created_at', sa.TIMESTAMP, nullable=False, server_default=sa.func.now()),
        sa.Column('completed_at', sa.TIMESTAMP, nullable=True),
    )

    # Create price_quotes table
    op.create_table(
        'price_quotes',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('service_id', sa.String(36), sa.ForeignKey('services.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('client_agent_id', sa.String(36), sa.ForeignKey('agents.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('job_description', sa.Text, nullable=False),
        sa.Column('max_price_willing', sa.Numeric(20, 8), nullable=False),
        sa.Column('quoted_price', sa.Numeric(20, 8), nullable=False),
        sa.Column('service_min_price', sa.Numeric(20, 8), nullable=False),
        sa.Column('service_max_price', sa.Numeric(20, 8), nullable=False),
        sa.Column('negotiation_factors', sa.Text, nullable=True),
        sa.Column('status', sa.String(20), nullable=False, server_default='pending', index=True),
        sa.Column('created_at', sa.TIMESTAMP, nullable=False, server_default=sa.func.now()),
        sa.Column('valid_until', sa.TIMESTAMP, nullable=False),
        sa.Column('accepted_at', sa.TIMESTAMP, nullable=True),
    )

    # Create balance_migrations table
    op.create_table(
        'balance_migrations',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('agent_id', sa.String(36), sa.ForeignKey('agents.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('old_balance', sa.Numeric(20, 8), nullable=False),
        sa.Column('old_currency', sa.String(10), nullable=False, server_default='USDC'),
        sa.Column('old_total_earned', sa.Numeric(20, 8), nullable=False),
        sa.Column('old_total_spent', sa.Numeric(20, 8), nullable=False),
        sa.Column('new_balance', sa.Numeric(20, 8), nullable=False),
        sa.Column('new_currency', sa.String(10), nullable=False, server_default='AGNT'),
        sa.Column('new_total_earned', sa.Numeric(20, 8), nullable=False),
        sa.Column('new_total_spent', sa.Numeric(20, 8), nullable=False),
        sa.Column('conversion_rate', sa.Numeric(20, 8), nullable=False),
        sa.Column('migrated_at', sa.TIMESTAMP, nullable=False, server_default=sa.func.now()),
        sa.Column('migration_batch', sa.String(50), nullable=True),
    )


def downgrade() -> None:
    op.drop_table('balance_migrations')
    op.drop_table('price_quotes')
    op.drop_table('withdrawal_transactions')
    op.drop_table('deposit_transactions')
