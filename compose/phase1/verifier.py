"""Deterministic Phase 1 fixture acceptance authority."""
from __future__ import annotations

import argparse
import os
import shutil
import threading
import time
from pathlib import Path
from typing import Any

import httpx

BASE_URL = os.environ.get("PHASE1_BASE_URL", "http://phase1-fixture:3018").rstrip("/")
RECEIVER_URL = "http://receiver:8080/outcomes"
FIXTURE_DIR = Path(os.environ.get("PHASE1_FIXTURE_DIR", "/verify/fixtures"))
FIXTURE_ENDPOINTS = {
    "PHASE1_FEISHU_RECEIVER_URL": "http://receiver:8080/feishu",
    "PHASE1_TELEGRAM_RECEIVER_URL": "http://receiver:8080/telegram",
}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def smoke() -> None:
    """Validate only local image contents; Docker runs this with --network none."""
    from app.contracts.market_data import FixtureBundle

    bundle = FixtureBundle.load(FIXTURE_DIR)
    require(len(bundle.instruments) == 1, "fixture smoke requires one deterministic instrument")
    require(len(bundle.daily) >= 15, "fixture smoke requires enough daily history")
    browsers_path = Path(os.environ.get("PLAYWRIGHT_BROWSERS_PATH", "/ms-playwright"))
    require(any(browsers_path.glob("chromium-*")), "prepared verifier image lacks Chromium")
    require(shutil.which("node") is not None and shutil.which("pnpm") is not None, "prepared verifier image lacks Node/pnpm")
    print("phase1 verifier smoke passed")


def wait_for_health(client: httpx.Client) -> None:
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        try:
            response = client.get(f"{BASE_URL}/health")
            if response.status_code == 200 and response.json().get("status") == "ok":
                return
        except httpx.HTTPError:
            pass
        time.sleep(1)
    raise RuntimeError("app did not become healthy")


def response_json(response: httpx.Response, expected: int) -> dict[str, Any]:
    require(response.status_code == expected, f"{response.request.method} {response.request.url} returned {response.status_code}: {response.text}")
    payload = response.json()
    require(isinstance(payload, dict), "API response must be an object")
    return payload


def assert_fixture_delivery_guard() -> None:
    require(os.environ.get("PHASE1_FIXTURE_MODE", "").lower() in {"1", "true", "yes"}, "fixture mode is not enabled")
    for name, expected in FIXTURE_ENDPOINTS.items():
        require(os.environ.get(name) == expected, f"external fixture delivery target rejected: {name}")


def collect_sse(events: list[str], ready: threading.Event, stop: threading.Event) -> None:
    try:
        with httpx.Client(timeout=httpx.Timeout(30, connect=5)) as client:
            with client.stream("GET", f"{BASE_URL}/api/intraday/stream") as response:
                require(response.status_code == 200, "SSE endpoint unavailable")
                ready.set()
                for line in response.iter_lines():
                    if line.startswith("event:"):
                        events.append(line.split(":", 1)[1].strip())
                    if stop.is_set() and {"strategy_alert", "portfolio_updated"}.issubset(events):
                        return
    finally:
        ready.set()


def exercise_api_sse_and_delivery(client: httpx.Client) -> None:
    sync = response_json(client.get(f"{BASE_URL}/api/pipeline/phase1-fixture"), 200)
    require(sync.get("provider") == "fixture" and "done" in sync.get("stages", []), "fixture sync report is incomplete")
    instruments = response_json(client.get(f"{BASE_URL}/api/kline/instruments/search", params={"q": "600519"}), 200)
    require(any(row.get("symbol") == "600519.SH" for row in instruments.get("results", [])), "fixture instrument is unavailable through API")

    events: list[str] = []
    ready = threading.Event()
    stop = threading.Event()
    listener = threading.Thread(target=collect_sse, args=(events, ready, stop), daemon=True)
    listener.start()
    require(ready.wait(10), "SSE listener did not connect")

    account = response_json(client.post(f"{BASE_URL}/api/portfolio/accounts", json={"name": "验收预置账户", "available_funds": 50000}), 201)["account"]
    position = response_json(client.post(f"{BASE_URL}/api/portfolio/positions", json={
        "account_id": account["id"], "instrument_symbol": "600519.SH", "cost_price": 1500,
        "quantity": 2, "invested_amount": 3000, "trading_style": "swing",
    }), 201)["position"]
    summary = response_json(client.get(f"{BASE_URL}/api/portfolio/summary"), 200)
    require(summary.get("positions"), "SQLite-backed portfolio summary is empty")

    rule = {
        "id": "phase1_price_rule", "name": "fixture delivery rule", "type": "price", "scope": "symbols",
        "symbols": ["600519.SH"], "conditions": [{"field": "close", "op": ">", "value": 1}],
        "webhook_channels": ["feishu", "telegram"], "cooldown_seconds": 0, "severity": "critical",
    }
    response_json(client.post(f"{BASE_URL}/api/monitor-rules", json=rule), 200)
    response_json(client.post(f"{BASE_URL}/api/intraday/phase1-trigger"), 200)

    deadline = time.monotonic() + 20
    outcomes: list[dict[str, str]] = []
    while time.monotonic() < deadline:
        outcomes_payload = response_json(client.get(RECEIVER_URL), 200)
        outcomes = outcomes_payload.get("outcomes", [])
        if {outcome.get("channel") for outcome in outcomes} == {"feishu", "telegram"}:
            break
        time.sleep(0.25)
    require({outcome.get("channel") for outcome in outcomes} == {"feishu", "telegram"}, "receiver did not capture both fixture deliveries")

    run = response_json(client.post(f"{BASE_URL}/api/decision/runs", json={"symbol": "600519.SH", "as_of": "2024-01-29"}), 201)
    review = response_json(client.post(f"{BASE_URL}/api/decision/runs/{run['id']}/review"), 200)
    require(review.get("review_status") == "unavailable", "fixture AI review must remain disabled")
    replay = response_json(client.post(f"{BASE_URL}/api/decision/replay", json={"run_ids": [run["id"]], "as_of": "2024-01-29"}), 201)
    require(replay.get("provider") is None and replay.get("model") is None, "fixture replay invoked a provider")

    deadline = time.monotonic() + 10
    while time.monotonic() < deadline and not {"strategy_alert", "portfolio_updated"}.issubset(events):
        time.sleep(0.1)
    stop.set()
    listener.join(timeout=5)
    require({"strategy_alert", "portfolio_updated"}.issubset(events), f"missing named SSE events: {events}")
    require(position["account_id"] == account["id"], "position was not persisted for its account")


def run_browser_suite() -> None:
    import subprocess

    environment = dict(
        os.environ,
        PHASE1_BASE_URL=BASE_URL,
        NO_PROXY="phase1-fixture,receiver,localhost,127.0.0.1",
        no_proxy="phase1-fixture,receiver,localhost,127.0.0.1",
        HTTP_PROXY="",
        HTTPS_PROXY="",
        ALL_PROXY="",
    )
    result = subprocess.run(
        ["pnpm", "--dir", "/verify/frontend", "exec", "playwright", "test"],
        env=environment,
        check=False,
    )
    require(result.returncode == 0, "desktop/mobile Playwright fixture workflow failed")


def accept() -> None:
    assert_fixture_delivery_guard()
    with httpx.Client(timeout=httpx.Timeout(15, connect=5)) as client:
        wait_for_health(client)
        exercise_api_sse_and_delivery(client)
    run_browser_suite()
    print("phase1 fixture acceptance passed")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--smoke", action="store_true")
    args = parser.parse_args()
    if args.smoke:
        smoke()
    else:
        accept()


if __name__ == "__main__":
    main()
