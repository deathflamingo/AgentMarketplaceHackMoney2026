"""add p2p negotiation tables

Revision ID: 6a7b8c9d0e1f
Revises: 5a6b7c8d9e0f
Create Date: 2026-02-06 00:01:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import sqlite

# revision identifiers, used by Alembic.
revision = '6a7b8c9d0e1f'
down_revision = '5a6b7c8d9e0f'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create negotiations table
    op.create_table(
        'negotiations',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('service_id', sa.String(36), sa.ForeignKey('services.id'), nullable=False),
        sa.Column('client_agent_id', sa.String(36), sa.ForeignKey('agents.id'), nullable=False),
        sa.Column('worker_agent_id', sa.String(36), sa.ForeignKey('agents.id'), nullable=False),
        sa.Column('job_description', sa.Text, nullable=False),
        sa.Column('status', sa.String(20), nullable=False, server_default='active'),
        sa.Column('current_price', sa.Numeric(20, 8), nullable=False),
        sa.Column('current_proposer', sa.String(10), nullable=False),
        sa.Column('service_min_price', sa.Numeric(20, 8), nullable=False),
        sa.Column('service_max_price', sa.Numeric(20, 8), nullable=False),
        sa.Column('client_max_price', sa.Numeric(20, 8), nullable=True),
        sa.Column('round_count', sa.Integer, nullable=False, server_default='0'),
        sa.Column('max_rounds', sa.Integer, nullable=False, server_default='5'),
        sa.Column('created_at', sa.TIMESTAMP, nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('expires_at', sa.TIMESTAMP, nullable=False),
        sa.Column('agreed_at', sa.TIMESTAMP, nullable=True),
    )

    # Create indexes for negotiations
    op.create_index('ix_negotiations_client_agent_id', 'negotiations', ['client_agent_id'])
    op.create_index('ix_negotiations_worker_agent_id', 'negotiations', ['worker_agent_id'])
    op.create_index('ix_negotiations_service_id', 'negotiations', ['service_id'])
    op.create_index('ix_negotiations_status', 'negotiations', ['status'])

    # Create negotiation_offers table
    op.create_table(
        'negotiation_offers',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('negotiation_id', sa.String(36), sa.ForeignKey('negotiations.id'), nullable=False),
        sa.Column('agent_id', sa.String(36), sa.ForeignKey('agents.id'), nullable=False),
        sa.Column('agent_role', sa.String(10), nullable=False),
        sa.Column('action', sa.String(20), nullable=False),
        sa.Column('price', sa.Numeric(20, 8), nullable=False),
        sa.Column('message', sa.Text, nullable=True),
        sa.Column('created_at', sa.TIMESTAMP, nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
    )

    # Create indexes for negotiation_offers
    op.create_index('ix_negotiation_offers_negotiation_id', 'negotiation_offers', ['negotiation_id'])
    op.create_index('ix_negotiation_offers_agent_id', 'negotiation_offers', ['agent_id'])

    # Add negotiation_id to jobs table
    # Note: Foreign key constraint omitted for SQLite compatibility
    # The relationship is still enforced at the ORM level
    op.add_column('jobs',
        sa.Column('negotiation_id', sa.String(36), nullable=True))

    op.create_index('ix_jobs_negotiation_id', 'jobs', ['negotiation_id'])

    print("✅ Created P2P negotiation tables")
    print("   - negotiations")
    print("   - negotiation_offers")
    print("   - Added negotiation_id to jobs")


def downgrade() -> None:
    # Drop indexes
    op.drop_index('ix_jobs_negotiation_id', 'jobs')
    op.drop_index('ix_negotiation_offers_agent_id', 'negotiation_offers')
    op.drop_index('ix_negotiation_offers_negotiation_id', 'negotiation_offers')
    op.drop_index('ix_negotiations_status', 'negotiations')
    op.drop_index('ix_negotiations_service_id', 'negotiations')
    op.drop_index('ix_negotiations_worker_agent_id', 'negotiations')
    op.drop_index('ix_negotiations_client_agent_id', 'negotiations')

    # Drop column from jobs
    op.drop_column('jobs', 'negotiation_id')

    # Drop tables
    op.drop_table('negotiation_offers')
    op.drop_table('negotiations')

    print("✅ Dropped P2P negotiation tables")
