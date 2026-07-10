# User-Facing Copy Quality and Platform Audit Design

## Scope

Remove and prevent em dashes and en dashes in the live frontend only. Architecture documents and unserved mockups are outside this cleanup.

## Copy Check

Add a dependency-free Node script that scans `frontend/src` and `frontend/index.html` for Unicode em dash and en dash characters. The script reports each matching file and line, exits with a failure code, and runs before the existing TypeScript and Vite production build.

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

The copy check must fail clearly with file names, line numbers, and the offending character. Existing runtime errors should continue through current API and UI error surfaces.

## Verification

- run the copy check directly
- run all backend tests in Docker
- run Ruff on changed Python files
- run the production frontend build
- validate Docker Compose with test-only environment values
- run `git diff --check`
- rescan user-facing frontend source for long dashes

## Commit Boundaries

Commit only the copy check, verified platform fixes, tests, and this design document. Exclude the modified SQLite fixture and the pre-existing admin integration plan.
