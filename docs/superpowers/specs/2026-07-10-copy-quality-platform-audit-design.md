# User-Facing Copy Quality and Platform Audit Design

> **Status (2026-07-15):** The user explicitly cancelled the copy-guard task. Its scanner, package commands, build integration, and copy-specific required QA are intentionally removed. Normal clipboard support remains in scope, including the `PurgeTestDataPanel` copy button.

## Scope

The copy-guard portion of this design is cancelled. The platform-audit scope below remains as historical context; it does not impose automated copy restrictions.

## Copy Guard (Cancelled)

Do not add or require a copy scanner, package command, or production-build gate.

## Platform Audit

Review the core authenticated product flows:

- profile and household workspace loading
- watch creation, pause, resume, and search
- deal timeline, readiness, approval, and rejection
- booking state and mock-disabled behavior
- frontend and backend API contracts
- deployment configuration and public-repository safety

Only reproducible correctness or reliability defects are in scope. Broad redesign and unrelated refactoring are excluded.

## Error Handling

Existing runtime errors should continue through current API and UI error surfaces.

## Verification

- run all backend tests in Docker
- run Ruff on changed Python files
- run the production frontend build
- validate Docker Compose with test-only environment values
- run `git diff --check`

## Commit Boundaries

Commit only verified platform fixes, tests, and this design document. Exclude the modified SQLite fixture and the pre-existing admin integration plan.
