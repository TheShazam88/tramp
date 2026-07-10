# TRAMP

TRAMP is a localhost-first travel concierge platform with real authentication, seeded admin access, persistent profile/watch/deal/booking flows, writable admin integrations, notification delivery diagnostics, calendar hooks, disruption simulation, and a Docker-first development stack.

## Stack

- `frontend`: React + Vite UI
- `api`: FastAPI backend
- `worker`: Celery worker for async notification jobs
- `beat`: Celery beat scheduler
- `postgres`: PostgreSQL 16
- `redis`: Redis broker/cache
- `caddy`: local reverse proxy
- `vault`: optional local dev secrets backend

## Local startup

1. Copy the example env file:

   ```bash
   cp .env.example .env
   ```

2. Update at least:
   - `APP_SECRET`
   - `INITIAL_ADMIN_EMAIL`
   - `INITIAL_ADMIN_PASSWORD`
   - `POSTGRES_PASSWORD`
   - `PUBLIC_BASE_URL` if you are not using `http://localhost`

3. Start the stack:

   ```bash
   docker compose up --build
   ```

4. Open `http://localhost`.

## Seeded admin access

- Email: the `INITIAL_ADMIN_EMAIL` value from your private `.env`
- Password: the `INITIAL_ADMIN_PASSWORD` value from your private `.env`

On first login, TRAMP allows the seeded admin to sign in before TOTP exists, then complete authenticator enrollment in the onboarding flow. Duo Mobile, Google Authenticator, 1Password, Authy, and other standard TOTP apps work.

## Localhost operating modes

TRAMP v2 stays safe on localhost by supporting three shapes:

- `demo`: seeded data and dry-run side effects
- `test-live-shape`: real code paths with sandbox-style credentials where available
- `localhost-prod-shape`: full local contracts, queues, and diagnostics using locally supplied credentials

The default setup remains safe and mock/test-oriented until you configure integrations in the admin UI.

## What v2 adds

- Writable admin integrations with encrypted secret persistence
- Notification transport adapters with Celery-backed delivery tracking
- Calendar sync hooks with log-only fallback
- Booking attempt tracking and stronger idempotency/audit paths
- Localhost disruption simulation and resolution flow
- Optional local-file auto-unlock support for unattended booking experiments
- Richer health output at `/api/v1/health`

## Integration management

Provider credentials now live primarily in the TRAMP admin UI instead of only in `.env`.

- Go to `Admin` after logging in
- Save credentials, modes, and feature flags per integration
- Use `Test connection` to validate the currently saved state
- Settings are stored encrypted at rest in PostgreSQL and survive restart

Supported v2 admin-managed surfaces include:

- flights
- hotels
- booking
- notifications
- calendar

## Notification and calendar behavior

- Notification mode defaults to `log_only`
- SMTP dev mode can be pointed at a local mail sink such as MailHog/Mailpit
- Telegram mode can use a test bot token
- Calendar mode defaults to `log_only`
- Google Calendar mode can be enabled by saving `calendar_id` and `access_token` in Admin

Booking and cancellation flows now record notification delivery state and calendar sync detail so localhost runs remain observable.

## Auto-unlock for localhost

Default mode stays:

```env
KEY_UNLOCK_MODE=master_key
```

For unattended booking experiments, switch to:

```env
KEY_UNLOCK_MODE=auto
MASTER_KEY_SOURCE=local_file
AUTO_UNLOCK_LOCAL_FILE_PATH=.tramp-auto-unlock.key
AUTO_UNLOCK_SEED_MATERIAL=replace-me
```

This keeps the local auto-unlock secret encrypted on disk using the app secret. It is intended only for localhost testing.

## Health and diagnostics

- App health: `GET /api/v1/health`
- Admin integrations: UI-backed diagnostics for saved providers
- Bookings page: notification, calendar, and disruption status summaries

## Verification

Minimum verification after a fresh boot:

1. Log in with the seeded admin.
2. Complete TOTP enrollment.
3. Save at least one integration setting in `Admin`.
4. Run a connection test.
5. Create or review a booking flow.
6. Confirm notification and calendar detail appears on the booking record.
7. Simulate a disruption and resolve it.

## Optional Vault

Vault is still optional. Start it only if you want to experiment with secrets backends:

```bash
docker compose --profile vault up -d vault
```

## Repository pointers

- `docs/runbook.md`: restart-safe local operations guide
- `.env.example`: local bootstrap defaults
- `backend/`: API, models, services, migrations, worker tasks
- `frontend/`: app shell, onboarding, profile, bookings, admin UI
