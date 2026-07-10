# Autonomous Travel Watch & Booking System — Build Specification

> **This document is the single source of truth.** It is written to be handed to Cursor whole: "Read this spec and build all of it." Everything needed — architecture, data model, flows, algorithms, providers, design system, env, and a master build prompt (§21) — is here. A suggested build order (§20) is guidance, not a prerequisite.

**Product north star:** *Maximum luxury for minimum cost.* Find the **best quality-per-dollar** within the user's constraints — not merely the cheapest. For every trip, surface *the most luxury within budget* and *the cheapest option that still clears the quality floor.*

**What it does:** A self-hosted (Docker) web app that monitors flight + hotel + car prices for trips the user defines, ranks by value, alerts (email/Telegram), books via legitimate APIs on one-tap approval, auto-fills the right frequent-flyer numbers (alliance-aware), uses encrypted payment details, learns from rejections, respects hard spend limits, uses price history intelligently, and is deliberately simple to use.

**Core design decision — API-first, not scraper-first.** Continuously crawling Google Flights / Booking / Airbnb behind NordVPN and auto-filling cards into their checkout is fragile, breaks ToS, gets fraud-flagged, and — for Airbnb — is impossible (no booking API). We **fan out across real booking + metasearch APIs**. Scraping is an optional, off-by-default, price-signal layer only.

---

## 1. User Journey (deliberately small, one-tap where it counts)

**Set up once (Profiles, §7):** add your household — yourself, partner, kids — each with passport details, ages, frequent-flyer/hotel numbers, seat/meal preferences. Add payment once (encrypted). Set default preferences (home airports, preferred cabin, airlines, the luxury⇄savings default). The profile also exposes a **household workspace summary** so the user can instantly see traveler count, saved groups, payment readiness, passport gaps, and whether 2FA still blocks fast booking.

**Then, per trip:**
1. **New Watch** — pick *who's travelling* with one tap (a saved group like "Whole family", or individual travelers), then where, when (date or range + length), the **price range** (hard ceiling), and the **luxury⇄savings dial**. Preferences pre-fill everything else; advanced options (flight timing, refundable, Airbnb) sit under "More options."
2. The engine searches and optimizes for luxury within budget, using **price history** to aim for a genuinely good price (§10), and already knows the travelers, their FF numbers, payment, and preferences.
3. It **runs daily**; when something worthy appears it pings you (email/Telegram) with the value pick, the price *in historical context*, the FF numbers it will use, and a one-tap approval.
4. **Approve in one tap** (Telegram button or email link → login + TOTP → Confirm & book). It re-prices, books, attaches the correct alliance FF number, charges your card, adds it to your calendar, and watches for disruptions.

From alert to booked is effectively **one tap plus a code** — because the algorithm already holds the who/how/pay.

---

## 2. Feasibility Summary

| Capability | Verdict | How |
|---|---|---|
| Profiles: household, travelers, saved preferences, groups | ✅ Easy | §6, §7 |
| Select who you're booking for, per trip | ✅ Easy | traveler groups / picks (§7) |
| Alliance-aware frequent-flyer auto-fill (e.g. KLM # on a Delta booking) | ✅ Mostly | alliance map + Duffel loyalty accounts; manual fallback (§7.4) |
| Advanced timing (outbound/return time windows, avoid red-eye) | ✅ Easy | watch fields + filter/score (§7, §10) |
| Price monitoring — flights / hotels | ✅ Robust | Amadeus, Duffel(+NDC), Kiwi, Travelpayouts / EPS, Booking, Hotelbeds, Amadeus |
| Value ranking — luxury per dollar | ✅ Core | §9 |
| Smart price range + history | ✅ Core | §10 |
| Learn from rejections (preference vs value) | ✅ Core | §8.4 |
| Hard spend guardrails | ✅ Core | §11 |
| Alerts via email + Telegram (one-tap) | ✅ Easy | §12 |
| Auto-book flight / hotel after approval | ✅ Possible | Duffel order / EPS·Booking·Hotelbeds |
| Calendar push + disruption handling | ✅ Possible | Google Calendar + provider webhooks |
| Passport/visa sanity checks | ✅ Advisory | §8.6 |
| Encrypted local payment storage | ✅ Possible | Vault / libsodium (§14) |
| Truly exhaustive (every price everywhere) | ❌ Impossible | no single source has all inventory (§13) |
| Auto-book Airbnb | ❌ Not possible | no public booking API; discovery-only toggle (§8.5) |
| Scraping + saved-card booking on arbitrary sites | ❌ Avoid | breaks, ToS, fraud flags |
| NordVPN to evade anti-bot | ❌ Counterproductive | VPN IPs pre-flagged; use residential proxies if ever needed |

---

## 3. Architecture

```
                ┌───────────────────────────────┐
                │          Web UI (React)        │  4 screens, one-tap (§17)
                │  Watches · New Watch · Deal    │
                │  review · Profile/Settings     │
                └───────────────┬────────────────┘
                                │ REST / WebSocket
                ┌───────────────▼────────────────┐
                │        Backend API (FastAPI)   │
                │  profiles · watches · deals    │
                │  value · pricing/timing        │
                │  guardrails · loyalty mapping  │
                │  preference model · approvals  │
                └──┬────────┬────────┬────────┬──┘
        ┌──────────▼─┐ ┌────▼────┐ ┌─▼──────┐ ┌▼──────────────┐
        │Scheduler/  │ │Postgres │ │ Vault  │ │ Notifications │
        │Worker      │ │         │ │secrets │ │ email+Telegram│
        │(Celery+Redis)│ │         │ │        │ │ +calendar push│
        └────┬───────┘ └─────────┘ └────────┘ └───────────────┘
             │
   ┌─────────▼──────────────────────────────────────────────┐
   │   Source Adapter Layer (FAN-OUT)                        │
   │   flights(book): Amadeus, Duffel(+NDC), Kiwi            │
   │   flights(signal): Travelpayouts / Skyscanner           │
   │   hotels(book): EPS, Booking, Hotelbeds, Amadeus        │
   │   cars: Amadeus / CarTrawler ; discovery: Airbnb(opt)   │
   └─────────┬───────────────────────────────────────────────┘
             │ normalized offers + rolling price history
   ┌─────────▼───────────┐
   │ Value (§9) + Pricing│ apply targets/glide (§10), preferences (§7),
   │ /Timing + Preference│ acceptance band + suppression (§8.4)
   └─────────┬───────────┘
             │ proposes (never spends)   ┌────────────────────┐
   ┌─────────▼───────────┐               │ Agent (LLM): explain│
   │ Eligible candidates ├──────────────►│ tradeoffs, summary  │ no money/secrets
   └─────────┬───────────┘               └────────────────────┘
             │ signed approval + guardrail check (§11) + loyalty mapping (§7.4)
   ┌─────────▼─────────────────────────────────┐
   │ Booking Executor (DETERMINISTIC) → book,   │
   │ attach FF#, charge, calendar, disruptions  │
   └─────────────────────────────────────────────┘
```

**Principle: agents propose, deterministic code disposes.** LLM/value layers search, rank, explain. Booking is plain, auditable code behind signed approval + §11 guardrails; it never lets the LLM move money or see decrypted secrets.

---

## 4. Tech Stack

Backend: Python 3.12, FastAPI, Pydantic v2, SQLAlchemy 2.x · Jobs: Celery + Redis · DB: PostgreSQL 16 · Frontend: React + Vite + TypeScript + TanStack Query (theme = §17) · Agent: LangGraph → Anthropic API (explanations only) · Notifications: SES/Postmark + Telegram Bot API · Calendar: Google Calendar API · Scrape (optional): Playwright · Secrets: HashiCorp Vault or libsodium + runtime master key (§14) · Container: Docker + docker-compose (api, worker, beat, postgres, redis, vault, frontend, caddy, optional gluetun) · TLS: Caddy · Auth: multi-user with roles (admin/user) — sign-up, session + password + TOTP (§7.0).

---

## 5. Providers (tiered — maximize coverage)

Apply early; some need a business entity + KYC. **Flights — bookable:** Duffel (search→offer→order, NDC airline-direct, `loyalty_programme_accounts`, bags/seats; test free, live needs business+funding — primary booking), Amadeus Self-Service (free test + monthly prod quota; primary monitoring), Kiwi/Tequila (virtual interlining, LCCs). **Flights — signal:** Travelpayouts / Skyscanner affiliate (metasearch breadth + deep links; the legitimate substitute for scraping Google Flights). **Hotels — bookable (best-of):** Expedia Rapid, Booking Demand, Hotelbeds APItude (net rates), Amadeus Hotel. **Cars:** Amadeus / CarTrawler. **Notify/calendar:** Telegram Bot API, Google Calendar API. **Out of scope for booking:** Airbnb/Vrbo (Airbnb discovery-only, §8.5); luxury rate programs (Amex FHR, Virtuoso) — named as gaps (§13).

---

## 6. Data Model (Postgres)

```
users
  id, email, password_hash, totp_secret,
  role(admin|user),                   # admin manages platform integrations + feature flags (§7.6); also has a normal profile
  onboarding_completed(bool),
  default_notify_channel(email|telegram|both), telegram_chat_id,
  global_max_auto_book_amount, weekly_max_spend, weekly_max_bookings,
  annual_travel_budget, annual_budget_currency,   # optional yearly cap tracked across all watches (§Roadmap)
  google_calendar_token_ref, created_at

platform_integrations                  # ADMIN-managed, encrypted; overrides env at runtime (§7.6, §14)
  id, key(amadeus|duffel|kiwi|travelpayouts|eps|booking|hotelbeds|telegram|google_calendar|anthropic|airbnb_dataapi|proxy|...),
  encrypted_credentials,               # client id/secret/token(s)
  environment(test|live), enabled(bool), feature_flags_json, updated_by, updated_at

travelers                              # the household — define once, reuse (§7)
  id, user_id, relationship(self|partner|child|other), display_name,
  legal_first_name, legal_last_name, dob, gender, nationality, residency_country,
  passport_number_enc, passport_country, passport_expiry,
  known_traveler_number, redress_number,
  seat_pref(aisle|window|extra_legroom|no_pref), meal_pref, accessibility_needs,
  infant_on_lap(bool), created_at
  # NOTE: age (adult/child/infant) is derived from dob at travel date for correct fare types

loyalty_accounts
  id, traveler_id, program_type(airline|hotel|car|alliance),
  program_code,                        # e.g. "AF"(Flying Blue), "AA"(AAdvantage), "BA"(Avios)
  alliance(star|oneworld|skyteam|none),
  account_number, status_tier, preferred_earning_for_alliance(bool)

traveler_groups                        # one-tap presets for "who's travelling"
  id, user_id, name, traveler_ids[]
  # API also returns a derived household workspace summary:
  # traveler_count, traveler_group_count, payment_method_count, template_count,
  # passport_gap_count, has_self_traveler, has_payment_method, totp_enabled,
  # setup_warnings[], readiness_label

user_preferences                       # defaults applied to new watches + algorithm weights (§7.3)
  id, user_id, home_airports[], default_cabin, default_luxury_vs_savings,
  preferred_airlines[], avoided_airlines[], preferred_alliances[],
  preferred_hotel_brands[], avoided_hotel_brands[], default_hotel_min_rating,
  avoid_redeye(bool), default_max_layover_minutes, default_min_connection_minutes,
  default_outbound_window_json, default_return_window_json,
  prefer_refundable(bool), seat_auto_select(bool),
  default_notify_channel(inherit|email|telegram|both), quiet_hours_start, quiet_hours_end

trip_templates                         # save a watch config to relaunch (annual trips etc.)
  id, user_id, name, watch_payload_json

payment_methods                        # encrypted; see §14
  id, user_id, label, brand, last4, encrypted_blob, provider_token, billing_address_enc

trip_watches
  id, user_id, status(active|paused|fulfilled),
  trip_mode(flights_then_hotels|flights_only|hotels_only),
  traveler_group_id,                   # plus watch_travelers for explicit picks
  origin_iatas[], destination_iatas[],
  destination_mode(fixed|flexible), flexible_region, flexible_theme,   # "anywhere warm/beach/city under budget" (§Roadmap)
  depart_date_from, depart_date_to, return_date_from, return_date_to,
  trip_min_nights, trip_max_nights,
  cabin_class, max_stops, max_layover_minutes, min_connection_minutes,
  preferred_airlines[], preferred_alliances[], avoid_redeye(bool),
  -- ADVANCED TIMING (per direction) --
  outbound_earliest_depart, outbound_latest_depart, outbound_arrive_by,
  return_earliest_depart, return_latest_depart, return_arrive_by,
  -- BUDGET (hard) --
  flight_budget_max, hotel_budget_per_night_max, max_total_trip_spend, budget_currency,
  -- PRICING & TIMING (§10) --
  ideal_price, glide_start_days(default 42), glide_end_days(default 3),
  -- VALUE (§9) --
  quality_floor(0-100), luxury_vs_savings(0-1),
  hotel_min_rating, hotel_area_lat, hotel_area_lng, hotel_radius_km,
  prefer_refundable(bool), loyalty_weighting(0-1),
  -- LEARNED STATE (§8.4) --
  value_target, band_tolerance(default 0.10), value_pressure(0-1),
  -- AIRBNB (§8.5) --
  include_airbnb(bool default false), airbnb_disclosure_ack_at,
  -- OPS --
  refresh_interval(daily|6h|hourly default daily),
  notify_channel(inherit|email|telegram|both), want_car(bool),
  auto_book_mode(always_confirm|auto_under_X), created_at, updated_at

watch_travelers   id, watch_id, traveler_id

price_observations  id, watch_id, kind(flight|hotel|car), source, observed_at, price, currency, payload_json, fingerprint_hash
# offers/deals also carry all-in pricing (§9): base_price, taxes_fees, ancillaries, fx_fee, all_in_price, home_currency
price_stats         id, scope_type(route_cabin|hotel_area), scope_key, month_bucket, p10, p25, median, p75, volatility, sample_n, updated_at
suppressed_attributes  id, watch_id, attr_type(airline|hotel_property|hotel_chain|area_cluster|routing_trait), attr_value, weight(0-1), created_at
rejected_fingerprints  id, watch_id, fingerprint_hash, created_at

deals
  id, watch_id, kind, source, total_price, currency,
  quality_index, value_score, price_percentile, timing_advice,
  framing(max_luxury|best_value|cheapest_ok),
  fingerprint_hash, summary_text, coverage_report_json, validation_warnings_json,
  loyalty_plan_json,                   # which FF program will be attached per traveler (§7.4)
  # API exposes additional derived layers per watch/deal:
  # readiness{score,label,blockers[],warnings[]}
  # badges[better than usual|target reached|timing weak|action needed]
  # cta_actions[open_deal|search_now|pause_watch|resume_watch|book_now|ignore]
  offer_ref, expires_at,
  status(proposed|confirmed|expired|booked|failed|rejected),
  rejected_reason, confirm_token_hash, payload_json, created_at

deal_feedback  id, watch_id, deal_id, rejected_value_score, reason, signal_type(value|preference|constraint|ambiguous), action_taken_json, created_at
bookings  id, deal_id, provider, provider_booking_ref, status(pending_ticketing|ticketed|booked|cancel_pending|cancelled|failed), idempotency_key, amount_charged, currency, documents_json, loyalty_attached_json, loyalty_manual_followup(bool), calendar_event_id, booked_at, error_text
cancellations  id, booking_id, reason, refund_expected, refund_received, currency, status(requested|processing|refunded|denied), requested_at, resolved_at
spend_ledger  id, user_id, watch_id, booking_id, amount, currency, booked_at
disruptions  id, booking_id, type(schedule_change|cancellation|better_deal_in_free_window), detail_json, detected_at, status(new|notified|resolved)
audit_log  id, actor, action, target, amount, currency, at, meta_json

# STATIC SEED DATA (config, not user data):
alliance_map        airline_iata -> alliance(star|oneworld|skyteam|none)   # maintain a complete map
```

---

## 7. Profiles, Travelers & Preferences

The profile is what makes launching a trip one tap: the system already knows *who*, *their documents and loyalty numbers*, *how to pay*, and *what they like*.

### 7.0 Accounts, roles & onboarding
**Multi-user with two roles.** `user` — registers an account and manages their own household, watches, bookings, and payment. `admin` — everything a user can do (the admin also fills in their own profile and can book), **plus** manages platform-wide integrations and feature flags (§7.6). The first account created is the admin; admins can invite or approve further users (open self-sign-up is a config flag, off by default).
**Sign-up & auth:** email + password + TOTP enrolment; per-user data is strictly scoped by `user_id`; users never see platform credentials or other users' data.
**Onboarding (collect the minimum, defer the rest).** A short wizard gets a new user to their first watch fast, then lets them enrich later:
1. Account + TOTP. 2. Add yourself as the first traveler (name as on passport, DOB, nationality) — passport number can be added later, it's only needed before a flight books. 3. Add one payment method (or skip — required only before booking). 4. Set 2–3 preferences (home airports, luxury⇄savings default, notify channel). 5. Optional "create your first watch" hand-off.
The wizard writes `onboarding_completed`; everything skipped is surfaced later as a gentle "finish setup" nudge on the relevant screen (e.g. "add a passport before this can book"). Nothing blocks browsing/monitoring; only the booking step enforces the data it truly needs.

### 7.1 Household & travelers
Define each person once in `travelers`: legal name (exactly as on passport), DOB (used to derive adult/child/infant fare type at travel date), gender, nationality, residency, passport number/expiry, Known Traveler / redress numbers, and per-person seat/meal/accessibility preferences. Add their loyalty accounts (airline/hotel/car) with status tiers.

The profile API should also return a **derived household workspace summary** so setup status is obvious without opening every form. That summary is deterministic and includes traveler count, saved traveler-group count, payment-method count, passport-gap count, TOTP enabled/disabled, and human-readable setup warnings that can later feed booking-readiness explanations.

### 7.2 Selecting who's travelling (per trip)
On a watch, choose travelers via a one-tap **group** (`traveler_groups`, e.g. "Whole family", "Me + partner") or pick individuals (`watch_travelers`). This sets passenger counts and ages, supplies passports for booking and validation, and determines which loyalty numbers get attached. Groups are the fast path; most trips are one tap.

Traveler groups must feel like first-class reusable presets, not hidden metadata. The profile/presets surface should let the user create, edit, and remove groups directly, and the watch editor should continue to consume those groups as the main "who is travelling" shortcut.

### 7.3 Saved preferences feed the algorithm
`user_preferences` pre-fills new watches and biases scoring: home airports (origin auto-fill), default cabin and luxury⇄savings, preferred/avoided airlines and alliances, preferred/avoided hotel brands, min hotel rating, red-eye avoidance, layover/connection limits, default departure/arrival time windows, refundable preference, and whether to auto-select preferred seats. Preferred items add to the quality index; avoided items act as soft suppressions (§8.4). The user can always override per watch.

### 7.4 Alliance-aware frequent-flyer auto-fill (the loyalty mapper)
At proposal and again at booking, for each traveler the system selects the **best loyalty account to attach**, given the flight's marketing/operating carrier:
1. If the traveler holds a program for **that exact airline**, use it.
2. Else resolve the airline's **alliance** via `alliance_map`; among the traveler's accounts in that alliance, pick by priority: (a) one flagged `preferred_earning_for_alliance`, (b) one where they hold `status_tier`, (c) otherwise any. *(Example: booking Delta → SkyTeam → attach the traveler's KLM/Air France Flying Blue number.)*
3. Pass it via Duffel `loyalty_programme_accounts` per passenger. Record the plan in `deals.loyalty_plan_json` and `bookings.loyalty_attached_json`.
**Honest caveats (surface, don't hide):** cross-partner accrual isn't universally accepted via API — some carriers/NDC offers reject a partner number, and deep-discount fare classes may earn little or nothing (an airline rule). If the carrier rejects the number at booking, set `loyalty_manual_followup = true` and notify: "add your KLM number to this Delta reservation manually." The user can also override the chosen program before approving.

### 7.5 Reusability
`trip_templates` let the user save and relaunch a watch config (e.g. an annual family trip). Other usability features baked in: home-airport auto-fill, one-tap traveler groups, defaults from preferences, pause/resume a watch, and duplicate-a-watch.

### 7.6 Admin console — integrations & platform settings (admin only)
So the admin can manage features without touching the server, a dedicated **Admin** area lets them enter and manage **all provider API credentials in the interface** (stored encrypted in `platform_integrations`, §14): Amadeus, Duffel, Kiwi, Travelpayouts/Skyscanner, Expedia Rapid, Booking, Hotelbeds, cars, Telegram bot, Google Calendar, Anthropic, Airbnb data API, residential proxy. For each integration: paste credentials, choose `test`/`live`, enable/disable, see a **live "test connection"** status, and flip **feature flags** (which adapters are active, scrape/Airbnb layer on/off, auto-book availability, default guardrails). **Precedence:** values entered here override the `.env` bootstrap values at runtime, so the platform can be configured and reconfigured entirely from the UI; env is only the initial seed / fallback. Credentials are encrypted with the same master key/Vault as payment data, are write-only in the UI (shown masked, never echoed back in full), and are never exposed to non-admin users, the agent/LLM, or logs. The admin area also surfaces platform health (§15): per-adapter status, quota usage vs free tiers, and the booking audit log.

---

## 8. Core Flows

### 8.1 Monitoring (scheduler → worker)
Enqueue each `active` watch on its `refresh_interval` (**default daily**). Fan out across adapters in parallel; normalize → `price_observations` (+ `fingerprint_hash`); update `price_stats`. Ranges → cheapest-date search; combinations → Kiwi filtered by stops/layover/`min_connection_minutes`; **apply timing windows** (outbound/return earliest/latest depart, arrive-by, `avoid_redeye`). Dedup identical offers. Score (§9), apply pricing/timing (§10) and eligibility (§8.4), validate (§8.6), summarize, alert.

### 8.2 Alert + approval
Auto-generate a unique, HMAC-signed, **single-use**, ~30-min approval token per proposed plan (can bundle flight+hotel). Deliver via chosen channel (§12): Telegram message with **Confirm/Reject** buttons and/or email signed link → confirm step requires login + TOTP, shows the breakdown, the FF program to be attached per traveler, the historical price context, the coverage report, and any validation warnings → one **Confirm & book** + **Reject** with reasons. Confirming consumes the token; reject/expiry invalidates it.

### 8.3 Booking executor (deterministic, post-approval)
Re-validate + re-price the live offer → **guardrail check (§11)** → **obtain the data key per `KEY_UNLOCK_MODE` (§14)** (in `master_key` mode the master key entered at this approval; in `auto` mode the resident key) → decrypt payment/traveler data in memory → resolve **loyalty mapping (§7.4)** per traveler → Duffel `order` create (passengers, ages, KTN/redress, `loyalty_programme_accounts`, seats/meals if `seat_auto_select`/`meal_pref`, services) / best-of hotel booking → persist `bookings` + `spend_ledger` + `audit_log` → **push to Google Calendar** → notify → zeroize secrets and key. **Trip-mode sequencing:** flights_then_hotels (hotels gated until flight booked; dates lock nights) · hotels_only (skip flights) · flights_only. On failure: never silently retry a charge.

**Booking integrity (money-correctness — required):**
- **Idempotency:** every order-create call carries an idempotency key derived from `deal_id`; retries/timeouts can never double-book or double-charge.
- **Bundle saga / compensation:** for a flight+hotel plan, book sequentially and define rollback — if the flight books but the hotel fails, do **not** silently leave a half-booked trip: notify immediately, hold the flight, and offer to retry the hotel or cancel the flight within its void/free-cancel window (never auto-cancel a booked flight without approval).
- **Ticketing reconciliation:** an order being "created" ≠ "ticketed." Poll/verify the PNR reaches ticketed status with a ticket number; surface `pending_ticketing` and alert if it doesn't resolve.
- **APIS / Secure Flight compliance:** pass the required Advance Passenger Information (passport, DOB, gender, nationality) to carriers; enforce that passenger names exactly match passports (block on mismatch). This is mandatory for real ticketing, not optional polish.

### 8.4 Rejection feedback — value vs preference (acceptance band, not a hard floor)
Always store the offer fingerprint (never re-propose the identical thing) + log feedback. **Preference** (wrong_airline|wrong_hotel|wrong_area) → add `suppressed_attributes`; **value band untouched** (similar-value options that avoid the trait stay eligible). **Constraint** (layover) → tighten it. **Value** (too_pricey → raise `value_pressure`; not_luxe → raise `quality_floor`). **Ambiguous/bare no** → mild nudge, escalate on repeats. Eligibility: `price ≤ ceiling` AND `quality ≥ quality_floor` AND `value_score ≥ band_low` (=`value_target×(1−band_tolerance)`, lifted by `value_pressure`) AND not a rejected fingerprint AND not a hard-suppressed attribute (soft suppression subtracts weight first). Anti-nag: alert only on a distinct eligible candidate; never require strictly beating the last.

### 8.5 Airbnb — optional discovery toggle (`include_airbnb`)
No booking API → cannot be auto-booked; toggle adds it for **discovery only**. Sources (no official API needed): third-party Airbnb data API (Apify/RapidAPI-style — **default**, most robust), self-hosted Playwright scraper (fallback), analytics datasets (area context). All data-only and ToS-grey. Listings scored on the hotel quality index and shown in the same value-ranked alert; **booking is a manual deep link**. Turning it on requires an acknowledged disclosure (`airbnb_disclosure_ack_at`). The only official Airbnb API is supply-side (Partner/Connectivity, for managing your own listings) — not a traveler booking API.

### 8.6 Pre-proposal validation (passport / visa / calendar — advisory)
Check each selected traveler's passport expiry vs travel date (warn if <6 months remaining); flag likely visa requirement for destination/nationality (uses `residency_country` too). **Calendar conflict check:** if Google Calendar is connected, cross-check proposed dates against the user's calendar and flag (or de-prioritize) trips that overlap existing commitments — don't book over a conflict without acknowledgement. Warnings ride in `validation_warnings_json` + the notification. Advisory only; hard issues (expired passport) require acknowledgement before booking.

### 8.7 Post-booking disruption handling
Subscribe to provider webhooks (Duffel order changes; hotel cancellations) + poll where unavailable. On change/cancellation → notify, summarize, offer a rebooking search; never auto-rebook without approval. Free-cancellation tracker: if a better deal appears while a refundable booking is inside its free-cancel window, alert "cheaper option found — cancel & rebook?" (manual confirm).

### 8.8 Cancellation & refunds (in-app)
Booking is only half a product — the user must be able to **unwind** it. From the booking detail, show the cancellation policy and any refund/void window, and allow the user to cancel within policy (flights via Duffel order cancel/void; hotels via the supplier's cancel endpoint). Track refund status to completion in `cancellations`, write `audit_log`, remove the calendar event, and reconcile the refund against `spend_ledger`. Cancellation is a money-moving action: same signed-approval + (in `master_key` mode) master-key gate as booking.

### 8.9 On-demand search ("find me something now")
Besides the daily cadence, a one-tap **Search now** on any watch runs the full pipeline immediately and returns the current best value with its historical context — for when the user is actively planning and doesn't want to wait for the next scheduled run.

### 8.10 Timeline, readiness, badges, and CTA metadata
Every watch/deal response should expose four extra derived layers so the frontend does not guess:

1. **Timeline API:** `PriceObservation` history is exposed as a compact deal/watch timeline with recent points, current price, target, glide limit, and a short trend summary.
2. **Booking readiness:** a deterministic score built from TOTP enabled, payment method present, traveler/passport completeness, deal state, watch state, and live-inventory availability. Return both `score` and structured `blockers` / `warnings`.
3. **Semantic badges:** derive a stable badge set from existing score/timing/price signals:
   - `better than usual`
   - `target reached`
   - `timing weak`
   - `action needed`
4. **CTA metadata:** watch/deal payloads should explicitly describe the intended actions (`open_deal`, `search_now`, `pause_watch`, `resume_watch`, `book_now`, `ignore`) so the frontend renders the platform's recommendation instead of inferring it ad hoc.

`Book now` still routes into the existing secure review / TOTP approval path. It is a stronger label for the same guarded flow, not a bypass.

---

## 9. Value Scoring Engine — "maximum luxury for minimum cost"

**Quality index (0–100)** — *flights:* cabin, fewer stops, duration vs great-circle, layover comfort, carrier rating, redeye penalty (heavier if `avoid_redeye`), baggage; **+ refundability bonus** if `prefer_refundable`; **+ loyalty bonus** scaled by `loyalty_weighting` for carriers where the traveler earns/holds status; **+ preference bonus** for preferred airlines/timing, soft penalty for avoided ones. *Hotels:* stars, reviews, distance to point, amenities, room category, brand tier (+/− for preferred/avoided brands).
```
value_score = quality_index / (price_normalized ^ price_sensitivity)
```
`price_sensitivity` from `luxury_vs_savings` + `value_pressure`. **Three framings shown:** Best value (headline) · Max luxury in budget · Cheapest acceptable. **Dial** slides splurge↔thrift (default 0.6). **Hotel envelope:** total = per-night × nights; maximize quality across the whole stay.

**All-in price normalization (critical for a value product).** Compare and rank on **true total cost**, not headline fare/rate, or the engine will recommend "cheap" options that aren't. Normalize each option to include: taxes & carrier-imposed fees; **the ancillaries the traveler actually needs** (e.g. a checked bag per `seat_pref`/profile, seat selection if `seat_auto_select`); hotel resort fees + city/occupancy taxes; and **FX/payment fees** when the fare is in a foreign currency (convert to home currency and add the card's typical FX margin). Store `base_price`, `taxes_fees`, `ancillaries`, `fx_fee`, and `all_in_price` on the offer; budgets, targets (§10), and `value_score` all run on `all_in_price`. Show the all-in number to the user with a one-line breakdown.

---

## 10. Pricing & Timing Methodology — using the range + history well

**Three reference points, not one.** **Ceiling (hard):** the price-range max — inviolable, never proposed/booked above. **Target (smart):** a historically good price aimed for first — default **p25** of the band for `route+cabin+month` (or `hotel-area+month`); override with `ideal_price`. **Quality floor:** minimum luxury (§9).
`price_stats` holds rolling p10/p25/median/p75 + volatility per scope/month (seeded by observation; backfill from provider historical/seasonal endpoints where available).
1. **Percentile-aware alerting:** alert when under ceiling AND ≥ quality floor AND ≤ target (~p25) — good *for this route*, not merely affordable.
2. **Deadline glide:** if no target-level deal appears, relax acceptance from target toward ceiling on a schedule (`glide_start_days`→`glide_end_days`, default 42→3). Hold out early, never miss the trip, never breach the cap.
3. **Book-now vs wait (honest heuristic):** percentile + days-to-departure + volatility → plain advice ("p8, 5 weeks out → book" vs "mid-band, 3 months, volatile → holding"). Stored as `timing_advice`.
4. **Error-fare flag:** far below p10 (robust z-score) → high-priority "may vanish fast" alert.
5. **Context on every deal:** "¥118,400 — cheapest ~8% seen for HND–SIN business in 90 days; typical ¥150–210k; usually rises 6 weeks out."

---

## 11. Spend Guardrails (hard limits, independent of value)

Checked after re-pricing, before any charge: per-watch `flight_budget_max`, `hotel_budget_per_night_max`, `max_total_trip_spend`; global `global_max_auto_book_amount` (no single auto-booking above it, ever, regardless of `auto_book_mode`); rolling `weekly_max_spend` / `weekly_max_bookings` (tracked in `spend_ledger`). Any breach → drop to manual confirm or skip + notify. Every booking writes `spend_ledger` + `audit_log`. Note: `auto_book_mode = auto_under_X` only functions when `KEY_UNLOCK_MODE = auto` (§14); under the default `master_key` mode there is no resident key to book unattended, so it falls back to one-tap approval.

---

## 12. Notifications (email + Telegram, one-tap)

`notify_channel` per watch (inherits user default). Telegram bot = instant push with inline Confirm/Reject carrying the signed single-use token (the charge still gates on login + TOTP). Email = signed link. Quiet hours hold non-urgent alerts; error-fares/expiring deals can override. One deal = one notification; deduped. Optional daily run summary (§15).

---

## 13. Coverage Strategy & Honest Limits

As exhaustive as legitimately possible — never a claimed global minimum. Fan out across all bookable sources (best-of), pull NDC airline-direct via Duffel, layer metasearch signal with deep links, dedup. Residual gaps named in every `coverage_report`: some LCCs, airline-direct member fares, Airbnb/Vrbo (no API; discovery-only), luxury rate programs (Amex FHR/Virtuoso/hotel-direct).
```json
{ "searched_sources":[...], "results_per_source":{...},
  "known_gaps_for_this_route":["LCC: Peach/Jetstar may be cheaper direct","Check Amex FHR for this property"],
  "confidence":"high|medium|low" }
```

---

## 14. Secrets, Payment Data & Compliance

Tokenize where possible (store provider token, not raw card). If raw card stored: AES-256-GCM/libsodium, master key supplied at runtime, never plaintext on disk; decrypt in memory at booking; zeroize.

**Master-key unlock — user toggle `KEY_UNLOCK_MODE`. Default = `master_key`.**
- **`master_key` (DEFAULT — most secure, unlock every booking):** the user enters the master key/passphrase at **each booking approval** (alongside login + TOTP at the Confirm step). It derives the data key in memory for that one booking, then is zeroized — the key is never persisted and never held between bookings, so a stolen disk, backup, or running host yields nothing. Recommended default, especially with a multi-person household's passports + payment stored. Tradeoff: **no unattended booking** — every booking needs you present to approve and unlock (which you already are). Therefore `auto_book_mode = auto_under_X` is disabled in this mode (an auto-book deal instead waits as a normal one-tap approval).
- **`auto` (autonomous):** the master key is fetched at startup from Vault or the OS keychain (`MASTER_KEY_SOURCE=vault|keychain`) with no human present and held in memory, so bookings — including `auto_book_mode` — run unattended through reboots. Tradeoff: larger attack surface; pair with tight Vault policies, short-lived tokens, and host hardening.

One `KeyProvider` interface with both modes; selectable in Profile/Settings. In `master_key` mode the booking executor blocks until the key is supplied at approval and shows "enter master key to book"; in `auto` mode, if unlock hasn't happened it shows "vault locked — unlock to enable booking." Monitoring/alerting always run regardless. Prefer Vault (transit+KV) for the `auto` backend.

**PCI (honest):** for **personal/household use** (you and your family, your own cards) you're a cardholder, not a merchant; formal PCI-DSS merchant scope doesn't apply, but you must still secure what you store (tokenization sidesteps most). **Multi-user caveat:** if accounts are opened to people outside your household — so others book through the admin's provider accounts with their own cards — the admin becomes a travel seller processing third-party payments: that triggers full PCI scope, seller-of-record obligations, and possibly ticketing licensing/bonding (effectively running an OTA). Keep it household-scoped unless you intend that. Never log card data or put it in LLM context. Encrypt passport + DOB; keep the master key out of backups.

**Admin-managed provider credentials.** Provider API keys (§7.6) are stored encrypted in `platform_integrations` using the same master key/Vault, entered and rotated from the Admin console, masked in the UI, and never exposed to users, the agent, or logs. Admin-entered values override the `.env` bootstrap at runtime.

---

## 15. Operations — quota, cost, health

Per-adapter usage counters vs free tiers; throttle/pause near quota to stay free; log spend for paid sources (proxy, Airbnb data API). Adapter health: repeated errors → degraded, surfaced in UI, others keep running. Optional daily run summary.

---

## 16. Optional Scrape / Discovery Layer

Signal/discovery only (Google Flights, Airbnb). Playwright + residential rotating proxies — not NordVPN. Pluggable, fails safe, rate-limited, off by default. Includes the Airbnb adapter (§8.5).

---

## 17. Design System & UX — Palette A "Atelier" · one-tap, less is more

**Thesis:** a calm, premium concierge. Color *means* something — **azure blue = value/savings**, **champagne = the luxury tier** — encoding the product rather than decorating. Spend boldness only on the value bar + the price.

**Color tokens**
```
--canvas #F6F3EC   --surface #FFFFFF   --ink #1F1E1B   --muted #6E6A63
--line   #E7E1D5   --value  #2C5E8C    --luxury #B98A4B --alert #B4502E
            # --value is a stylish deep azure (was green); pair tint #E8EEF5 for soft fills, hover #244E76
```
One accent per surface. `--value` is the workhorse (buttons, score bar, success); `--luxury` is a scarce highlight (luxury badge, premium cabins, top of the score bar). Ink-on-paper carries the rest.

**Typography (free defaults; upgrade if licensed)** — Display & prices: **Spectral** (serif, used sparingly) / Georgia fallback. Body & UI: **Inter** / system-ui. Labels/eyebrows/data: **ui-monospace**, uppercase + tracked. Scale px: display 40 · h1 28 · h2 20 · body 16 · small 13 · micro 11. Sentence case throughout.

**Layout & feel** — 8px grid; container ~720–880px; radius 14–18; hairline dividers; generous whitespace; **mobile-first**. Quality floor: visible keyboard focus, reduced-motion respected, AA contrast. Motion minimal and earned (gentle card reveal, score-bar fill); nothing else.

**The whole app — four screens:**
1. **Watches** — your trips as cards, each showing status + best current deal in context. One primary button: **New watch**.
2. **New / Edit watch** — a single page. Visible: **who** (one-tap traveler group / picks), where, when, **price range**, the **luxury⇄savings dial**. Everything else (cabin, stops, airlines, **flight timing windows**, refundable, Airbnb, notify channel) under a quiet **More options** disclosure. Preferences pre-fill defaults, so most fields can be skipped.
3. **Deal review (the hero)** — segmented control across the 3 framings (Best value default); the **price big** with its one-line historical context; the **luxury-per-dollar score bar** (signature element); the FF program to be attached per traveler; collapsible coverage report; validation warnings; one **Confirm & book** + **Reject** with reason chips.
4. **Profile / Settings** — travelers (with loyalty, documents, seat/meal prefs), traveler groups, saved preferences, encrypted payment, guardrails, notifications, key-unlock mode, trip templates.

**The one-tap flow, made explicit (taps counted):**
- *Setup (once):* add travelers + loyalty + payment + preferences.
- *Create a watch:* tap traveler group (1) → enter where/when/price-range, nudge the dial → **Save** (1). Two meaningful taps; the rest is pre-filled.
- *Get alert → booked:* tap **Confirm** in Telegram (1) → enter TOTP → **Booked**. One tap + a code, because the system already holds who/how/pay/loyalty.

**Microcopy** — active voice, named by what the user controls: button **Confirm & book** → toast **Booked**. Empty states invite action ("No travelers yet — add your household to start"). Errors say what happened and how to fix it, never apologetic or vague.

### 17.1 Screens & exactly where each input lives (wireframe level)

**Where standing info is entered → Profile / Settings (screen 4).** Where per-trip info is entered → New / Edit Watch (screen 2). Where approvals happen → a notification (email/Telegram) → the Approval page (screen 3). New users first pass through **Sign-up + Onboarding (screen 0)**; admins also get the **Admin / Integrations console (screen 5)**. Nothing is entered "nowhere": every field in the §6 data model maps to one of these screens below.

**Screen 0 — Sign-up & onboarding (new users)**
```
┌─────────────────────────────────────────────┐
│  Travel Watch                                │
│  Create your account                         │
│  Email [______]  Password [______]           │  ← users (role defaults to user)
│  [ Continue ] → enrol 2-factor (TOTP)        │
│  ── then a 4-step wizard (skippable) ──      │
│  1 You as a traveller (name, DOB, country)   │  ← travelers (passport later)
│  2 Add a payment method (or skip)            │  ← payment_methods (needed before booking)
│  3 Preferences: home airports · dial · alerts│  ← user_preferences
│  4 Create your first watch  → screen 2       │
│  [ Finish ]  (skipped items become nudges)   │  ← onboarding_completed
└─────────────────────────────────────────────┘
```

**Screen 1 — Watches (home)**
```
┌─────────────────────────────────────────────┐
│  Travel Watch                       ⚙ Profile│
│                                              │
│  Your trips                      [ + New ]   │
│  ┌─────────────────────────────────────────┐ │
│  │ Tokyo → Singapore   ●active             │ │
│  │ 12–19 Apr · 2 travellers · Business     │ │
│  │ Best now: ¥118,400  (cheapest ~8% / 90d)│ │
│  │ [ Search now ]  [ Edit ]  [ Pause ]     │ │
│  └─────────────────────────────────────────┘ │
│  ┌─────────────────────────────────────────┐ │
│  │ Tokyo → Anywhere warm  ●active  flexible│ │
│  │ March · 2+2 · under ¥600k all-in        │ │
│  └─────────────────────────────────────────┘ │
└─────────────────────────────────────────────┘
```
Inputs here: none new — list, status, the "best now" context line, and per-watch actions (Search now §8.9, Edit, Pause). Empty state: "No watches yet — add your first trip."

**Screen 2 — New / Edit Watch (the per-trip input form)**
```
┌─────────────────────────────────────────────┐
│  ‹ New watch                                 │
│                                              │
│  Who's travelling                            │
│  ( Whole family )( Me + partner )( + pick )  │  ← traveler_group_id / watch_travelers
│                                              │
│  From   [ HND, NRT ▾ ]   (home airports)     │  ← origin_iatas (prefilled)
│  To      [ Singapore ]   ○ Flexible          │  ← destination / destination_mode
│  When   [ 12 Apr ▾ ]–[ 19 Apr ▾ ]            │  ← depart/return ranges
│          nights [ 5 ]–[ 9 ]                  │  ← trip_min/max_nights
│                                              │
│  Price range (all-in)                        │
│   Flights up to [ ¥160,000 ]                 │  ← flight_budget_max
│   Hotel/night  up to [ ¥45,000 ]             │  ← hotel_budget_per_night_max
│                                              │
│  Luxury  ◀───────●──────▶  Savings           │  ← luxury_vs_savings
│                                              │
│  ▸ More options                              │  (disclosure, collapsed by default)
│      Cabin · stops · max layover · min       │
│      connection · preferred/avoided airlines │
│      & alliances · flight timing windows     │  ← outbound/return earliest/latest
│      (out/return earliest & latest depart,   │     depart, arrive_by, avoid_redeye
│      arrive-by) · avoid red-eye · refundable │  ← prefer_refundable
│      · hotel min rating/area/radius · car    │  ← hotel_*, want_car
│      · Airbnb (discovery only) [toggle]      │  ← include_airbnb (+ disclosure modal)
│      · notify via [email|telegram|both]      │  ← notify_channel
│      · check [daily|6h|hourly]               │  ← refresh_interval
│      · ideal price / glide window            │  ← ideal_price, glide_*
│                                              │
│  [ Save watch ]        [ Save as template ]  │
└─────────────────────────────────────────────┘
```
Smart defaults from `user_preferences` pre-fill everything; the five fields above the fold are all most trips need.

**Screen 3 — Deal review / Approval (the hero; reached from a notification or the app)**
```
┌─────────────────────────────────────────────┐
│  ‹ Deal                          ●expires 27m│
│  ( Best value )  Max luxury   Cheapest ok    │  ← framing segmented control
│                                              │
│  Tokyo → Singapore · Business                │
│  ¥118,400 all-in   (was ¥206,000)            │  ← all_in_price (§9)
│  Cheapest ~8% seen in 90d · usually rises 6w │  ← price_percentile / timing_advice (§10)
│  Taxes ¥14,200 · bag incl · FX ¥0            │  ← all-in breakdown
│                                              │
│  Luxury  ████████████████░░  92 / 100        │  ← quality_index score bar
│  Nonstop · 7h25m · ANA · Star Alliance       │
│  Miles → KLM Flying Blue (Matt), AA (TzuHui) │  ← loyalty_plan_json (§7.4)
│                                              │
│  ⚠ TzuHui passport expires 4 mo after travel │  ← validation_warnings (§8.6)
│  ▸ Coverage: 7 sources searched              │  ← coverage_report (collapsible, §13)
│                                              │
│  [  Confirm & book  ]                        │  ← primary; opens login+TOTP (+ master key)
│  [ Reject ]                                  │
└─────────────────────────────────────────────┘
```
**Reject** opens reason chips → *too pricey · layover too long · not luxurious enough · wrong area · other* → feeds §8.4 and replies "Got it — I'll keep looking and aim higher on value."

**Screen 4 — Profile / Settings (where standing & sensitive info is entered)**
- **Travelers** (one card per person): legal first/last name (as on passport), DOB, gender, nationality, residency, passport number + expiry, Known Traveler / redress numbers, seat / meal / accessibility prefs. → `travelers`
- **Loyalty** (under each traveler): program, number, status tier, "preferred to earn in this alliance". → `loyalty_accounts`
- **Traveler groups**: create presets ("Whole family") for one-tap selection. → `traveler_groups`
- **Payment methods** (encrypted): label + card (tokenized where possible) + billing address. **This is the only place card/bank info is entered.** → `payment_methods` (§14)
- **Preferences (defaults)**: home airports, default cabin, dial, preferred/avoided airlines & hotel brands, hotel min rating, timing defaults, refundable, seat auto-select, default notify channel, quiet hours. → `user_preferences`
- **Guardrails**: global max auto-book, weekly spend/booking caps, annual travel budget. → `users` (§11)
- **Security**: `KEY_UNLOCK_MODE` toggle — **master key (default) vs auto** (§14). In master-key mode the master key is entered at each approval (screen 3), never stored here.
- **Notifications**: email address; **connect Telegram** (link the bot once); default channel. → §12
- **Templates**: manage saved trip templates.

**Screen 5 — Admin / Integrations (admin only)**
```
┌─────────────────────────────────────────────┐
│  Admin · Integrations                        │
│  Provider            Status      Env         │
│  Duffel        ● connected   (live)  [edit]  │  ← platform_integrations
│  Amadeus       ● connected   (test)  [edit]  │
│  Expedia Rapid ○ not set            [add]    │
│  Hotelbeds     ● connected   (live)  [edit]  │
│  Telegram bot  ● connected          [edit]   │
│  Google Cal    ● connected          [edit]   │
│  Anthropic     ● connected          [edit]   │
│  Airbnb data   ○ disabled    [enable][edit]  │
│  [ + Add credential ]    [ Test all ]        │  ← paste key, choose test/live, test connection
│                                              │
│  Feature flags                               │
│   [✓] auto-book available  [✓] scrape layer  │
│   [ ] Airbnb discovery     default guardrails│  ← feature_flags_json
│                                              │
│  Platform health: adapters · quota · audit   │  ← §15
└─────────────────────────────────────────────┘
```
Inputs here: all provider credentials (encrypted, masked), per-integration env + enable, feature flags, and platform health/audit. Admin-entered values override `.env`. This is the **only** place API keys are managed in the UI; users never see this screen.

### 17.2 Communication interfaces — approve / reject (built in)

**Email** (when `notify_channel` includes email):
```
Subject: ✈ Tokyo→Singapore Business ¥118,400 all-in (cheapest ~8% in 90d)

Best value found for "Tokyo → Singapore":
  ¥118,400 all-in  (was ¥206,000) · taxes ¥14,200 · bag incl
  Nonstop 7h25m · ANA (Star Alliance) · Luxury 92/100
  Miles credited: KLM Flying Blue (Matt), AAdvantage (TzuHui)
  Cancellation: free within 24h
  ⚠ TzuHui passport expires <6mo after travel
  Searched 7 sources · gaps: check Peach direct

      [  Review & approve  ]        [  Reject  ]
      (opens a secure page — sign-in + code required to book)
```
The email never books on its own. **Review & approve** is the signed, single-use link (§8.2) → it opens the Approval page (screen 3) which requires login + TOTP (and, in master-key mode, the master key) before any charge. **Reject** opens the reason chips.

**Telegram** (when `notify_channel` includes telegram):
```
✈ Tokyo → Singapore · Business
¥118,400 all-in (was ¥206,000) · Luxury 92/100
Nonstop 7h25m · ANA · cheapest ~8% in 90d
Miles → KLM Flying Blue / AAdvantage
⚠ TzuHui passport <6mo after travel

[ ✅ Confirm ]   [ ❌ Reject ]   [ 🔍 Details ]
```
Buttons carry the signed single-use token. **Confirm** → opens the Approval page for login + TOTP (+ master key); it does not charge from the chat alone. **Reject** → inline quick-reply reason buttons (too pricey / layover / not luxe / wrong area / other) feeding §8.4. **Details** → the full Approval page.

**Approval page** (screen 3 in "approval mode"): login + TOTP gate → final all-in breakdown → (master-key field if in that mode) → **Confirm & book** → re-price + guardrail check (§11) + book (§8.3) → "Booked", itinerary attached, calendar updated. Token consumed; expiry/reject invalidates it.

**Other notifications:** booking confirmation + receipt, booking failure, disruption/schedule-change (§8.7), cancellation/refund status (§8.8), and an optional daily run summary (§15) — all on the chosen channel(s), honoring quiet hours.

---

## 18. Repository Structure

```
travel-autobook/
├── docker-compose.yml  .env.example  Caddyfile
├── backend/app/
│   ├── main.py  config.py
│   ├── db/                # models, session, alembic
│   ├── api/               # auth+signup, onboarding, admin/integrations, profiles, travelers, groups,
│   │                      #   preferences, templates, watches, deals, approve, reject, settings, webhooks
│   ├── adapters/flights/{amadeus,duffel,kiwi,travelpayouts}.py
│   ├── adapters/hotels/{eps,booking,hotelbeds,amadeus}.py
│   ├── adapters/cars/{amadeus,cartrawler}.py
│   ├── adapters/discovery/{airbnb_dataapi,airbnb_scraper,gflights}.py
│   ├── valuation/         # Value Engine (§9)
│   ├── pricing/           # targets, percentiles, glide, timing advice (§10)
│   ├── preferences/       # acceptance band + suppression + value_pressure (§8.4)
│   ├── loyalty/           # alliance_map + FF mapper (§7.4)
│   ├── guardrails/        # spend limits (§11)
│   ├── coverage/  validation/  disruptions/
│   ├── agents/            # LLM explanations only
│   ├── booking/           # deterministic executors + calendar push
│   ├── notifications/     # email + telegram + quiet hours (§12)
│   ├── security/          # vault, crypto, KeyProvider, signed tokens (§14)
│   └── scheduler/         # celery tasks, beat
├── frontend/src/{pages,components,api,hooks,theme}/   # theme = §17 tokens
└── docs/runbook.md
```

---

## 19. Environment Variables (`.env.example`)

> Core/infra vars (APP_SECRET, DB, Redis, Vault, `KEY_UNLOCK_MODE`) live here. **Provider API keys below are bootstrap/fallback only** — once running, the admin enters and manages them encrypted in the Admin console (§7.6), which overrides these at runtime. You can leave provider keys blank in env and configure everything from the UI.

```
APP_SECRET=...  DATABASE_URL=postgresql+psycopg://...  REDIS_URL=redis://redis:6379/0  PUBLIC_BASE_URL=https://travel.local
VAULT_ADDR=http://vault:8200  VAULT_TOKEN=...
ALLOW_SELF_SIGNUP=false   # if false, admin invites/approves users; first account created becomes admin
KEY_UNLOCK_MODE=master_key         # USER TOGGLE, DEFAULT master_key (unlock every booking, most secure) | auto (autonomous)
MASTER_KEY_SOURCE=vault            # used only when KEY_UNLOCK_MODE=auto: vault | keychain
EMAIL_PROVIDER=ses  SES_REGION=...  ALERT_FROM_ADDRESS=alerts@travel.local  TELEGRAM_BOT_TOKEN=...
GOOGLE_CALENDAR_CLIENT_ID=...  GOOGLE_CALENDAR_CLIENT_SECRET=...
AMADEUS_CLIENT_ID=...  AMADEUS_CLIENT_SECRET=...  AMADEUS_ENV=test
DUFFEL_ACCESS_TOKEN=...  DUFFEL_ENV=test  KIWI_TEQUILA_API_KEY=...
TRAVELPAYOUTS_TOKEN=...  SKYSCANNER_AFFILIATE_KEY=...
EPS_API_KEY=...  EPS_SHARED_SECRET=...  BOOKING_DEMAND_API_KEY=...  HOTELBEDS_API_KEY=...  HOTELBEDS_SECRET=...
AMADEUS_CARS=enabled
DEFAULT_LUXURY_VS_SAVINGS=0.6  DEFAULT_QUALITY_FLOOR=40  DEFAULT_BAND_TOLERANCE=0.10
TARGET_PERCENTILE=25  GLIDE_START_DAYS=42  GLIDE_END_DAYS=3
GLOBAL_MAX_AUTO_BOOK_AMOUNT=...  WEEKLY_MAX_SPEND=...  WEEKLY_MAX_BOOKINGS=...
ANTHROPIC_API_KEY=...
SCRAPE_ENABLED=false  AIRBNB_DATA_API_KEY=...  RESIDENTIAL_PROXY_URL=...
NORDVPN_USER=...  NORDVPN_PASS=...
```

---

## 20. Suggested Build Order (guidance, not a prerequisite)

0. Scaffold (compose, auth+TOTP, migrations §6, theme tokens §17).
1. **Profiles first** — travelers, loyalty, groups, preferences, payment, templates (§7). The rest depends on this.
2. Watches + multi-source monitoring + `price_stats` (no money).
3. Value (§9) + pricing/timing (§10) + preference loop (§8.4) + loyalty mapper (§7.4) + coverage + validation + Deal-review screen + notifications (email/Telegram) with signed single-use approval; Confirm/Reject record intent only.
4. Flight booking (Duffel test mode): approve → re-price → guardrail (§11) → order with FF# + ages + KTN + seats/meals → persist → calendar push → notify.
5. Hotel booking + gating + cars + disruptions (§8.7).
6. Secrets hardening + KeyProvider toggle + full guardrails; go live only after full test-mode validation.
7. Optional Airbnb discovery (data-API default).

---

## 21. Master Build Prompt for Cursor

> "Read `docs/travel-autobook-spec.md` in full — it is the complete source of truth. Build the entire system it describes, API-first and multi-source, using the stack in §4, the data model in §6, the flows in §7–§8, the algorithms in §7.4 / §8.4 / §9 / §10 / §11, the providers in §5, the design system and screens in §17 (Palette A 'Atelier', `--value` = azure #2C5E8C), the repo layout in §18, and the env in §19. Multi-user with roles per §7.0 (sign-up + TOTP, onboarding wizard, strict `user_id` scoping); an admin Integrations console per §7.6 (all provider keys entered/managed encrypted in-UI, overriding env). Follow the suggested build order in §20 but deliver the whole thing. Hard rules: agents may rank/explain but must NEVER call the booking executor or see decrypted secrets; every money-moving action is deterministic, gated by a signed single-use approval token + login + TOTP + the §11 guardrails; the frequent-flyer mapper (§7.4) attaches the correct same-alliance program per traveler and flags manual follow-up if a carrier rejects it; never store card data or provider keys in logs or LLM context; respect the honest limits in §13 and the 'do not build' list in §25. Provide working `docker compose up`, Alembic migrations, adapter unit tests with recorded fixtures, and seed the `alliance_map`."

---

## 22. What YOU Must Provide

**Accounts/keys:** Amadeus, Duffel (test now; business+KYC+funding for live), Kiwi, Travelpayouts/Skyscanner, Expedia Rapid and/or Booking Demand, Hotelbeds, (opt) Amadeus Cars/CarTrawler, email provider+domain, Telegram bot token, Google Calendar OAuth, Anthropic key, (opt) Airbnb data-API / residential proxy.
**Infra:** Docker host, domain+TLS, Postgres backups + a separate safe place for the master key.
**Profile data (encrypted):** travelers (passport, DOB, KTN/redress, seat/meal prefs), loyalty numbers + status + preferred-earning program per alliance, payment (ideally tokenized), billing/contact, traveler groups, default preferences.
**Decisions:** budgets + `max_total_trip_spend`; quality floor + dial; band tolerance; ideal price / glide; trip mode; timing windows + avoid-redeye; refresh interval; constraints (stops, layover, min connection, cabin, airlines/alliances); refundable + loyalty weighting; notify channel + quiet hours; guardrails (`global_max_auto_book_amount`, weekly caps); `KEY_UNLOCK_MODE`: default `master_key` (unlock every booking, most secure) vs `auto` (autonomous); auto_book_mode; Airbnb toggle (default no).
**Acknowledgements:** live Duffel = small travel seller; hotel APIs have content/rate terms; "exhaustive" = all legitimately accessible inventory with named gaps; cross-alliance FF accrual + fare-class earning are airline-dependent (system attaches + flags, doesn't guarantee); Airbnb auto-book impossible (toggle = discovery-only, manual, ToS-grey); timing/visa/passport notes are guidance, not guarantees/legal advice.

---

## 23. Roadmap — great-product features (recommended next, not core)

High-value additions that elevate the product; promote into the build as desired. **My top three to pull forward: flexible-destination mode, the itinerary hub, and the onboarding wizard.**
- **Flexible-destination / inspiration mode** (`destination_mode=flexible`): "anywhere warm/beach/city under ¥X in March." Let the destination float and rank candidate cities by luxury-per-dollar — perfectly aligned with the north star and a genuine differentiator. (Kiwi/Amadeus cheapest-destination search.)
- **Itinerary hub + confirmation aggregation + expense export:** one place showing every upcoming/past trip with all documents; optionally ingest provider confirmation emails; export bookings to CSV/accounting (useful if you run businesses).
- **Onboarding wizard + starter templates:** guide first-run setup (household → payment → first watch) and offer preset watches ("annual home visit", "weekend getaway") so value is immediate.
- **Annual travel budget tracking:** track spend across all watches against `annual_travel_budget` with a simple burn-down (finance-friendly).
- **Seasonality & events awareness:** factor known demand spikes (holidays, Golden Week, major events) into targets/history so "good price" is season-aware.
- **Award / points-aware search:** detect when a trip is bookable (or cheaper) with miles/points and surface it ("~60k Flying Blue + ¥5k taxes vs ¥118k cash"). Award-availability APIs are limited, so treat as roadmap, not a promise.
- **Trip add-ons:** suggest travel insurance, eSIM, lounge access, and airport transfers to complete the trip.
- **Weather-at-destination** on the deal/itinerary for travel dates.
- **PWA + push:** installable mobile app feel with web push, complementing Telegram.
- **i18n (EN/JA):** UI language toggle.
- **Co-approval for big spends:** optional partner sign-off above a threshold (household use).
- **Cross-watch preference learning:** let rejections/preferences inform other watches, not just the one.

---

## 24. Engineering Hardening & Non-Functional Requirements (build these — a money system needs them)

- **Config validation at boot:** fail fast with a clear error if any required env/secret is missing or malformed; never start half-configured.
- **Resilience:** per-adapter timeouts, retries with backoff, and circuit breakers; one failing/slow source must never block the others or the run.
- **Caching:** short-TTL cache of search results to cut API cost and stay within free tiers.
- **Idempotency & exactly-once money ops:** enforced at the booking/cancellation layer (§8.3, §8.8).
- **Observability:** structured logging, metrics, request tracing, and error tracking (e.g. Sentry); a minimal health/status view of adapters, queues, and the scheduler. **Never log card data, full PII, or secrets.**
- **Backups & disaster recovery:** automated encrypted Postgres backups + a documented restore runbook; the master key stored separately from backups (a backup is useless without it).
- **Secrets rotation:** support rotating `APP_SECRET`, the master key (re-encrypt blobs), and provider tokens without downtime.
- **CI/CD:** lint, type-check, and tests as merge gates; reproducible builds.
- **Testing strategy:** adapter unit tests with recorded fixtures; an end-to-end booking test in Duffel/EPS **test mode**; contract tests against provider schemas; a global **simulation/dry-run** switch so the whole pipeline (including "booking") can run without real charges.
- **Feature flags:** toggle individual adapters/features (and the scrape/Airbnb layer) without redeploying.
- **Scheduler robustness:** handle DST, missed runs, and catch-up; idempotent jobs.
- **Privacy / data lifecycle:** one-click **export all** and **delete all** personal data; a stated retention policy for `price_observations`/logs; encryption at rest for all PII.
- **Notification deliverability:** SPF/DKIM/DMARC for email; Telegram as the reliable fallback.
- **Accessibility & responsiveness:** AA contrast, visible focus, reduced-motion, full keyboard use; mobile-first layouts.
- **Multi-user with roles (admin/user):** strict `user_id` scoping on all personal data; platform credentials are admin-only and never reach user scope; keep boundaries clean so household → small-group scaling needs no rewrite. (Opening to unrelated third parties = OTA compliance, §14.)

---



## 25. Things to deliberately NOT build

- ❌ Constant polling (daily/6h/hourly covers it).  ❌ A hard monotonic value floor (use the §8.4 band).  ❌ Acting on "any price under the ceiling" (use §10 targets).  ❌ LLM-driven browser checkout with the saved card.  ❌ Auto-booking Airbnb by driving their site (toggle = discovery-only + manual).  ❌ "Reply YES to book" as sole auth (use signed single-use tokens + login + TOTP).  ❌ NordVPN as anti-bot evasion.  ❌ Storing raw card data when a provider token will do.  ❌ Guaranteeing cross-alliance mileage accrual (attach + flag instead).  ❌ Cramming the UI (four screens, one primary action each).  ❌ Promising a true global price minimum.

---

*End of specification. The document is self-contained: hand it to Cursor with the §21 master prompt. North star throughout: maximum luxury per dollar, honest coverage, smart price-history use, hard spend limits, alliance-aware loyalty, and a calm one-tap interface.*
