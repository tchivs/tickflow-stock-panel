#!/bin/sh
set -u

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
cd "$ROOT"
COMPOSE="docker compose -p athenaquant-phase1-test -f docker-compose.yml -f compose/phase1.test.yml"

for image in athenaquant-phase1-app:phase1 athenaquant-phase1-receiver:phase1 athenaquant-phase1-verifier:phase1; do
  if ! docker image inspect "$image" >/dev/null 2>&1; then
    echo "missing prepared Phase 1 image: $image; run bash compose/phase1/prepare-images.sh first" >&2
    exit 2
  fi
done

set +e
$COMPOSE up --no-build --pull never --abort-on-container-exit --exit-code-from verifier
status=$?
set -e

$COMPOSE down -v --remove-orphans || true
rm -rf .tmp/phase1-data
exit "$status"
