"""hhxg.top read-only A-share market snapshot client.

Adapts the hhxg-market static-snapshot pattern (恢恢量化) into the AthenaQuant
service layer. The upstream publishes daily post-close JSON snapshots plus
calendar/margin/news endpoints; this client fetches them read-only, caches
with a short TTL, and normalizes into plain dicts the market recap prompt
builder and a read-only API can consume.

Endpoints (verified live 2026-08):
  /api/snapshot   -> {meta, date, ai_summary, market, hot_themes, sectors,
                      ladder, ladder_detail, focus_news, macro_news, hotmoney,
                      comparison, signals_count, links}
  /api/margin     -> {data: {scope, schema_version, generated_at, window,
                      market, top_net_buy, top_net_sell}}
  /api/calendar   -> {type, month, data:[date strings]} (type=trading|delivery|
                      earnings|unlock)
  /api/news       -> {success, data:[{t, cat, title}]}

No auth; x-openai-isConsequential: false. Snapshot schema_version is checked
against SUPPORTED_SCHEMA so a server-side schema bump surfaces as a warning
instead of silently mis-shaping downstream consumers.
"""
from __future__ import annotations

import logging
import threading
import time
from typing import Any

import httpx

logger = logging.getLogger(__name__)

BASE_URL = "https://hhxg.top"
SUPPORTED_SCHEMA = 3  # snapshot meta.schema_version; bump when shapes change


class HhxgMarketClient:
    """Read-only client for hhxg.top snapshot/calendar/margin/news endpoints."""

    name = "hhxg"
    display_name = "hhxg 静态快照 (恢恢量化)"

    def __init__(self, base_url: str = BASE_URL, timeout: float = 12.0,
                 ttl_seconds: float = 600.0) -> None:
        self.base_url = base_url.rstrip("/")
        self._timeout = timeout
        # Snapshot regenerates ~20:00 daily; calendar/margin/news are low-churn.
        # 10min TTL keeps scheduled recap from re-hitting the site every run.
        self._ttl = ttl_seconds
        self._client = httpx.Client(timeout=timeout, follow_redirects=True)
        self._cache: dict[str, tuple[float, Any]] = {}
        self._lock = threading.Lock()

    def close(self) -> None:
        self._client.close()

    # -- public surface ------------------------------------------------------

    def snapshot(self, force: bool = False) -> dict | None:
        """Daily post-close market snapshot dict, or None on failure."""
        data = self._get("/api/snapshot", force=force)
        if not isinstance(data, dict):
            return None
        if data.get("success") is False:
            return None
        payload = data.get("data") if "data" in data else data
        if not isinstance(payload, dict):
            return None
        self._check_schema(payload)
        return payload

    def margin(self, force: bool = False) -> dict | None:
        """Recent 7-day margin financing/securities payload (normalized)."""
        data = self._get("/api/margin", force=force)
        if not isinstance(data, dict):
            return None
        if data.get("success") is False:
            return None
        payload = data.get("data") if "data" in data else data
        if not isinstance(payload, dict):
            return None
        return payload

    def calendar(self, type_: str = "trading", month: str | None = None,
                 force: bool = False) -> list[dict] | list[str]:
        """Calendar data.

        trading -> list of YYYY-MM-DD strings (full year; the endpoint ignores
        ``month`` for this type). unlock/earnings/delivery -> list of event
        dicts (``{date, type, label, description, count, total_value,
        top_companies}``).
        """
        params: dict[str, str] = {"type": type_}
        if month:
            params["month"] = month
        data = self._get("/api/calendar", params=params, force=force)
        if not isinstance(data, dict):
            return []
        raw = data.get("data")
        if isinstance(raw, list):
            return [str(x) for x in raw]
        if isinstance(raw, dict):
            events = raw.get("events") or []
            return [dict(e) for e in events if isinstance(e, dict)]
        return []

    def news(self, limit: int = 20, force: bool = False) -> list[dict]:
        """Latest financial news, newest first. Rows: {t, cat, title, ...}."""
        data = self._get("/api/news", params={"limit": limit}, force=force)
        if not isinstance(data, dict):
            return []
        payload = data.get("data") if "data" in data else data
        if not isinstance(payload, dict):
            return []
        items = payload.get("items") or payload.get("list") or []
        return [dict(item) for item in items if isinstance(item, dict)]

    def margin_rows(self, force: bool = False) -> list[dict]:
        """Flatten margin payload into row dicts for display/consumption."""
        payload = self.margin(force=force)
        if not payload:
            return []
        rows: list[dict] = []
        market = payload.get("market") or {}
        daily = market.get("daily_totals") or []
        for item in daily:
            if isinstance(item, dict):
                rows.append({**item, "scope": "daily_total"})
        top = payload.get("top") or {}
        for key, scope in (
            ("increase_rzye", "融资净买入"),
            ("decrease_rzye", "融资净卖出"),
            ("increase_rqye", "融券净买入"),
            ("increase_rzrqye", "两融净买入"),
        ):
            for item in top.get(key) or []:
                if isinstance(item, dict):
                    rows.append({**item, "scope": scope})
        return rows

    def calendar_events(self, type_: str = "unlock", month: str | None = None,
                        force: bool = False) -> list[dict]:
        """Calendar event dicts for unlock/earnings/delivery types."""
        return [e for e in self.calendar(type_, month, force=force) if isinstance(e, dict)]

    def snapshot_news(self, force: bool = False) -> list[dict]:
        """News embedded in the snapshot (focus + macro), normalized for recap."""
        snap = self.snapshot(force=force)
        if not snap:
            return []
        out: list[dict] = []
        for key, cat in (("focus_news", "焦点"), ("macro_news", "宏观")):
            items = snap.get(key) or []
            if isinstance(items, list):
                for item in items:
                    if not isinstance(item, dict):
                        continue
                    out.append({
                        "title": str(item.get("title") or ""),
                        "snippet": str(item.get("title") or "")[:160],
                        "source": "hhxg",
                        "published_date": str(item.get("t") or ""),
                        "category": item.get("cat") or cat,
                    })
        return out

    # -- protocol helpers -----------------------------------------------------

    def _get(self, path: str, params: dict[str, str] | None = None,
             force: bool = False) -> Any:
        cache_key = path + ("?" + "&".join(f"{k}={v}" for k, v in sorted((params or {}).items())) if params else "")
        now = time.monotonic()
        with self._lock:
            cached = self._cache.get(cache_key)
            if not force and cached is not None and now - cached[0] < self._ttl:
                return cached[1]
        try:
            resp = self._client.get(self.base_url + path, params=params)
            resp.raise_for_status()
            payload = resp.json()
        except Exception as e:
            logger.warning("hhxg %s failed: %s", path, e)
            return None
        with self._lock:
            self._cache[cache_key] = (time.monotonic(), payload)
        return payload

    def _check_schema(self, payload: dict) -> None:
        meta = payload.get("meta") or {}
        version = meta.get("schema_version")
        if isinstance(version, int) and version > SUPPORTED_SCHEMA:
            logger.warning(
                "hhxg snapshot schema v%d newer than supported v%d; shapes may mis-parse",
                version, SUPPORTED_SCHEMA,
            )
