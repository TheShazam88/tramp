#!/usr/bin/env bash

set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
RUN_ID="tramp-migration-test-$$-$(date +%s)"
NETWORK_NAME="${RUN_ID}-network"
POSTGRES_CONTAINER="${RUN_ID}-postgres"
RUNNER_CONTAINER="${RUN_ID}-runner"
API_IMAGE="${RUN_ID}-api"
RESOURCE_LABEL="tramp.migration-test=${RUN_ID}"

NETWORK_CREATED=0
POSTGRES_CREATED=0
RUNNER_MAY_EXIST=0
API_IMAGE_CREATED=0

cleanup() {
  local cleanup_status=0

  if [[ "$RUNNER_MAY_EXIST" == "1" ]] &&
    docker container inspect "$RUNNER_CONTAINER" >/dev/null 2>&1; then
    if ! docker rm --force --volumes "$RUNNER_CONTAINER" >/dev/null 2>&1; then
      echo "WARNING: failed to remove test runner container $RUNNER_CONTAINER." >&2
      cleanup_status=1
    fi
  fi
  if [[ "$POSTGRES_CREATED" == "1" ]]; then
    if ! docker rm --force --volumes "$POSTGRES_CONTAINER" >/dev/null 2>&1; then
      echo "WARNING: failed to remove PostgreSQL container $POSTGRES_CONTAINER." >&2
      cleanup_status=1
    fi
  fi
  if [[ "$NETWORK_CREATED" == "1" ]]; then
    if ! docker network rm "$NETWORK_NAME" >/dev/null 2>&1; then
      echo "WARNING: failed to remove Docker network $NETWORK_NAME." >&2
      cleanup_status=1
    fi
  fi
  if [[ "$API_IMAGE_CREATED" == "1" ]]; then
    if ! docker image rm "$API_IMAGE" >/dev/null 2>&1; then
      echo "WARNING: failed to remove temporary API image $API_IMAGE." >&2
      cleanup_status=1
    fi
  fi

  return "$cleanup_status"
}

on_exit() {
  local original_status=$?
  local cleanup_status

  trap - EXIT INT TERM
  set +e
  cleanup
  cleanup_status=$?

  if [[ "$original_status" != "0" ]]; then
    if [[ "$cleanup_status" != "0" ]]; then
      echo "WARNING: cleanup also failed; preserving original status $original_status." >&2
    fi
    exit "$original_status"
  fi
  exit "$cleanup_status"
}

trap on_exit EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

command -v docker >/dev/null
docker info >/dev/null

docker network create --label "$RESOURCE_LABEL" "$NETWORK_NAME" >/dev/null
NETWORK_CREATED=1
docker run --detach \
  --name "$POSTGRES_CONTAINER" \
  --label "$RESOURCE_LABEL" \
  --network "$NETWORK_NAME" \
  --network-alias postgres \
  --tmpfs /var/lib/postgresql/data:rw \
  --env POSTGRES_DB=tramp_migration_test \
  --env POSTGRES_USER=travelwatch \
  --env POSTGRES_PASSWORD=travelwatch \
  --health-cmd="pg_isready -U travelwatch -d tramp_migration_test" \
  --health-interval=1s \
  --health-timeout=5s \
  --health-retries=30 \
  postgres:16-alpine >/dev/null
POSTGRES_CREATED=1

docker build --label "$RESOURCE_LABEL" --tag "$API_IMAGE" "$BACKEND_DIR"
API_IMAGE_CREATED=1

for attempt in {1..60}; do
  health="$(
    docker inspect --format='{{.State.Health.Status}}' "$POSTGRES_CONTAINER" 2>/dev/null ||
      true
  )"
  if [[ "$health" == "healthy" ]]; then
    break
  fi
  if [[ "$health" == "unhealthy" || "$attempt" == "60" ]]; then
    docker logs "$POSTGRES_CONTAINER" >&2
    echo "Disposable PostgreSQL did not become healthy." >&2
    exit 1
  fi
  sleep 1
done

RUNNER_MAY_EXIST=1
docker run --rm --interactive \
  --name "$RUNNER_CONTAINER" \
  --label "$RESOURCE_LABEL" \
  --network "$NETWORK_NAME" \
  --volume "$BACKEND_DIR/scripts:/app/scripts:ro" \
  --volume "$BACKEND_DIR/tests:/app/tests:ro" \
  --env MIGRATION_TEST_DATABASE_URL=postgresql+psycopg://travelwatch:travelwatch@postgres:5432/tramp_migration_test \
  --env MIGRATION_TEST_ALLOW_RESET=1 \
  --env DATABASE_URL=postgresql+psycopg://travelwatch:travelwatch@postgres:5432/tramp_migration_test \
  --env INITIAL_ADMIN_EMAIL=admin@example.com \
  --env INITIAL_ADMIN_PASSWORD=test-admin-password \
  --env APP_SECRET=migration-test-secret-with-at-least-thirty-two-bytes \
  --env REDIS_URL=redis://localhost:6379/0 \
  --env PUBLIC_BASE_URL=https://tramp-migration.test \
  "$API_IMAGE" /bin/sh <<'CONTAINER_SCRIPT'
set -eu

pip install "pytest>=8.2,<9.0" >/tmp/pytest-install.log
pytest \
  tests/test_admin_activity_postgres.py \
  tests/test_migration_chain.py \
  tests/test_tramp_stamps_postgres.py \
  -q \
  -rs \
  --junitxml=/tmp/postgres-results.xml

python - <<'PYTHON'
from pathlib import Path
from xml.etree import ElementTree

report = Path("/tmp/postgres-results.xml")
root = ElementTree.parse(report).getroot()
suites = [root] if root.tag == "testsuite" else list(root.findall("testsuite"))
tests = sum(int(suite.attrib.get("tests", "0")) for suite in suites)
skipped = sum(int(suite.attrib.get("skipped", "0")) for suite in suites)
print(f"PostgreSQL verification: {tests} tests, {skipped} skipped")
raise SystemExit(1 if skipped else 0)
PYTHON
CONTAINER_SCRIPT
RUNNER_MAY_EXIST=0
