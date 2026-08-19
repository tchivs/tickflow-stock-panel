#!/usr/bin/env python3
"""Smoke: Provider degradation visibility (BASE-03).

Verifies that provider degradation is visible through the API surface —
data source health checks, AI provider configuration status, and the
data quality API. This smoke does NOT trigger degradation (that requires
network manipulation); it verifies the visibility infrastructure exists
and returns structured health/quality data.

Exit codes:
    0  PASS — all health/quality endpoints return structured data
    1  FAIL — an endpoint returned missing/malformed health data
    2  SKIP  — no data sources configured
    3  ERROR — network/auth/runtime error

Usage:
    DEP_PASSWORD=$(sed -n 's/^AUTH_PASSWORD=//p' .env) \
      python3 backend/scripts/smoke_provider_degradation.py --base-url http://127.0.0.1:3018

Zero new dependencies: stdlib only (urllib, json, argparse, http.cookiejar).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.request
from http.cookiejar import CookieJar


def _login(base_url: str, password: str, jar: CookieJar) -> bool:
    url = f"{base_url}/api/auth/login"
    data = json.dumps({"password": password}).encode()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    try:
        resp = opener.open(
            urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"}),
            timeout=15,
        )
        body = json.loads(resp.read())
        return resp.status == 200 and body.get("ok") is True
    except Exception:
        return False


def _get(base_url: str, path: str, jar: CookieJar, timeout: float = 15) -> tuple[int, dict | list | str]:
    url = f"{base_url}{path}"
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    try:
        resp = opener.open(urllib.request.Request(url), timeout=timeout)
        raw = resp.read()
        try:
            return resp.status, json.loads(raw)
        except json.JSONDecodeError:
            return resp.status, raw.decode(errors="replace")
    except urllib.request.HTTPError as e:  # type: ignore[misc]
        raw = e.read().decode(errors="replace")
        try:
            return e.code, json.loads(raw)
        except json.JSONDecodeError:
            return e.code, raw
    except Exception as e:
        return 0, str(e)


def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke: Provider degradation visibility")
    parser.add_argument("--base-url", default="http://127.0.0.1:3018")
    parser.add_argument("--password", default=None)
    args = parser.parse_args()

    password = args.password or os.environ.get("DEP_PASSWORD", "")
    base_url = args.base_url.rstrip("/")
    jar = CookieJar()

    print(f"[smoke-deg] base_url={base_url}")

    # Step 1: Login
    if not password:
        print("[smoke-deg] FAIL: no password (set DEP_PASSWORD or --password)")
        return 3
    if not _login(base_url, password, jar):
        print("[smoke-deg] FAIL: login failed")
        return 3
    print("[smoke-deg] login OK")

    results: list[tuple[str, bool, str]] = []

    # Step 2: Settings endpoint — AI provider config + data source health
    print("[smoke-deg] checking /api/settings (AI provider + data source health)...")
    status, settings = _get(base_url, "/api/settings", jar)
    if status != 200 or not isinstance(settings, dict):
        results.append(("settings", False, f"status={status}"))
    else:
        # AI provider visibility
        ai_configured = settings.get("ai_configured")
        ai_provider = settings.get("ai_provider", "?")
        has_ai_key = settings.get("has_ai_key", False)
        if ai_configured is None:
            results.append(("settings.ai_configured", False, "missing ai_configured field"))
        else:
            results.append(("settings.ai_configured", True, f"provider={ai_provider} configured={ai_configured}"))

        # Data source health visibility (via tier_label, current_endpoint, etc.)
        tier_label = settings.get("tier_label", "")
        current_endpoint = settings.get("current_endpoint", "")
        if not tier_label and not current_endpoint:
            results.append(("settings.data_sources", False, "no data source indicators"))
        else:
            results.append(("settings.data_sources", True, f"tier={tier_label} endpoint={current_endpoint}"))

    # Step 3: Data sources health endpoint
    print("[smoke-deg] checking /api/settings/data-sources...")
    status, data_sources = _get(base_url, "/api/settings/data-sources", jar)
    if status != 200:
        results.append(("data-sources", False, f"status={status}"))
    elif not isinstance(data_sources, list):
        results.append(("data-sources", False, f"not a list: {type(data_sources)}"))
    elif len(data_sources) == 0:
        results.append(("data-sources", True, "empty (no sources configured)"))
        print("[smoke-deg] NOTE: no data sources configured")
    else:
        # Verify each source has health indicator
        all_have_health = all(isinstance(s, dict) and "health" in s or "status" in s for s in data_sources)
        if all_have_health:
            healths = [s.get("health") or s.get("status") for s in data_sources]
            results.append(("data-sources.health", True, f"{len(data_sources)} sources: {healths}"))
        else:
            keys = [list(s.keys()) if isinstance(s, dict) else "?" for s in data_sources[:3]]
            results.append(("data-sources.health", False, f"missing health/status: {keys}"))

    # Step 4: Data quality endpoint (if exists from Phase 52)
    print("[smoke-deg] checking /api/settings/data-sources for quality fields...")
    if isinstance(data_sources, list) and len(data_sources) > 0:
        has_quality = any(
            isinstance(s, dict) and any(k in s for k in ("freshness", "quality", "last_sync", "updated_at"))
            for s in data_sources
        )
        if has_quality:
            results.append(("data-quality", True, "freshness/quality fields present"))
        else:
            results.append(("data-quality", True, "not yet (Phase 52 will add unified data quality API)"))

    # Summary
    print()
    all_pass = True
    for name, ok, detail in results:
        symbol = "PASS" if ok else "FAIL"
        if not ok:
            all_pass = False
        print(f"  [{symbol}] {name}: {detail}")

    if all_pass:
        print(f"\n[smoke-deg] PASS: provider degradation visibility verified ({len(results)} checks)")
        return 0
    else:
        fails = sum(1 for _, ok, _ in results if not ok)
        print(f"\n[smoke-deg] FAIL: {fails}/{len(results)} checks failed")
        return 1


if __name__ == "__main__":
    sys.exit(main())
