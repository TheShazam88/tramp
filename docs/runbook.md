# TRAMP Runbook

This runbook is the restart-safe local operations guide for TRAMP v2.

## Cold start

```bash
cp .env.example .env
docker compose up --build
```

Open `http://localhost` after the containers are up.

## First login

1. Open `/login`
2. Sign in with:
   - email: the `INITIAL_ADMIN_EMAIL` value from your private `.env`
   - password: the `INITIAL_ADMIN_PASSWORD` value from your private `.env`
3. Go through onboarding and enroll TOTP
4. Use the same account for admin integrations and booking approval

## Stop or reset

Stop containers:

```bash
docker compose down
```

Full clean reset:

```bash
docker compose down -v
docker compose up --build
```

## Container checks

Status:

```bash
docker compose ps
```

All logs:

```bash
docker compose logs -f
```

Focused logs:

```bash
docker compose logs -f api worker beat frontend caddy postgres redis
```

## Local expectations

- `caddy` exposes `http://localhost`
- `frontend` serves the TRAMP UI
- `api` serves `/api/v1`
- `worker` processes notification delivery jobs
- `beat` remains available for scheduler expansion
- `postgres` stores users, integrations, bookings, deliveries, and disruption state
- `redis` backs Celery and cache-style coordination

## Health checks

Primary API health:

```bash
curl http://localhost/api/v1/health
```

Expected high-level fields:

- `status`
- `environment`
- `checks.database`
- `checks.redis`
- `checks.key_unlock_mode`
- `checks.master_key_source`
- `checks.integrations`

## Admin integrations workflow

After logging in:

1. Open `Admin`
2. Save or update provider settings
3. Use `Test connection`
4. Confirm the provider status and health notes update

Recommended localhost-safe defaults:

- notifications: `delivery_mode=log_only`
- calendar: `delivery_mode=log_only`
- flights/hotels/booking: leave credentials blank unless you are testing live-shaped setup

## Notification delivery modes

### Log only

Safe default. Notification attempts are recorded without real delivery.

### SMTP dev

Point to a local mail sink, for example:

```env
delivery_mode=smtp_dev
smtp_host=mailpit
smtp_port=1025
smtp_from_address=alerts@tramp.local
```

### Telegram bot

Save `telegram_bot_token` in Admin and make sure the user profile or integration config provides a destination chat ID.

## Calendar modes

### Log only

Safe default. Booking and cancellation still record calendar detail without external side effects.

### Google Calendar

Save:

- `delivery_mode=google_calendar`
- `calendar_id`
- `access_token`

Then book and cancel a trip to confirm event creation and unwind state.

## Auto-unlock mode

Default:

```env
KEY_UNLOCK_MODE=master_key
```

Optional localhost unattended mode:

```env
KEY_UNLOCK_MODE=auto
MASTER_KEY_SOURCE=local_file
AUTO_UNLOCK_LOCAL_FILE_PATH=.tramp-auto-unlock.key
AUTO_UNLOCK_SEED_MATERIAL=replace-me
```

This is intended for local experimentation only.

## Manual localhost verification checklist

1. `docker compose up --build`
2. Confirm `GET /api/v1/health` returns `status=ok` or expected degraded diagnostics
3. Log in as the seeded admin
4. Complete TOTP enrollment
5. Open `Admin` and save at least one integration setting
6. Run `Test connection`
7. Confirm provider state survives page refresh
8. Complete a booking approval flow
9. Open `Bookings` and confirm:
   - booking status
   - calendar detail
   - notification delivery detail
10. Click `Simulate disruption`
11. Confirm the disruption appears
12. Click `Resolve disruption`

## Useful commands

Run migrations manually:

```bash
docker compose run --rm api alembic upgrade head
```

Backend shell:

```bash
docker compose run --rm api /bin/sh
```

Frontend build smoke check:

```bash
docker compose run --rm frontend nginx -t
```

Backend tests:

```bash
docker compose run --rm api pytest
```

## Optional Vault

Vault is still optional:

```bash
docker compose --profile vault up -d vault
```

Use it only for local development experiments.
