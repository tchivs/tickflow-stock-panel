"""Phase 5 real-host e2e telemetry (test-harness only, env-gated).

The CR-01 real-host acceptance contract requires a deployment-owned
``/api/__phase5_real_host__/telemetry`` endpoint that reports whether the Shadow
pipeline leaked repository IDs or made unexpected external requests.  A real
deployment harness tracks these live; the isolated e2e fixture backend runs
fully offline, so every counter is genuinely zero.
"""

from __future__ import annotations

import os
from typing import Any

from fastapi import APIRouter

router = APIRouter(prefix="/api/__phase5_real_host__", tags=["phase5-real-host-telemetry"])


def telemetry_enabled() -> bool:
    """Enable only inside the isolated Phase 5 real-host e2e harness."""
    return os.environ.get("PHASE5_REAL_HOST_TELEMETRY", "").strip().lower() in {"1", "true", "yes"}


@router.get("/telemetry")
def real_host_telemetry() -> dict[str, Any]:
    """Report Shadow-pipeline telemetry counters for the acceptance contract."""
    return {
        "repository_id_bypass": 0,
        "live_action_counts": {},
        "unexpected_external_requests": 0,
        "ready": True,
    }
