#!/bin/sh
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
cd "$ROOT"
COMPOSE="docker compose -p athenaquant-phase1-test -f docker-compose.yml -f compose/phase1.test.yml"

# FixtureBundle validates real file mode in addition to the read-only mount.
chmod a-w compose/phase1/fixtures compose/phase1/fixtures/instruments.json compose/phase1/fixtures/market-data.json

$COMPOSE build app
$COMPOSE build receiver
$COMPOSE build verifier

for image in athenaquant-phase1-app:phase1 athenaquant-phase1-receiver:phase1 athenaquant-phase1-verifier:phase1; do
  docker image inspect "$image" >/dev/null
done

docker run --rm --network none \
  -e PHASE1_FIXTURE_MODE=true \
  -e PHASE1_FIXTURE_DIR=/verify/fixtures \
  -e PLAYWRIGHT_BROWSERS_PATH=/ms-playwright \
  athenaquant-phase1-verifier:phase1 --smoke
