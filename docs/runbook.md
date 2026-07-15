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

## Selective simulated-activity purge

Use the selective purge when you want to remove generated test activity without resetting household setup or the database volume:

1. Sign in as an administrator.
2. Open `Admin` → `Runtime`.
3. Select `Preview purge`.
4. Review the per-table counts, watch restorations, and warnings.
5. Copy or type the exact phrase `PURGE TEST DATA`.
6. Execute the purge from the same preview. The API binds execution to that preview's `plan_digest` and refuses a stale plan.

The preview endpoint is `GET /api/v1/admin/test-data/purge-preview`; it does not mutate data. The confirmed endpoint is `POST /api/v1/admin/test-data/purge` with both the exact confirmation and preview digest.

The transaction removes classified simulated observations, deals, feedback, booking attempts and bookings, simulated cancellations and disruptions, related notifications and spend rows, affected learning state, test audit rows, and derived price statistics. It restores eligible watch, deal, and booking state where test activity had changed it.

It preserves users, travelers, loyalty accounts, traveler groups, preferences, payment methods, trip templates, watch definitions, integration settings, live activity, and every stamped booking. The service aborts rather than deleting a booking referenced by `tramp_stamp_ledger`.

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
- `postgres` stores users, integrations, bookings, the TRAMP-Stamp ledger, deliveries, and disruption state
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

## Live booking and TRAMP-Stamps

The in-app `Book now` action is the real guarded booking path, not an approval-intent shortcut:

1. Open a proposed deal and review readiness, price context, loyalty mapping, and coverage.
2. Choose a saved payment method.
3. Enter the six-digit TOTP code and, when the configured key mode requires it, the master-key passphrase.
4. TRAMP mints or verifies a signed approval token and submits `/api/v1/bookings/approve` with one idempotency key.
5. The booking service revalidates the offer and guardrails, executes the configured provider, and durably commits booking, spend, audit, notification, and eligible stamp state before any external calendar call.
6. Calendar creation runs only after that commit. Its success, failure, or simulated log-only outcome is persisted in a second transaction. An idempotent booking replay returns the saved record and never repeats the calendar call.

Exactly one ledger row is inserted only when execution is explicitly non-simulated, the deal source and provider payload are non-simulated, and the resulting booking is `ticketed` or `booked`. The unique booking constraint makes retries safe. Mock bookings, failed attempts, and idempotent replays earn no stamp; cancellation does not revoke an earned stamp.

The frontend shows the blue-and-gold butterfly only when the response reports `tramp_stamps_awarded=1`. The profile and top-bar balance are calculated from `tramp_stamp_ledger`, not a mutable cached counter.

## Secure cancellation

Cancellation is a money-moving action and is fail-closed. The Bookings screen first mints a signed, single-use token at `POST /api/v1/bookings/{booking_id}/cancellation-approval-token`, then submits `POST /api/v1/bookings/{booking_id}/cancel` with:

- `approval_token`
- six-digit `totp_code`
- `master_key_passphrase` when `KEY_UNLOCK_MODE=master_key`
- a stable `idempotency_key`
- optional `reason`

The token is bound to the booking, deal, watch, and authenticated owner. The booking row is locked during execution, the provider receives the cancellation idempotency key, and replaying the same key returns the saved cancellation without another provider call. Requests missing any required security field are rejected before provider execution.

## Admin recovery for unresolved booking attempts

An administrator can release an ambiguous or pending attempt only after checking the provider independently and deciding that no successful provider booking should be represented in TRAMP:

`POST /api/v1/admin/booking-attempts/{idempotency_key}/recover-failed`

The JSON body must contain the exact confirmation `MARK ATTEMPT FAILED`. The action marks only an unresolved attempt failed, clears `recovery_required`, writes `booking_attempt.recovered_as_failed`, and returns the deal to `proposed` only when no booking row exists. If a booking row exists, its deal remains booked. This action never creates a booking or claims provider success.

## Notification delivery modes

### Log only

Safe default. Notification attempts are recorded without real delivery.

Simulated deals, providers, payloads, cancellations, and manual disruption tests are forced through this path even if SMTP, Telegram, or Google Calendar is configured. The local delivery and calendar outcome remain visible for audit and status review.

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

### Booking-claim migration maintenance window

Revision `20260710_0005` creates its unique booking-attempt index concurrently, then attaches
the database constraint. Stop every old process that can write booking state before upgrading:

```bash
docker compose stop api worker beat
docker compose run --rm api alembic upgrade head
docker compose up -d api worker beat
```

Keep PostgreSQL running and take the normal database backup before the window. If the migration
reports duplicate idempotency keys, leave the API and workers stopped, inspect the reported
`booking_attempts` audit rows, and resolve them manually. The migration never deletes audit
history.

An interrupted concurrent-index build can leave
`ux_booking_attempts_idempotency_key_claim` behind. Rerunning the migration safely drops that
temporary index concurrently and rebuilds it before attaching the constraint. Do not restart old
API or worker processes between a failed attempt and the retry.

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

### Refresh documentation screenshots

The capture script starts its own loopback-only Vite process, forces `VITE_API_MODE=mock`, fixes browser time and locale, blocks external HTTP requests, disables animation, and captures a `1440x1000` viewport. It does not need real credentials or a separately running development server.

```bash
cd frontend
npm ci
npx playwright install chromium
npm run screenshots
npm run screenshots:smoke
```

The outputs are:

- `docs/screenshots/01-watches-dashboard.png`
- `docs/screenshots/02-deal-review.png`
- `docs/screenshots/03-admin-integrations.png`
- `docs/screenshots/04-household-workspace.png`

`npm run screenshots:smoke` verifies each file is non-empty, has a valid PNG header and terminator, and is exactly `1440x1000`.

## Optional Vault

Vault is still optional:

```bash
docker compose --profile vault up -d vault
```

Use it only for local development experiments.
