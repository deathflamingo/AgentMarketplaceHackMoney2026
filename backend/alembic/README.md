# Alembic Database Migrations

## Setup

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Set up your database URL in `.env`:
```bash
DATABASE_URL=postgresql+asyncpg://postgres:password@localhost:5432/agentmarket
```

## Creating Migrations

### Auto-generate migration from model changes:
```bash
alembic revision --autogenerate -m "Description of changes"
```

### Create empty migration:
```bash
alembic revision -m "Description of changes"
```

## Running Migrations

### Upgrade to latest version:
```bash
alembic upgrade head
```

### Upgrade by one version:
```bash
alembic upgrade +1
```

### Downgrade by one version:
```bash
alembic downgrade -1
```

### Show current version:
```bash
alembic current
```

### Show migration history:
```bash
alembic history
```

## Initial Migration

The initial migration will create all 6 tables:
- agents
- services
- jobs
- deliverables
- messages
- activity_log

With proper indexes and foreign key constraints.
