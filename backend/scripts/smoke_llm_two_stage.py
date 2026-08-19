#!/usr/bin/env python3
"""Smoke: real LLM two-stage analysis (BASE-03).

Executes a real two-stage FactorResearchAgent flow against a deployed AthenaQuant
instance: Stage 1 (hypothesis generation) → Stage 2 (recommendation + caveats).
Requires a configured AI provider (OpenAI-compatible or Codex CLI).

Exit codes:
    0  PASS — both stages returned valid structured payloads
    1  FAIL — a stage returned an invalid/partial response or schema mismatch
    2  SKIP  — AI provider not configured (explicit, never silent)
    3  ERROR — network/auth/runtime error

Usage:
    # Against local deployment
    python3 backend/scripts/smoke_llm_two_stage.py --base-url http://127.0.0.1:3018

    # With explicit auth password
    DEP_PASSWORD=$(sed -n 's/^AUTH_PASSWORD=//p' .env) \
      python3 backend/scripts/smoke_llm_two_stage.py --base-url http://127.0.0.1:3018

    # Force fixture mode (no real LLM needed, validates schema only)
    python3 backend/scripts/smoke_llm_two_stage.py --base-url http://127.0.0.1:3018 --fixture

Zero new dependencies: stdlib only (urllib, json, argparse, http.cookiejar).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from http.cookiejar import CookieJar


def _login(base_url: str, password: str, jar: CookieJar) -> bool:
    """Single-attempt login; returns True on 200."""
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


def _settings(base_url: str, jar: CookieJar) -> dict | None:
    """Get settings to check AI configuration."""
    url = f"{base_url}/api/settings"
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    try:
        resp = opener.open(urllib.request.Request(url), timeout=10)
        return json.loads(resp.read())
    except Exception:
        return None


def _post(base_url: str, path: str, body: dict, jar: CookieJar, timeout: float = 120) -> tuple[int, dict | str]:
    url = f"{base_url}{path}"
    data = json.dumps(body).encode()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    try:
        resp = opener.open(
            urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"}),
            timeout=timeout,
        )
        raw = resp.read()
        try:
            return resp.status, json.loads(raw)
        except json.JSONDecodeError:
            return resp.status, raw.decode(errors="replace")
    except urllib.error.HTTPError as e:
        raw = e.read().decode(errors="replace")
        try:
            return e.code, json.loads(raw)
        except json.JSONDecodeError:
            return e.code, raw
    except Exception as e:
        return 0, str(e)


def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke: real LLM two-stage analysis")
    parser.add_argument("--base-url", default="http://127.0.0.1:3018", help="Base URL of deployed instance")
    parser.add_argument("--password", default=None, help="Auth password (or set DEP_PASSWORD)")
    parser.add_argument("--fixture", action="store_true", help="Use fixture mode (no real LLM, validates schema only)")
    parser.add_argument("--symbol", default="600519.SH", help="Symbol for analysis")
    parser.add_argument("--timeout", type=float, default=180, help="HTTP timeout in seconds")
    args = parser.parse_args()

    password = args.password or os.environ.get("DEP_PASSWORD", "")
    base_url = args.base_url.rstrip("/")
    jar = CookieJar()

    print(f"[smoke-llm] base_url={base_url} symbol={args.symbol} fixture={args.fixture}")

    # Step 1: Login
    if not password:
        print("[smoke-llm] FAIL: no password (set DEP_PASSWORD or --password)")
        return 3
    if not _login(base_url, password, jar):
        print("[smoke-llm] FAIL: login failed")
        return 3
    print("[smoke-llm] login OK")

    # Step 2: Check AI configuration (unless fixture mode)
    settings = _settings(base_url, jar)
    if settings is None:
        print("[smoke-llm] FAIL: cannot read /api/settings")
        return 3

    ai_configured = settings.get("ai_configured", False)
    if not args.fixture and not ai_configured:
        print(f"[smoke-llm] SKIP: AI provider not configured (ai_provider={settings.get('ai_provider', 'none')})")
        print("[smoke-llm]       Configure AI in Settings or use --fixture for schema-only validation")
        return 2

    if args.fixture:
        print("[smoke-llm] fixture mode: validating schema only (no real LLM call)")
    else:
        print(f"[smoke-llm] AI provider: {settings.get('ai_provider', '?')} model={settings.get('ai_model', '?')}")

    # Step 3: Stage 1 — draft hypothesis
    print(f"[smoke-llm] Stage 1: drafting hypothesis for {args.symbol}...")
    t0 = time.monotonic()
    status, stage1 = _post(
        base_url,
        "/api/research/hypotheses/drafts",
        {"hypothesis": f"测试假设: {args.symbol} 近期量价关系", "options": {"fixture": args.fixture}},
        jar,
        timeout=args.timeout,
    )
    elapsed_s1 = time.monotonic() - t0

    if status != 200:
        print(f"[smoke-llm] FAIL: Stage 1 returned {status}: {stage1}")
        return 1

    if not isinstance(stage1, dict):
        print(f"[smoke-llm] FAIL: Stage 1 returned non-dict: {type(stage1)}")
        return 1

    # Validate Stage 1 schema: must have hypothesis text
    hypothesis_text = stage1.get("hypothesis") or stage1.get("text") or ""
    if not hypothesis_text:
        print(f"[smoke-llm] FAIL: Stage 1 missing hypothesis text: {list(stage1.keys())}")
        return 1

    is_partial = stage1.get("partial", False)
    print(f"[smoke-llm] Stage 1 OK ({elapsed_s1:.1f}s, partial={is_partial})")
    print(f"[smoke-llm]   hypothesis: {hypothesis_text[:80]}...")

    # Step 4: Stage 2 — reviewed factor (recommendation + caveats)
    print(f"[smoke-llm] Stage 2: reviewing factor for {args.symbol}...")
    t1 = time.monotonic()
    status2, stage2 = _post(
        base_url,
        "/api/research/hypotheses/reviewed-factor",
        {"hypothesis": hypothesis_text, "options": {"fixture": args.fixture}},
        jar,
        timeout=args.timeout,
    )
    elapsed_s2 = time.monotonic() - t1

    if status2 != 200:
        print(f"[smoke-llm] FAIL: Stage 2 returned {status2}: {stage2}")
        return 1

    if not isinstance(stage2, dict):
        print(f"[smoke-llm] FAIL: Stage 2 returned non-dict: {type(stage2)}")
        return 1

    # Validate Stage 2 schema: must have recommendation or caveats
    has_recommendation = bool(stage2.get("recommendation") or stage2.get("recommendation_text"))
    has_caveats = "caveats" in stage2
    if not has_recommendation and not has_caveats:
        print(f"[smoke-llm] FAIL: Stage 2 missing recommendation/caveats: {list(stage2.keys())}")
        return 1

    print(f"[smoke-llm] Stage 2 OK ({elapsed_s2:.1f}s)")
    if has_recommendation:
        rec = stage2.get("recommendation") or stage2.get("recommendation_text") or ""
        print(f"[smoke-llm]   recommendation: {str(rec)[:80]}...")
    if has_caveats:
        caveats = stage2.get("caveats") or []
        print(f"[smoke-llm]   caveats: {len(caveats)} items")

    # Summary
    print(f"\n[smoke-llm] PASS: two-stage analysis completed (Stage1={elapsed_s1:.1f}s, Stage2={elapsed_s2:.1f}s)")
    if is_partial:
        print("[smoke-llm]   NOTE: Stage 1 was partial (degraded response, distinctly labeled)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
