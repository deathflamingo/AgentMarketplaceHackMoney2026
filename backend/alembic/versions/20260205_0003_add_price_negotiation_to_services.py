"""add price negotiation to services

Revision ID: 4a5b6c7d8e9f
Revises: 3a4b5c6d7e8f
Create Date: 2026-02-05 00:03:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import text
from decimal import Decimal

# revision identifiers, used by Alembic.
revision = '4a5b6c7d8e9f'
down_revision = '3a4b5c6d7e8f'
branch_labels = None
depends_on = None

# Conversion rate: 1 USDC = 10,000 AGNT
CONVERSION_RATE = Decimal("10000")
# Default price range: ±10% from base price
PRICE_RANGE_FACTOR = Decimal("0.1")


def upgrade() -> None:
    # Add new columns for price negotiation
    op.add_column('services',
        sa.Column('min_price_agnt', sa.Numeric(20, 8), nullable=True))
    op.add_column('services',
        sa.Column('max_price_agnt', sa.Numeric(20, 8), nullable=True))
    op.add_column('services',
        sa.Column('allow_negotiation', sa.Boolean(), server_default='1', nullable=False))

    # Get connection for data migration
    connection = op.get_bind()

    # Fetch all services with their current USD prices
    result = connection.execute(text(
        "SELECT id, price_usd FROM services"
    ))
    services = result.fetchall()

    # Convert each service price to AGNT with a range
    for service in services:
        service_id, price_usd = service

        # Convert to AGNT base price
        base_price_agnt = Decimal(str(price_usd)) * CONVERSION_RATE

        # Set range: -10% to +10% of base price
        min_price = base_price_agnt * (Decimal("1") - PRICE_RANGE_FACTOR)
        max_price = base_price_agnt * (Decimal("1") + PRICE_RANGE_FACTOR)

        # Update service with AGNT price range
        connection.execute(text(
            """
            UPDATE services
            SET min_price_agnt = :min_price,
                max_price_agnt = :max_price,
                allow_negotiation = 1
            WHERE id = :service_id
            """
        ), {
            'min_price': float(min_price),
            'max_price': float(max_price),
            'service_id': service_id
        })

    connection.commit()

    # Note: SQLite doesn't support ALTER COLUMN for NOT NULL constraint
    # Since we've populated all existing rows, new services will be required
    # to have these fields by the Service model definition

    # Drop old price_usd column (after migration complete)
    # Note: Uncomment this after verifying migration works correctly
    # op.drop_column('services', 'price_usd')

    print(f"✅ Migrated {len(services)} service prices to AGNT with negotiation ranges")
    print(f"   Base rate: 1 USDC = {CONVERSION_RATE} AGNT")
    print(f"   Price range: ±{PRICE_RANGE_FACTOR * 100}%")
    print(f"\nNote: price_usd column retained for backward compatibility.")
    print(f"      Drop manually after verification: op.drop_column('services', 'price_usd')")


def downgrade() -> None:
    # Re-add price_usd column if it was dropped
    # op.add_column('services', sa.Column('price_usd', sa.Numeric(10, 2), nullable=True))

    # Get connection
    connection = op.get_bind()

    # Convert min_price_agnt back to USD (use min as base)
    # connection.execute(text(
    #     """
    #     UPDATE services
    #     SET price_usd = min_price_agnt / :conversion_rate
    #     """
    # ), {'conversion_rate': float(CONVERSION_RATE)})

    # connection.commit()

    # Drop negotiation columns
    op.drop_column('services', 'allow_negotiation')
    op.drop_column('services', 'max_price_agnt')
    op.drop_column('services', 'min_price_agnt')

    print("✅ Reverted services to USD pricing")
