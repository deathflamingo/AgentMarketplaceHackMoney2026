"""add_payment_transactions_table

Revision ID: 17636626f0c7
Revises: 1a2b3c4d5e6f
Create Date: 2026-02-04 22:18:47.847975

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '17636626f0c7'
down_revision: Union[str, None] = '1a2b3c4d5e6f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create payment_transactions table."""
    op.create_table(
        'payment_transactions',
        sa.Column('id', sa.String(36), primary_key=True, nullable=False),
        sa.Column('tx_hash', sa.String(66), unique=True, nullable=False, index=True),
        sa.Column('amount', sa.Numeric(20, 8), nullable=False),
        sa.Column('currency', sa.String(10), nullable=False, server_default='USDC'),
        sa.Column('transaction_type', sa.String(20), nullable=False, server_default='top_up'),
        sa.Column('status', sa.String(20), nullable=False, server_default='pending', index=True),
        sa.Column('initiator_agent_id', sa.String(36), nullable=False, index=True),
        sa.Column('recipient_agent_id', sa.String(36), nullable=True, index=True),
        sa.Column('from_address', sa.String(42), nullable=True),
        sa.Column('to_address', sa.String(42), nullable=False),
        sa.Column('token_address', sa.String(42), nullable=False),
        sa.Column('block_number', sa.Integer, nullable=True),
        sa.Column('transaction_metadata', sa.Text, nullable=True),
        sa.Column('failure_reason', sa.Text, nullable=True),
        sa.Column('created_at', sa.TIMESTAMP, nullable=False, server_default=sa.text('CURRENT_TIMESTAMP'), index=True),
        sa.Column('verified_at', sa.TIMESTAMP, nullable=True),
        sa.Column('credited_at', sa.TIMESTAMP, nullable=True),
    )


def downgrade() -> None:
    """Drop payment_transactions table."""
    op.drop_table('payment_transactions')
