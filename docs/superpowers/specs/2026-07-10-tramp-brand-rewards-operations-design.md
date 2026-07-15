# TRAMP Brand, Rewards, Operations, and Release Design

> **Copy-guard cancellation (2026-07-15):** The user explicitly cancelled the user-facing copy-guard task. No scanner, package command, build gate, or copy-specific required QA remains in scope. Normal clipboard support is unchanged, including the `PurgeTestDataPanel` copy button.

## Goal

Ship a cohesive release that preserves the established TRAMP interface while adding:

- Editorial Gold `TRAMP` wordmark
- `Travel Amplifier` brand meaning
- one TRAMP-Stamp per successful live booking
- ornate blue and gold butterfly reward animation
- inline API credential acquisition guidance
- selective admin purge of generated test activity
- focused usability improvements
- value-first product screenshots and README documentation
- verified GitHub publication with a local legacy backup

## Scope and Design Lock

The current visual system remains unchanged:

- cream canvas and page background
- white surfaces
- blue value accents
- gold luxury accents
- rust alert accents
- Spectral and Georgia display typography
- existing rounded cards, controls, navigation, and page layouts

The black and gold `T` remains the installed app icon, favicon, and PWA icon. It is removed only from the authenticated top bar.

## 1. Brand Header

Replace the top-bar icon with the existing Editorial Gold text wordmark:

- `TRAMP` in the current Georgia gold treatment
- `TRAVEL AMPLIFIER` beneath it in a compact blue uppercase label
- current contextual tagline retained below or beside the subtitle where space allows
- stamp balance displayed as a compact luxury badge near header actions

The login wordmark remains text-based and receives the `Travel Amplifier` subtitle for consistency.

## 2. TRAMP-Stamps

### Earning rule

Award exactly one TRAMP-Stamp when a non-simulated booking is successfully created. Do not award for:

- mock or test providers
- simulated payloads
- failed booking attempts
- deal confirmation without booking
- idempotent booking replays
- cancellations

Cancellation does not remove an earned stamp in this release.

### Data model

Add `tramp_stamp_ledger`:

- `id`
- `user_id`, foreign key to users
- `booking_id`, unique foreign key to bookings
- `amount`, constrained to `1`
- `reason`, fixed to `live_booking_completed`
- `awarded_at`
- `meta_json` containing deal, watch, and provider references

The displayed balance is calculated from ledger entries. A separate cached counter is intentionally omitted to prevent drift.

### Transaction flow

Inside `approve_and_book()`:

1. validate deal, approval token, TOTP, payment, and guardrails
2. execute the provider booking
3. reject simulated providers and payloads when live booking is required
4. create the booking, spend entry, audit entry, and stamp ledger row
5. commit once
6. return booking data with `tramp_stamps_awarded` and `tramp_stamp_balance`

The unique booking constraint guarantees at-most-once awards.

### Frontend booking correction

Replace the confirmation-only `Book now` behavior with the existing real booking endpoint:

- select a saved payment method
- enter TOTP
- enter the master-key passphrase when required
- generate an approval token
- submit to `/bookings/approve` with an idempotency key
- show booking result and refresh deal, bookings, profile, and dashboard queries

The confirmation-intent endpoint remains available for notification workflows but is no longer the primary in-app booking action.

## 3. Butterfly Emblem and Animation

Create a reusable SVG and React component inspired by the user-provided butterfly reference:

- rounded broad upper wings
- long lower wing tails
- curled ornamental markings
- deep blue wing gradient
- metallic gold outline and detailing
- gold body with blue edge

Animation sequence:

1. butterfly enters from above in top-down perspective
2. three quick wing beats during descent
3. landing settles at screen center
4. two smaller settling flutters
5. wings remain fully open
6. `+1 TRAMP-Stamp` and updated balance appear
7. animation fades without blocking navigation

The animation runs once only when the booking response reports a new award. `prefers-reduced-motion` shows the final static pose and count update.

## 4. Inline API Acquisition Guidance

Extend integration catalog entries with structured acquisition information:

- official signup URL
- application creation URL where different
- account or approval requirements
- ordered setup steps
- test versus production availability
- TRAMP capabilities enabled by that provider
- credential-specific notes

Render a collapsed `How to get credentials` panel above each provider credential form. The panel uses existing disclosure, notice, helper-copy, and button styles.

The expected sequence is:

1. open official provider portal
2. create or approve an account
3. create an API application
4. copy credentials
5. select test or live in TRAMP
6. save credentials
7. run the existing connection test

README mirrors the same guidance and links to the Admin UI. Secrets are never added to README or committed environment files.

## 5. Selective Test-Data Purge

### API

Add admin-only endpoints:

- preview simulated activity purge
- execute simulated activity purge

Preview returns exact counts and performs no mutation.

Execution requires the confirmation phrase `PURGE TEST DATA`. The UI displays the phrase in a read-only field with a copy button, then requires it to be pasted or typed into a separate confirmation input.

### Deletion scope

Delete generated simulated activity in foreign-key-safe order:

- notification deliveries tied to simulated activity
- manual test disruptions
- simulated cancellations
- simulated booking attempts and bookings
- associated spend entries
- simulated deal feedback and learning state
- simulated deals
- simulated price observations
- derived price statistics, which rebuild on later searches
- related test audit events

Preserve:

- users
- travelers and loyalty accounts
- traveler groups
- preferences
- payment methods
- trip templates
- watch definitions and traveler links
- live deals and bookings
- stamp ledger
- integration credentials and profiles

Affected fulfilled watches return to active only when no real booked deal remains.

### Transaction and audit

Run purge in one transaction. Return per-table deletion counts and watch reset counts. Add a new audit event after deletion with the administrator and summary.

## 6. Focused Usability Improvements

- Make watch readiness blockers link to the exact profile or integration page that resolves them.
- Collapse advanced watch fields by default.
- Auto-open secure booking review when a valid signed approval link is present.
- Move disruption simulation into a collapsed `Local test tools` section.
- Preserve all existing controls and advanced options.

## 7. Screenshots and README

Capture screenshots from a local mock-mode session using the established visual system:

1. watch dashboard
2. deal review with readiness and timeline
3. Admin Integrations with inline credential guidance
4. household workspace

README order:

1. Editorial Gold brand and `TRAMP = Travel Amplifier`
2. concise value proposition
3. screenshots
4. core capabilities
5. quick start
6. provider API acquisition guide
7. TRAMP-Stamps explanation
8. mock mode and purge behavior
9. verification and operations links

Screenshots are demonstration data and are labeled as such.

## 8. Error Handling

- Stamp insertion conflicts return the existing award rather than duplicating it.
- Booking errors do not animate or award.
- Purge preview and execution require admin authentication.
- Purge confirmation mismatch returns HTTP 400.
- Purge transaction failures roll back all deletions.
- Provider-guide links open in a new tab with safe rel attributes.
- Frontend mutations display existing notice patterns and invalidate affected queries.

## 9. Verification

Backend:

- migration upgrade
- full Pytest suite
- stamp eligibility, idempotency, and exclusion tests
- purge preview, execution, preservation, and rollback tests
- booking endpoint flow tests
- changed-file Ruff checks

Frontend:

- TypeScript and Vite production build
- booking form behavior
- animation trigger and reduced-motion behavior
- purge confirmation and copy button
- provider disclosure rendering
- screenshot route smoke tests

Operations:

- Docker Compose validation
- API health smoke test
- mock-off visibility verification
- `git diff --check`
- secret scan for known credential patterns

## 10. Backup and GitHub Release

Before implementation:

- create a timestamped Git bundle of the legacy local branch
- copy the local SQLite fixture into the backup directory
- store backups outside the repository

After verification:

- commit only relevant source, migration, test, screenshot, and documentation files
- publish a sanitized commit to public `main`
- verify remote file and commit metadata
- delete remote `cursor/initial-tramp-app`
- retain the local legacy branch and backup files

The existing untracked admin integration plan and modified SQLite fixture remain excluded from release commits.
