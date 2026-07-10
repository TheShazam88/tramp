# TRAMP Brand, Rewards, Operations, and Release Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Preserve the existing TRAMP design while shipping the Editorial Gold wordmark, one-stamp live-booking rewards with the approved butterfly animation, real in-app booking, inline provider acquisition guidance, selective test-data purge, usability improvements, screenshots, documentation, QA, backups, and a sanitized GitHub release.

**Architecture:** Add an immutable stamp ledger keyed uniquely by booking, award from the existing booking transaction, and expose balance through profile and booking responses. Keep provider guidance in the integration catalog, and isolate destructive cleanup in an admin service with preview and confirmed execution. Implement all frontend additions with existing primitives, tokens, and query patterns.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2, Alembic, PostgreSQL, Pytest, React 19, TypeScript 6, TanStack Query, Vite 8, CSS/SVG animation, Playwright Chromium, Docker Compose, GitHub CLI.

---

## File Structure

### Backend files to create

- `backend/alembic/versions/20260710_0004_tramp_stamps.py`: creates the stamp ledger.
- `backend/app/tramp_stamp_service.py`: stamp eligibility, idempotent award, and balance calculation.
- `backend/app/admin_activity_service.py`: preview and execute selective simulated-activity purge.
- `backend/tests/test_tramp_stamps.py`: reward eligibility and idempotency tests.
- `backend/tests/test_admin_activity_purge.py`: purge preview, deletion, and preservation tests.

### Frontend files to create

- `frontend/src/components/brand/TrampBrand.tsx`: shared Editorial Gold wordmark.
- `frontend/src/components/rewards/TrampStampButterfly.tsx`: approved SVG and animation.
- `frontend/src/components/admin/CredentialGuide.tsx`: provider acquisition disclosure.
- `frontend/src/components/admin/PurgeTestDataPanel.tsx`: preview and confirmed purge UI.
- `frontend/scripts/check-user-copy.mjs`: user-facing long-dash regression check.
- `frontend/scripts/capture-screenshots.mjs`: deterministic local screenshot capture.
- `docs/screenshots/01-watches-dashboard.png`
- `docs/screenshots/02-deal-review.png`
- `docs/screenshots/03-admin-integrations.png`
- `docs/screenshots/04-household-workspace.png`

### Existing files to modify

- `backend/app/db/models.py`
- `backend/app/api/schemas/bookings.py`
- `backend/app/api/schemas/profile.py`
- `backend/app/api/schemas/integrations.py`
- `backend/app/api/routes/profile.py`
- `backend/app/api/routes/admin.py`
- `backend/app/booking_service.py`
- `backend/app/integrations/types.py`
- `backend/app/integrations/catalog.py`
- `frontend/package.json`
- `frontend/src/api/types.ts`
- `frontend/src/api/travelWatchApi.ts`
- `frontend/src/layouts/AppLayout.tsx`
- `frontend/src/pages/LoginPage.tsx`
- `frontend/src/pages/DealReviewPage.tsx`
- `frontend/src/pages/AdminIntegrationsPage.tsx`
- `frontend/src/pages/WatchesPage.tsx`
- `frontend/src/pages/BookingsPage.tsx`
- `frontend/src/components/watch/WatchForm.tsx`
- `frontend/src/theme/global.css`
- `README.md`
- `docs/runbook.md`
- `travel-autobook-spec.md`

---

### Task 1: Save the Legacy Release Locally

**Files:**
- Create outside repository: `/Users/mattdm/Documents/Cursor_Projects/Travel Booking Legacy Backups/<timestamp>/tramp-legacy.bundle`
- Create outside repository: `/Users/mattdm/Documents/Cursor_Projects/Travel Booking Legacy Backups/<timestamp>/test_profile_loyalty.sqlite3`
- Create outside repository: `/Users/mattdm/Documents/Cursor_Projects/Travel Booking Legacy Backups/<timestamp>/SHA256SUMS`

- [ ] **Step 1: Verify the source repository and backup parent**

Run:

```bash
git -C "/Users/mattdm/Documents/Cursor_Projects/Travel Booking" status --short
ls "/Users/mattdm/Documents/Cursor_Projects"
```

Expected: the SQLite fixture and pre-existing plan may be dirty; the parent directory exists.

- [ ] **Step 2: Create a timestamped backup directory**

Run:

```bash
BACKUP_ROOT="/Users/mattdm/Documents/Cursor_Projects/Travel Booking Legacy Backups/$(date +%Y%m%d-%H%M%S)"
mkdir -p "$BACKUP_ROOT"
printf '%s\n' "$BACKUP_ROOT"
```

Expected: one new directory outside the Git repository.

- [ ] **Step 3: Create and verify the Git bundle**

Run:

```bash
git -C "/Users/mattdm/Documents/Cursor_Projects/Travel Booking" bundle create "$BACKUP_ROOT/tramp-legacy.bundle" --all
git bundle verify "$BACKUP_ROOT/tramp-legacy.bundle"
```

Expected: verification reports a complete bundle with the legacy branches and tags.

- [ ] **Step 4: Copy the local SQLite fixture and write checksums**

Run:

```bash
cp "/Users/mattdm/Documents/Cursor_Projects/Travel Booking/backend/test_profile_loyalty.sqlite3" "$BACKUP_ROOT/test_profile_loyalty.sqlite3"
shasum -a 256 "$BACKUP_ROOT/tramp-legacy.bundle" "$BACKUP_ROOT/test_profile_loyalty.sqlite3" > "$BACKUP_ROOT/SHA256SUMS"
```

Expected: all three backup files exist outside the repository.

---

### Task 2: Add the User-Facing Copy Guard

**Files:**
- Create: `frontend/scripts/check-user-copy.mjs`
- Modify: `frontend/package.json`

- [ ] **Step 1: Write the failing copy-check smoke case**

Create a temporary file and run the not-yet-existing command:

```bash
printf 'Bad \342\200\224 copy\n' > /tmp/tramp-bad-copy.txt
cd frontend
npm run check:copy -- /tmp/tramp-bad-copy.txt
```

Expected: FAIL because `check:copy` does not exist.

- [ ] **Step 2: Implement the dependency-free scanner**

Create `frontend/scripts/check-user-copy.mjs`:

```javascript
import { readdir, readFile, stat } from "node:fs/promises";
import { resolve } from "node:path";

const forbidden = /[\u2013\u2014]/g;
const defaults = ["src", "index.html"];
const requested = process.argv.slice(2);
const roots = (requested.length ? requested : defaults).map((item) => resolve(item));
const files = [];

async function collect(path) {
  const info = await stat(path);
  if (info.isFile()) {
    files.push(path);
    return;
  }
  for (const entry of await readdir(path, { withFileTypes: true })) {
    if (entry.name.startsWith(".") || entry.name === "node_modules") continue;
    await collect(resolve(path, entry.name));
  }
}

for (const root of roots) await collect(root);

const failures = [];
for (const file of files) {
  const text = await readFile(file, "utf8");
  text.split(/\r?\n/).forEach((line, index) => {
    if (forbidden.test(line)) failures.push(`${file}:${index + 1}: ${line.trim()}`);
    forbidden.lastIndex = 0;
  });
}

if (failures.length) {
  console.error("User-facing copy contains an em dash or en dash:");
  console.error(failures.join("\n"));
  process.exit(1);
}
console.log(`Copy check passed across ${files.length} files.`);
```

- [ ] **Step 3: Wire the scanner into the build**

Update `frontend/package.json` scripts:

```json
{
  "check:copy": "node scripts/check-user-copy.mjs",
  "build": "npm run check:copy && tsc --noEmit && vite build"
}
```

- [ ] **Step 4: Verify failure and success**

Run:

```bash
cd frontend
npm run check:copy -- /tmp/tramp-bad-copy.txt
npm run check:copy
```

Expected: the first command fails with file and line; the second passes.

- [ ] **Step 5: Commit**

```bash
git add frontend/scripts/check-user-copy.mjs frontend/package.json
git commit -m "Add user-facing copy guard"
```

---

### Task 3: Add the TRAMP-Stamp Ledger and Profile Balance

**Files:**
- Create: `backend/alembic/versions/20260710_0004_tramp_stamps.py`
- Modify: `backend/app/db/models.py`
- Modify: `backend/app/api/schemas/profile.py`
- Modify: `backend/app/api/routes/profile.py`
- Create: `backend/tests/test_tramp_stamps.py`

- [ ] **Step 1: Write failing model and balance tests**

Create `backend/tests/test_tramp_stamps.py`:

```python
from datetime import UTC, datetime
from uuid import uuid4

from app.db.models import BookingStatus, TrampStampLedger
from app.tramp_stamp_service import stamp_balance


class FakeScalarSession:
    def __init__(self, scalar_result: int) -> None:
        self.scalar_result = scalar_result

    def scalar(self, _statement):
        return self.scalar_result


def test_stamp_ledger_is_one_stamp_per_booking() -> None:
    award = TrampStampLedger(
        user_id=uuid4(),
        booking_id=uuid4(),
        amount=1,
        reason="live_booking_completed",
        awarded_at=datetime.now(UTC),
        meta_json={},
    )
    assert award.amount == 1
    assert BookingStatus.TICKETED.value == "ticketed"


def test_stamp_balance_returns_sum() -> None:
    db = FakeScalarSession(scalar_result=3)
    assert stamp_balance(db=db, user_id=uuid4()) == 3
```

- [ ] **Step 2: Run the focused test**

Run:

```bash
docker run --rm \
  -v "$PWD/backend/app:/app/app:ro" \
  -v "$PWD/backend/tests:/app/tests:ro" \
  -e INITIAL_ADMIN_EMAIL=admin@example.com \
  -e INITIAL_ADMIN_PASSWORD=test-admin-password \
  -e APP_SECRET=test-secret-with-at-least-thirty-two-bytes \
  -e DATABASE_URL=postgresql+psycopg://user:pass@localhost/test_db \
  -e REDIS_URL=redis://localhost:6379/0 \
  -e PUBLIC_BASE_URL=https://tramp.test \
  travelbooking-api /bin/sh -c "pip install 'pytest>=8.2,<9.0' >/tmp/pytest.log && pytest tests/test_tramp_stamps.py -q"
```

Expected: FAIL because the model and service do not exist.

- [ ] **Step 3: Add the model**

Add after `SpendLedger` in `backend/app/db/models.py`:

```python
class TrampStampLedger(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "tramp_stamp_ledger"
    __table_args__ = (
        UniqueConstraint("booking_id", name="uq_tramp_stamp_ledger_booking_id"),
        CheckConstraint("amount = 1", name="ck_tramp_stamp_ledger_single_stamp"),
    )

    user_id: Mapped[UUID] = mapped_column(
        SQLUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    booking_id: Mapped[UUID] = mapped_column(
        SQLUUID(as_uuid=True), ForeignKey("bookings.id", ondelete="RESTRICT"), nullable=False
    )
    amount: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    reason: Mapped[str] = mapped_column(String(64), nullable=False)
    awarded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    meta_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
```

Import `CheckConstraint` if it is not already imported.

- [ ] **Step 4: Add the migration**

Create revision `20260710_0004`, down revision `20260630_0003`, with columns and constraints matching the model. The downgrade drops the table and its user index.

- [ ] **Step 5: Add balance calculation**

Create `backend/app/tramp_stamp_service.py`:

```python
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import TrampStampLedger


def stamp_balance(*, db: Session, user_id: UUID) -> int:
    return int(
        db.scalar(
            select(func.coalesce(func.sum(TrampStampLedger.amount), 0)).where(
                TrampStampLedger.user_id == user_id
            )
        )
        or 0
    )
```

- [ ] **Step 6: Expose balance in profile**

Add `tramp_stamp_balance: int` to `ProfileSummaryResponse`. Populate it in `_build_profile_summary()` with `stamp_balance(db=db, user_id=user.id)`.

- [ ] **Step 7: Run migration and tests**

Run:

```bash
export COMPOSE_PROJECT_NAME=tramp-rewards-qa
export INITIAL_ADMIN_EMAIL=admin@example.com
export INITIAL_ADMIN_PASSWORD=test-admin-password
export APP_SECRET=test-secret-with-at-least-thirty-two-bytes
docker compose up -d postgres
docker compose run --rm api alembic upgrade head
```

Then rerun `tests/test_tramp_stamps.py`. Use
`docker compose down -v` after the migration and purge integration tests.

Expected: migration and focused tests pass.

- [ ] **Step 8: Commit**

```bash
git add backend/alembic/versions/20260710_0004_tramp_stamps.py backend/app/db/models.py backend/app/tramp_stamp_service.py backend/app/api/schemas/profile.py backend/app/api/routes/profile.py backend/tests/test_tramp_stamps.py
git commit -m "Add TRAMP-Stamp ledger"
```

---

### Task 4: Award One Stamp From Successful Live Bookings

**Files:**
- Modify: `backend/app/tramp_stamp_service.py`
- Modify: `backend/app/booking_service.py`
- Modify: `backend/app/api/schemas/bookings.py`
- Modify: `backend/tests/test_tramp_stamps.py`
- Modify: `backend/tests/test_booking_flow.py`

- [ ] **Step 1: Add failing eligibility tests**

Add this parameterized test to `test_tramp_stamps.py`:

```python
from types import SimpleNamespace

import pytest

from app.db.models import BookingStatus
from app.tramp_stamp_service import award_for_live_booking


class FakeStampSession:
    def __init__(self, existing=None):
        self.existing = existing
        self.added = []

    def scalar(self, _statement):
        return self.existing

    def add(self, value):
        self.added.append(value)


@pytest.mark.parametrize(
    ("status", "deal_source", "provider", "payload", "existing", "expected"),
    [
        (BookingStatus.TICKETED, "live-amadeus", "duffel", {}, None, 1),
        (BookingStatus.TICKETED, "mock-amadeus", "duffel", {}, None, 0),
        (BookingStatus.TICKETED, "live-amadeus", "mock-booking", {}, None, 0),
        (BookingStatus.TICKETED, "live-amadeus", "duffel", {"simulated": True}, None, 0),
        (BookingStatus.FAILED, "live-amadeus", "duffel", {}, None, 0),
        (BookingStatus.TICKETED, "live-amadeus", "duffel", {}, object(), 0),
    ],
)
def test_stamp_award_eligibility(
    status, deal_source, provider, payload, existing, expected
) -> None:
    db = FakeStampSession(existing=existing)
    user = SimpleNamespace(id=uuid4())
    deal = SimpleNamespace(id=uuid4(), watch_id=uuid4(), source=deal_source)
    booking = SimpleNamespace(id=uuid4(), status=status, provider=provider)

    awarded = award_for_live_booking(
        db=db,
        user=user,
        booking=booking,
        deal=deal,
        provider_payload=payload,
    )

    assert awarded == expected
    assert len(db.added) == expected
```

Extend `test_booking_flow.py` so a first successful response asserts
`tramp_stamps_awarded == 1`, its idempotent replay asserts
`tramp_stamps_awarded == 0`, and both responses report the same
`tramp_stamp_balance`.

- [ ] **Step 2: Run focused tests**

Run `pytest tests/test_tramp_stamps.py tests/test_booking_flow.py -q`.

Expected: FAIL because award behavior and response fields are missing.

- [ ] **Step 3: Implement idempotent award**

Add to `tramp_stamp_service.py`:

```python
def award_for_live_booking(
    *,
    db: Session,
    user: User,
    booking: Booking,
    deal: Deal,
    provider_payload: dict[str, object] | None,
) -> int:
    if booking.status not in {BookingStatus.TICKETED, BookingStatus.BOOKED}:
        return 0
    if source_is_simulated(deal.source):
        return 0
    if provider_is_simulated(booking.provider) or payload_is_simulated(provider_payload):
        return 0
    existing = db.scalar(
        select(TrampStampLedger).where(TrampStampLedger.booking_id == booking.id)
    )
    if existing:
        return 0
    db.add(
        TrampStampLedger(
            user_id=user.id,
            booking_id=booking.id,
            amount=1,
            reason="live_booking_completed",
            awarded_at=datetime.now(UTC),
            meta_json={"deal_id": str(deal.id), "watch_id": str(deal.watch_id), "provider": booking.provider},
        )
    )
    return 1
```

- [ ] **Step 4: Extend booking response**

Add to `BookingResponse`:

```python
tramp_stamps_awarded: int = 0
tramp_stamp_balance: int = 0
```

Update `serialize_booking()` to accept `tramp_stamps_awarded: int = 0` and calculate balance.

- [ ] **Step 5: Call award inside the booking transaction**

After booking and attempt rows are populated, before `db.commit()`:

```python
stamps_awarded = award_for_live_booking(
    db=db,
    user=user,
    booking=booking,
    deal=deal,
    provider_payload=provider_result.provider_payload,
)
```

Return:

```python
return serialize_booking(
    db=db,
    user=user,
    booking=booking,
    tramp_stamps_awarded=stamps_awarded,
)
```

- [ ] **Step 6: Verify focused and full backend tests**

Expected: all reward and booking tests pass; no simulated test earns a stamp.

- [ ] **Step 7: Commit**

```bash
git add backend/app/tramp_stamp_service.py backend/app/booking_service.py backend/app/api/schemas/bookings.py backend/tests/test_tramp_stamps.py backend/tests/test_booking_flow.py
git commit -m "Award one stamp for live bookings"
```

---

### Task 5: Implement the Real In-App Booking Flow

**Files:**
- Modify: `frontend/src/api/types.ts`
- Modify: `frontend/src/api/travelWatchApi.ts`
- Modify: `frontend/src/pages/DealReviewPage.tsx`

- [ ] **Step 1: Define the frontend booking contract**

Extend `DealApprovalResult`:

```typescript
trampStampsAwarded: number;
trampStampBalance: number;
```

Add a booking request type:

```typescript
export interface BookDealRequest {
  dealId: string;
  paymentMethodId: string;
  totpCode: string;
  masterKeyPassphrase: string;
}
```

- [ ] **Step 2: Replace candidate approval paths with the real endpoint**

Implement `bookDeal()` in `travelWatchApi.ts`:

```typescript
const approval = await travelWatchApi.createApprovalToken(payload.dealId);
const response = await apiClient.post<BookingRaw>("/bookings/approve", {
  deal_id: payload.dealId,
  approval_token: approval.token,
  totp_code: payload.totpCode,
  master_key_passphrase: payload.masterKeyPassphrase || undefined,
  payment_method_id: payload.paymentMethodId,
  idempotency_key: crypto.randomUUID(),
});
```

Map booking fields plus `tramp_stamps_awarded` and `tramp_stamp_balance`.

- [ ] **Step 3: Add secure booking inputs**

On `DealReviewPage`:

- load `ProfileWorkspace`
- show a saved payment-method selector
- show TOTP input
- show master-key passphrase input
- disable Book now unless readiness has no blockers, payment is selected, and TOTP has six digits
- submit through `bookDeal()`

- [ ] **Step 4: Refresh all affected data**

On success invalidate:

```typescript
queryKeys.deal(dealId, watchId)
queryKeys.dashboard
queryKeys.bookings
queryKeys.profile
```

- [ ] **Step 5: Verify TypeScript**

Run `npm run build`.

Expected: PASS, and no remaining `Book now` call uses `confirmDealIntent()`.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/api/types.ts frontend/src/api/travelWatchApi.ts frontend/src/pages/DealReviewPage.tsx
git commit -m "Connect Book now to booking execution"
```

---

### Task 6: Add Editorial Gold Branding and Butterfly Rewards

**Files:**
- Create: `frontend/src/components/brand/TrampBrand.tsx`
- Create: `frontend/src/components/rewards/TrampStampButterfly.tsx`
- Modify: `frontend/src/layouts/AppLayout.tsx`
- Modify: `frontend/src/pages/LoginPage.tsx`
- Modify: `frontend/src/pages/DealReviewPage.tsx`
- Modify: `frontend/src/api/types.ts`
- Modify: `frontend/src/api/travelWatchApi.ts`
- Modify: `frontend/src/theme/global.css`

- [ ] **Step 1: Map stamp balance from profile**

Add `tramp_stamp_balance` to `ProfileSummaryRaw` and `trampStampBalance` to `ProfileWorkspace`. Default mock balance is `0`.

- [ ] **Step 2: Build the shared wordmark**

Create:

```tsx
export function TrampBrand({ compact = false }: { compact?: boolean }) {
  return (
    <div className={compact ? "tramp-brand tramp-brand-compact" : "tramp-brand"}>
      <span className="brand-wordmark">TRAMP</span>
      <span className="brand-expansion">Travel Amplifier</span>
    </div>
  );
}
```

Use it in `AppLayout` and `LoginPage`. Remove only the header `<img className="app-logo">`. Leave `frontend/public/tramp-app-icon.*` unchanged.

- [ ] **Step 3: Build the approved ornate butterfly**

Create `TrampStampButterfly.tsx` with:

- a symmetric SVG inspired by the approved reference
- rounded blue wings
- metallic gold outlines and curled ornaments
- long lower tails
- three descent flutters
- two settling flutters
- final open-wing pose
- `+1 TRAMP-Stamp` label
- `aria-live="polite"`

The root receives `active`, `balance`, and `onComplete`.

- [ ] **Step 4: Add reduced-motion CSS**

Add keyframes matching the approved timing. Under `@media (prefers-reduced-motion: reduce)`, disable keyframes and show the final static state.

- [ ] **Step 5: Trigger once from booking success**

Store `stampAward` state on `DealReviewPage`. Activate only when `result.trampStampsAwarded === 1`, and clear it after `onComplete`.

- [ ] **Step 6: Show the persistent balance**

Add a luxury badge with a small static butterfly mark and:

```text
{data.trampStampBalance} TRAMP-Stamps
```

Use the actual mapped profile field name.

- [ ] **Step 7: Build and visually verify**

Run `npm run build`, then verify desktop and mobile widths in Chromium.

- [ ] **Step 8: Commit**

```bash
git add frontend/src/components/brand/TrampBrand.tsx frontend/src/components/rewards/TrampStampButterfly.tsx frontend/src/layouts/AppLayout.tsx frontend/src/pages/LoginPage.tsx frontend/src/pages/DealReviewPage.tsx frontend/src/api/types.ts frontend/src/api/travelWatchApi.ts frontend/src/theme/global.css
git commit -m "Add Editorial Gold stamp experience"
```

---

### Task 7: Add Structured Provider Acquisition Guidance

**Files:**
- Modify: `backend/app/integrations/types.py`
- Modify: `backend/app/integrations/catalog.py`
- Modify: `backend/app/api/schemas/integrations.py`
- Modify: `frontend/src/api/types.ts`
- Modify: `frontend/src/api/travelWatchApi.ts`
- Create: `frontend/src/components/admin/CredentialGuide.tsx`
- Modify: `frontend/src/pages/AdminIntegrationsPage.tsx`
- Modify: `README.md`

- [ ] **Step 1: Verify official provider URLs**

Use Firecrawl to verify current official URLs for Amadeus, Duffel, Kiwi partner access, Hotelbeds or Booking Demand, Telegram bot setup, SMTP guidance, and Google Cloud Calendar credentials. Reject stale or third-party signup pages.

- [ ] **Step 2: Add the structured backend type**

```python
@dataclass(frozen=True, slots=True)
class IntegrationAcquisitionGuide:
    signup_url: str
    application_url: str | None = None
    account_requirements: str = ""
    steps: tuple[str, ...] = ()
    environment_notes: str = ""
    enables: tuple[str, ...] = ()
```

Add `acquisition_guide` to catalog and resolved config types.

- [ ] **Step 3: Populate every catalog entry**

All seven provider entries must have a guide. Generic booking and hotel entries explain that exact signup depends on the selected provider and link to the supported official portals.

- [ ] **Step 4: Expose and map the guide**

Add the guide to `AdminIntegrationResponse`, `IntegrationProvider`, raw API interfaces, and `mapIntegrationProvider()`.

- [ ] **Step 5: Create the disclosure component**

Render:

- official signup link
- account requirements
- numbered steps
- test/live note
- enabled TRAMP capabilities

Use `<details>`, existing notice styles, `target="_blank"`, and `rel="noreferrer"`.

- [ ] **Step 6: Place the guide beside every credential form**

Call `CredentialGuide` in shared profile, flight, booking, and generic connector cards immediately before credential inputs.

- [ ] **Step 7: Document provider setup in README**

Add a concise provider table and numbered Admin UI workflow. Do not include any credential values.

- [ ] **Step 8: Verify and commit**

Run backend tests and frontend build.

```bash
git add backend/app/integrations/types.py backend/app/integrations/catalog.py backend/app/api/schemas/integrations.py frontend/src/api/types.ts frontend/src/api/travelWatchApi.ts frontend/src/components/admin/CredentialGuide.tsx frontend/src/pages/AdminIntegrationsPage.tsx README.md
git commit -m "Add inline provider setup guides"
```

---

### Task 8: Implement Selective Simulated-Activity Purge

**Files:**
- Create: `backend/app/admin_activity_service.py`
- Modify: `backend/app/api/schemas/integrations.py`
- Modify: `backend/app/api/routes/admin.py`
- Create: `backend/tests/test_admin_activity_purge.py`

- [ ] **Step 1: Write failing preview and execution tests**

Add concrete confirmation and classification tests:

```python
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.admin_activity_service import (
    ActivitySnapshot,
    build_purge_plan,
    purge_simulated_activity,
)


def test_execute_requires_exact_confirmation() -> None:
    with pytest.raises(ValueError, match="PURGE TEST DATA"):
        purge_simulated_activity(
            db=SimpleNamespace(),
            actor=SimpleNamespace(id=uuid4()),
            confirmation="purge",
        )


def test_plan_selects_simulated_and_preserves_live_activity() -> None:
    watch_id = uuid4()
    mock_deal = SimpleNamespace(
        id=uuid4(), watch_id=watch_id, source="mock-amadeus"
    )
    live_deal = SimpleNamespace(
        id=uuid4(), watch_id=watch_id, source="live-amadeus"
    )
    mock_booking = SimpleNamespace(
        id=uuid4(), deal_id=mock_deal.id, provider="mock-booking"
    )
    live_booking = SimpleNamespace(
        id=uuid4(), deal_id=live_deal.id, provider="duffel"
    )
    snapshot = ActivitySnapshot(
        deals=[mock_deal, live_deal],
        observations=[],
        bookings=[mock_booking, live_booking],
        booking_attempts=[],
        watches=[],
    )

    plan = build_purge_plan(snapshot)

    assert plan.ids_by_table["deals"] == {mock_deal.id}
    assert plan.ids_by_table["bookings"] == {mock_booking.id}
    assert live_deal.id not in plan.ids_by_table["deals"]
    assert live_booking.id not in plan.ids_by_table["bookings"]
```

Add a service test with a recording fake session that asserts preview never calls
`delete()` or `commit()`. Add a PostgreSQL-backed integration test that seeds one
mock and one live activity chain, executes purge, and asserts the mock chain and
all `PriceStat` rows are gone while users, profiles, watches, integrations, live
booking, and live `TrampStampLedger` remain.

- [ ] **Step 2: Add request and response schemas**

```python
class AdminPurgeTestDataRequest(BaseModel):
    confirmation: str = ""


class AdminPurgeTestDataResponse(BaseModel):
    dry_run: bool
    deleted_counts: dict[str, int]
    reset_watch_count: int
```

- [ ] **Step 3: Implement selection helpers**

Define the service boundary:

```python
@dataclass(slots=True)
class ActivitySnapshot:
    deals: list[Deal]
    observations: list[PriceObservation]
    bookings: list[Booking]
    booking_attempts: list[BookingAttempt]
    watches: list[TripWatch]


@dataclass(slots=True)
class PurgePlan:
    ids_by_table: dict[str, set[UUID]]
    reset_watch_ids: set[UUID]

    @property
    def deleted_counts(self) -> dict[str, int]:
        return {name: len(ids) for name, ids in self.ids_by_table.items()}
```

Load deals, observations, attempts, and bookings, then classify with existing
`source_is_simulated`, `provider_is_simulated`, and `payload_is_simulated`.
`build_purge_plan(snapshot)` is pure and returns IDs without mutating the
session.

- [ ] **Step 4: Implement preview**

`preview_simulated_activity_purge()` returns counts for every affected table and watch reset candidates.

- [ ] **Step 5: Implement confirmed deletion**

Reject any confirmation other than `PURGE TEST DATA`. Delete in this order:

1. notification deliveries
2. disruptions
3. cancellations
4. spend ledger rows
5. booking attempts
6. simulated bookings
7. deal feedback
8. simulated deals
9. simulated observations
10. affected suppressions and rejected fingerprints
11. all derived price stats
12. related test audit rows

Reset eligible watches, add `admin.test_data_purged` audit row, and commit once. Do not delete stamp rows, users, profiles, payment methods, watches, templates, or integrations.

- [ ] **Step 6: Add admin routes**

```python
@router.get("/test-data/purge-preview", response_model=AdminPurgeTestDataResponse)
@router.post("/test-data/purge", response_model=AdminPurgeTestDataResponse)
```

Both depend on `require_admin`.

- [ ] **Step 7: Run focused and full tests**

Expected: preview is non-mutating; execution is precise and transactional.

- [ ] **Step 8: Commit**

```bash
git add backend/app/admin_activity_service.py backend/app/api/schemas/integrations.py backend/app/api/routes/admin.py backend/tests/test_admin_activity_purge.py
git commit -m "Add selective test data purge"
```

---

### Task 9: Add Purge Preview and Copyable Confirmation UI

**Files:**
- Create: `frontend/src/components/admin/PurgeTestDataPanel.tsx`
- Modify: `frontend/src/api/types.ts`
- Modify: `frontend/src/api/travelWatchApi.ts`
- Modify: `frontend/src/pages/AdminIntegrationsPage.tsx`

- [ ] **Step 1: Add API types and methods**

```typescript
export interface PurgeTestDataResult {
  dryRun: boolean;
  deletedCounts: Record<string, number>;
  resetWatchCount: number;
}
```

Add `previewTestDataPurge()` and `purgeTestData(confirmation)`.

- [ ] **Step 2: Build the preview-first panel**

The Runtime page panel must:

- load preview only after user clicks `Preview purge`
- render per-table counts
- explain preserved data
- show `PURGE TEST DATA` in a read-only field
- provide a `Copy phrase` button using `navigator.clipboard.writeText`
- require paste or typing in a separate input
- disable Purge until exact match

- [ ] **Step 3: Invalidate affected queries**

After purge invalidate integrations, system status, dashboard, bookings, and deal queries.

- [ ] **Step 4: Show the returned summary**

Display deletion counts and reset watch count in `notice-value`. Clear the confirmation input.

- [ ] **Step 5: Build and commit**

```bash
git add frontend/src/components/admin/PurgeTestDataPanel.tsx frontend/src/api/types.ts frontend/src/api/travelWatchApi.ts frontend/src/pages/AdminIntegrationsPage.tsx
git commit -m "Add confirmed test data purge UI"
```

---

### Task 10: Apply Focused Usability Improvements

**Files:**
- Modify: `frontend/src/pages/WatchesPage.tsx`
- Modify: `frontend/src/components/watch/WatchForm.tsx`
- Modify: `frontend/src/pages/DealReviewPage.tsx`
- Modify: `frontend/src/pages/BookingsPage.tsx`

- [ ] **Step 1: Add actionable readiness links**

Map blocker text to `/profile`, `/profile/presets`, or `/admin/integrations`. Render the first blocker as an alert notice with one resolution button.

- [ ] **Step 2: Collapse advanced watch fields**

Keep trip essentials open. Move timing, carrier, hotel area, glide, and tuning fields into an existing styled `<details className="form-disclosure">`.

- [ ] **Step 3: Auto-open signed booking review**

When a valid `approvalToken` query parameter verifies, set the booking form visible and focus the TOTP field.

- [ ] **Step 4: Isolate local disruption tools**

Move simulation controls under:

```tsx
<details className="form-disclosure">
  <summary>Local test tools</summary>
  <div className="button-row">
    <Button
      type="button"
      variant="secondary"
      onClick={() => createDisruptionMutation.mutate(booking.id)}
      disabled={createDisruptionMutation.isPending}
    >
      {createDisruptionMutation.isPending ? "Injecting..." : "Simulate disruption"}
    </Button>
    {unresolvedDisruption ? (
      <Button
        type="button"
        variant="ghost"
        onClick={() => resolveDisruptionMutation.mutate(unresolvedDisruption.id)}
        disabled={resolveDisruptionMutation.isPending}
      >
        {resolveDisruptionMutation.isPending ? "Resolving..." : "Resolve disruption"}
      </Button>
    ) : null}
  </div>
</details>
```

Define `unresolvedDisruption` at the start of each booking-card render from
`booking.disruptions?.find((item) => item.status !== "resolved")`.

- [ ] **Step 5: Build and manually verify routes**

Verify `/watches`, `/watches/new`, `/deals/:id`, and `/bookings`.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/pages/WatchesPage.tsx frontend/src/components/watch/WatchForm.tsx frontend/src/pages/DealReviewPage.tsx frontend/src/pages/BookingsPage.tsx
git commit -m "Streamline core travel workflows"
```

---

### Task 11: Capture Value-First Screenshots and Rewrite README

**Files:**
- Create: `frontend/scripts/capture-screenshots.mjs`
- Modify: `frontend/package.json`
- Create: `docs/screenshots/*.png`
- Modify: `README.md`
- Modify: `docs/runbook.md`
- Modify: `travel-autobook-spec.md`

- [ ] **Step 1: Add Playwright**

Run:

```bash
cd frontend
npm install --save-dev @playwright/test
npx playwright install chromium
```

- [ ] **Step 2: Write deterministic capture script**

Start Vite in mock mode, wait for the port, then use Chromium at 1440 by 1000. Capture:

```javascript
await capture("/watches", "../docs/screenshots/01-watches-dashboard.png");
await capture("/deals/deal-118400?watchId=tokyo-singapore", "../docs/screenshots/02-deal-review.png");
await capture("/admin/integrations/flights", "../docs/screenshots/03-admin-integrations.png");
await capture("/profile", "../docs/screenshots/04-household-workspace.png");
```

The script must wait for page headings and disable repeating reward animation before capture.

- [ ] **Step 3: Capture screenshots**

Run:

```bash
cd frontend
VITE_API_MODE=mock npm run dev -- --host 127.0.0.1
node scripts/capture-screenshots.mjs
```

Expected: four non-empty PNG files with no secrets.

- [ ] **Step 4: Rewrite README value-first**

Add:

- `TRAMP = Travel Amplifier`
- concise value proposition
- the four screenshots with captions
- quick start
- inline Admin API workflow
- official provider links
- one-stamp butterfly explanation
- mock mode and selective purge
- link to runbook

- [ ] **Step 5: Update runbook and architecture spec**

Document purge commands, stamp ledger, booking flow, and screenshot refresh command.

- [ ] **Step 6: Build and commit**

```bash
git add frontend/package.json frontend/package-lock.json frontend/scripts/capture-screenshots.mjs docs/screenshots README.md docs/runbook.md travel-autobook-spec.md
git commit -m "Document Travel Amplifier release"
```

---

### Task 12: Final QA, Publication, and Remote Cleanup

**Files:**
- Verify all changed files
- Do not add local backups or SQLite fixtures

- [ ] **Step 1: Run backend tests**

Run the full Docker-mounted Pytest suite.

Expected: zero failures.

- [ ] **Step 2: Run changed-file Ruff**

Run Ruff against every changed backend and test file.

Expected: `All checks passed!`

- [ ] **Step 3: Run frontend verification**

```bash
cd frontend
npm run check:copy
npm run build
node scripts/capture-screenshots.mjs --smoke
```

Expected: copy check, TypeScript, Vite, and browser smoke pass.

- [ ] **Step 4: Validate operations**

```bash
INITIAL_ADMIN_EMAIL=admin@example.com \
INITIAL_ADMIN_PASSWORD=test-admin-password \
APP_SECRET=test-secret-with-at-least-thirty-two-bytes \
docker compose config --quiet
git diff --check
```

Expected: both commands return zero.

- [ ] **Step 5: Run secret and long-dash scans**

Search tracked content for the known removed credential patterns and scan `frontend/src` plus `frontend/index.html` for Unicode em dash and en dash.

Expected: no matches.

- [ ] **Step 6: Review staged scope**

Confirm the SQLite fixture, `.superpowers`, backup directory, and unrelated admin plan are absent from `git status --short` staged output.

- [ ] **Step 7: Push the verified feature branch**

```bash
git push origin feature/tramp-rewards-operations
```

- [ ] **Step 8: Publish to main**

Because the feature branch is based on sanitized `origin/main`, push by fast-forward:

```bash
git fetch origin main
git merge-base --is-ancestor origin/main HEAD
git push origin HEAD:main
```

Expected: fast-forward update.

- [ ] **Step 9: Verify GitHub**

Use `gh repo view`, `gh api repos/TheShazam88/tramp/commits/main`, and README fetch to verify:

- public visibility
- default branch `main`
- expected release commit
- screenshots render
- no legacy secret history was introduced

- [ ] **Step 10: Remove remote working branches**

After main verification:

```bash
git push origin --delete cursor/initial-tramp-app
git push origin --delete feature/tramp-rewards-operations
```

Expected: only `main` remains remotely. Keep local legacy and feature branches.

---

## Plan Self-Review Checklist

- [ ] Every approved design requirement maps to a task.
- [ ] One stamp is awarded per successful live booking.
- [ ] The approved rounder butterfly and livelier flutter are specified.
- [ ] The black `T` remains installed-app branding only.
- [ ] API guides are structured and use official URLs.
- [ ] Purge is preview-first and the confirmation phrase is copyable.
- [ ] Test purge preserves setup, watches, live activity, and stamps.
- [ ] User-facing long dashes are blocked.
- [ ] Screenshots and README use the value-first order.
- [ ] Legacy backup is outside the repository.
- [ ] Remote Cursor branch removal happens only after verified main publication.
