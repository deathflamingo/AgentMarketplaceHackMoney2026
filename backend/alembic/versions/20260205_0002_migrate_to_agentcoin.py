"""migrate agent balances to agentcoin

Revision ID: 3a4b5c6d7e8f
Revises: 2a3b4c5d6e7f
Create Date: 2026-02-05 00:02:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import text
from decimal import Decimal
import uuid
from datetime import datetime

# revision identifiers, used by Alembic.
revision = '3a4b5c6d7e8f'
down_revision = '2a3b4c5d6e7f'
branch_labels = None
depends_on = None

# Conversion rate: 1 USDC = 10,000 AGNT
CONVERSION_RATE = Decimal("10000")


def upgrade() -> None:
    # Add balance_currency column to agents
    op.add_column('agents',
        sa.Column('balance_currency', sa.String(10),
                  server_default='AGNT', nullable=False))

    # Get connection for data migration
    connection = op.get_bind()

    # Fetch all agents with their current balances
    result = connection.execute(text(
        "SELECT id, balance, total_earned, total_spent FROM agents"
    ))
    agents = result.fetchall()

    # Migration batch ID
    batch_id = datetime.utcnow().strftime("%Y%m%d_%H%M%S")

    # Migrate each agent's balance
    for agent in agents:
        agent_id, old_balance, old_earned, old_spent = agent

        # Convert to AGNT (multiply by 10,000)
        new_balance = Decimal(str(old_balance)) * CONVERSION_RATE
        new_earned = Decimal(str(old_earned)) * CONVERSION_RATE
        new_spent = Decimal(str(old_spent)) * CONVERSION_RATE

        # Update agent balances
        connection.execute(text(
            """
            UPDATE agents
            SET balance = :new_balance,
                total_earned = :new_earned,
                total_spent = :new_spent,
                balance_currency = 'AGNT'
            WHERE id = :agent_id
            """
        ), {
            'new_balance': float(new_balance),
            'new_earned': float(new_earned),
            'new_spent': float(new_spent),
            'agent_id': agent_id
        })

        # Record migration in balance_migrations table
        migration_id = str(uuid.uuid4())
        connection.execute(text(
            """
            INSERT INTO balance_migrations (
                id, agent_id,
                old_balance, old_currency, old_total_earned, old_total_spent,
                new_balance, new_currency, new_total_earned, new_total_spent,
                conversion_rate, migration_batch, migrated_at
            ) VALUES (
                :id, :agent_id,
                :old_balance, 'USDC', :old_earned, :old_spent,
                :new_balance, 'AGNT', :new_earned, :new_spent,
                :conversion_rate, :batch_id, CURRENT_TIMESTAMP
            )
            """
        ), {
            'id': migration_id,
            'agent_id': agent_id,
            'old_balance': float(old_balance),
            'old_earned': float(old_earned),
            'old_spent': float(old_spent),
            'new_balance': float(new_balance),
            'new_earned': float(new_earned),
            'new_spent': float(new_spent),
            'conversion_rate': float(CONVERSION_RATE),
            'batch_id': batch_id
        })

    connection.commit()

    print(f"✅ Migrated {len(agents)} agent balances from USDC to AGNT (rate: 1 USDC = {CONVERSION_RATE} AGNT)")


def downgrade() -> None:
    # Get connection
    connection = op.get_bind()

    # Revert balances back to USDC (divide by 10,000)
    connection.execute(text(
        """
        UPDATE agents
        SET balance = balance / :conversion_rate,
            total_earned = total_earned / :conversion_rate,
            total_spent = total_spent / :conversion_rate,
            balance_currency = 'USDC'
        """
    ), {'conversion_rate': float(CONVERSION_RATE)})

    connection.commit()

    # Drop balance_currency column
    op.drop_column('agents', 'balance_currency')

    print(f"✅ Reverted agent balances back to USDC")
