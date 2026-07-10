# Travel Watch Backend

FastAPI backend scaffold for the Travel Watch project.

## Quick start

```bash
pip install -e .
uvicorn app.main:app --reload
```

Set the required environment variables before starting the API:

- `APP_SECRET`
- `DATABASE_URL`
- `REDIS_URL`
- `PUBLIC_BASE_URL`

Run migrations with:

```bash
alembic upgrade head
```

## Required PostgreSQL verification

The ordinary Pytest suite skips destructive migration and database-constraint tests when no
dedicated PostgreSQL database is configured. Before release, run this command from the repository
root:

```bash
backend/scripts/test-migrations.sh
```

The script builds the backend image, starts a disposable PostgreSQL 16 container, sets
`MIGRATION_TEST_DATABASE_URL` and `MIGRATION_TEST_ALLOW_RESET=1`, and runs the migration-chain and
TRAMP-Stamp ledger database tests. It fails if any selected test skips and removes its temporary
container, network, database, and image on exit.
