"""update jobs for agentcoin pricing

Revision ID: 5a6b7c8d9e0f
Revises: 4a5b6c7d8e9f
Create Date: 2026-02-05 00:04:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import text
from decimal import Decimal

# revision identifiers, used by Alembic.
revision = '5a6b7c8d9e0f'
down_revision = '4a5b6c7d8e9f'
branch_labels = None
depends_on = None

# Conversion rate: 1 USDC = 10,000 AGNT
CONVERSION_RATE = Decimal("10000")


def upgrade() -> None:
    # Add new AGNT price column
    op.add_column('jobs',
        sa.Column('price_agnt', sa.Numeric(20, 8), nullable=True))

    # Add negotiation tracking fields
    op.add_column('jobs',
        sa.Column('initial_price_offer', sa.Numeric(20, 8), nullable=True))
    op.add_column('jobs',
        sa.Column('final_price_agreed', sa.Numeric(20, 8), nullable=True))
    op.add_column('jobs',
        sa.Column('negotiated_by', sa.String(20), nullable=True))  # "agent"|"llm"
    op.add_column('jobs',
        sa.Column('quote_id', sa.String(36), nullable=True))  # Reference to price_quote

    # Get connection for data migration
    connection = op.get_bind()

    # Migrate existing jobs from USD to AGNT
    result = connection.execute(text(
        "SELECT id, price_usd FROM jobs"
    ))
    jobs = result.fetchall()

    for job in jobs:
        job_id, price_usd = job

        # Convert to AGNT
        price_agnt = Decimal(str(price_usd)) * CONVERSION_RATE

        # Update job with AGNT price
        connection.execute(text(
            """
            UPDATE jobs
            SET price_agnt = :price_agnt,
                final_price_agreed = :price_agnt,
                negotiated_by = 'agent'
            WHERE id = :job_id
            """
        ), {
            'price_agnt': float(price_agnt),
            'job_id': job_id
        })

    connection.commit()

    # Note: SQLite doesn't support ALTER COLUMN for NOT NULL constraint
    # Since we've populated all existing rows, new jobs will be required
    # to have these fields by the Job model definition

    # Add index on quote_id for faster lookups
    op.create_index('ix_jobs_quote_id', 'jobs', ['quote_id'])

    # Drop old price_usd column (after verification)
    # Note: Uncomment after verifying migration works correctly
    # op.drop_column('jobs', 'price_usd')

    print(f"✅ Migrated {len(jobs)} job prices to AGNT")
    print(f"   Conversion rate: 1 USDC = {CONVERSION_RATE} AGNT")
    print(f"\nNote: price_usd column retained for backward compatibility.")
    print(f"      Drop manually after verification: op.drop_column('jobs', 'price_usd')")


def downgrade() -> None:
    # Drop index
    op.drop_index('ix_jobs_quote_id', 'jobs')

    # Drop negotiation columns
    op.drop_column('jobs', 'quote_id')
    op.drop_column('jobs', 'negotiated_by')
    op.drop_column('jobs', 'final_price_agreed')
    op.drop_column('jobs', 'initial_price_offer')
    op.drop_column('jobs', 'price_agnt')

    print("✅ Reverted jobs to USD pricing")
