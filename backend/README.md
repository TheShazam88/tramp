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
