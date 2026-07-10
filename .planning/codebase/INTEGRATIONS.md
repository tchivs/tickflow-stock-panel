# External Integrations

**Analysis Date:** 2026-07-10

## APIs & External Services

**Market Data (Primary):**
- **TickFlow API** — Primary A-share (Chinese stock market) data provider
  - SDK: `tickflow[all]>=0.1.23` (`backend/app/tickflow/client.py`)
  - Auth: `TICKFLOW_API_KEY` env var or `secrets.json` (`tickflow_api_key`)
  - Endpoints: `https://free-api.tickflow.org` (free tier) / `https://api.tickflow.org` (paid tier)
  - Custom endpoints configurable via `secrets.json` (`tickflow_base_url`)
  - Tiers: none (no key) → free → starter → pro → expert, with capability detection (`backend/app/tickflow/policy.py`)
  - Capabilities probed: quote (by_symbol, batch, pool), kline (daily, minute, batch), intraday, depth5, financial, adj_factor, websocket
  - Rate limits per capability defined in `tiers.yaml`

**Market Data (Plugin — stock-sdk):**
- **stock-sdk** — Free Node.js-based A-share market data provider (no API key required)
  - Plugin location: `backend/app/plugins/stocksdk/`
  - Runtime: Node.js >=18 (bridge via `bridge.mjs`)
  - Python entry: `app.plugins.stocksdk.provider:StockSDKProvider`
  - Datasets: daily, adj_factor, minute, realtime
  - Node deps defined in `backend/app/plugins/stocksdk/package.json`
  - Docker: Node.js runtime installed in container; plugin deps pre-built

**Market Data (Custom HTTP Sources):**
- **Generic HTTP Provider** — User-defined custom data sources
  - Implementation: `backend/app/data_providers/custom/provider.py`
  - Datasets: daily, adj_factor, minute, realtime, financial
  - Auth types: none, bearer, header, query parameter
  - Token sourced from environment variable
  - Config persisted at `data/sources/` directory

## AI Provider

**OpenAI-Compatible:**
- Provider: `openai_compat` (default) — Any OpenAI-compatible API endpoint
  - SDK: `openai>=1.40` using `AsyncOpenAI` client
  - Configuration: `AI_BASE_URL`, `AI_API_KEY`, `AI_MODEL` (in `secrets.json` or `.env`)
  - Usage: AI stock reports, market review reports, financial analysis, AI strategy building
  - Key files: `backend/app/services/ai_provider.py`, `backend/app/services/ai_reports.py`, `backend/app/services/stock_analyzer.py`
  - Streaming: supports `stream=True` for real-time text generation
  - Custom User-Agent configurable to bypass CDN/WAF bot detection (Issue #8)

**Codex CLI (Local AI):**
- Provider: `codex_cli` — OpenAI Codex CLI running locally
  - Execution: subprocess call to `codex exec` with ephemeral sandbox mode
  - Auth: reuses `~/.codex/auth.json`
  - Configuration: `ai_codex_command` (default: `codex`), `ai_model`
  - Key files: `backend/app/services/ai_provider.py` (lines 303-366, `_run_codex_cli`)
  - Service tiers supported: `fast`, `flex`

## Notification Channels

**Feishu (飞书) Group Webhook:**
- Endpoint: `https://open.feishu.cn/open-apis/bot/v2/hook/{webhook_id}`
  - Implementation: `backend/app/services/webhook_adapter.py`
  - Message types: text messages and interactive cards (lark_md for full reports)
  - Auth: optional HMAC-SHA256 signature verification
  - Retry: up to 3 attempts with exponential backoff (1s, 2s), no retry on 4xx
  - Configuration stored in preferences (`feishu_webhook_url`, `feishu_webhook_secret`)
  - URL validation prefix: `https://open.feishu.cn/open-apis/bot/v2/hook/`

**WeChat Work (企业微信) Group Webhook:**
- Endpoint: `https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key={key}`
  - Implementation: `backend/app/services/webhook_adapter.py`
  - Message types: text and native markdown (supports richer formatting than Feishu text)
  - Key-only URL format accepted (auto-normalized to full URL)
  - Rate limit: 20 messages/minute per bot
  - Configuration stored in preferences (`wecom_webhook_url`)

**WeChat Work (企业微信) Smart Bot WebSocket:**
- Connection: `wss://openws.work.weixin.qq.com` — persistent WebSocket for bidirectional communication
  - Implementation: `backend/app/services/wecom_bot_service.py`
  - Protocol: JSON frames with `aibot_subscribe` → heartbeat every 30s → receive messages/events
  - Auth: BotID + Secret (stored in preferences)
  - Reconnect: exponential backoff 5s → 60s cap, up to 10 consecutive failures
  - Single connection per bot (new connection kicks old one)
  - Supports @bot interactions, streaming replies, template cards (not yet implemented)

**Desktop Notifications:**
- Windows: `winotify` — Windows action center notifications
- macOS: `osascript` — AppleScript `display notification`
- Linux: `notify-send` — freedesktop.org standard
- Implementation: `backend/app/services/notify_adapter.py`

## Data Storage

**Databases:**
- **DuckDB >=1.0** — Embedded analytical database for market data querying via SQL
  - Client: duckdb Python library
  - Usage: complex analytical queries, data exploration
- **Parquet files** — Columnar storage for all market data
  - Primary storage format via Polars/DuckDB
  - Partitioned by date: `data/kline_daily/date=YYYY-MM-DD/`, `data/kline_minute/`, `data/depth5/`, etc.
  - Key directories: `data/kline_daily/`, `data/kline_daily_enriched/`, `data/kline_minute/`, `data/kline_adj/`, `data/depth5/`, `data/financials/`, `data/ext_data/`
- **Polars DataFrame** — In-memory data processing, enriched cache
  - `_enriched_cache` in `QuoteService` for intraday trading data with technical indicators

**File Storage:**
- Local filesystem only — `data/` directory at project root (or `DATA_DIR` env var)
  - Subdirectories: `data/user_data/` (secrets.json, preferences, auth.json), `data/strategies/` (custom/ai strategies), `data/sources/` (custom data source configs)
  - Docker: `data/` volume mounted into container at `/app/data`

**Caching:**
- **capabilities.json** — Persisted capability probe results at `data/capabilities.json`
- **Polars enriched cache** — In-memory cached enriched market data with technical indicators
- **SSE-based real-time push** — Server-Sent Events for live quote updates, strategy alerts, depth updates
- **React Query cache** — Frontend-side query caching with TanStack React Query

## Authentication & Identity

**Auth Provider:**
- **Custom password-based auth** — No external auth provider
  - Implementation: `backend/app/api/auth.py`, `backend/app/services/auth.py`
  - Password stored as hash in `data/user_data/auth.json`
  - Session tracked via cookie (`session_token`) with in-memory session store
  - Bootstrap via `AUTH_PASSWORD` env var (one-time initialization)
  - Middleware: `backend/app/main.py` lines 242-272 — auth middleware for `/api/` routes
  - Whitelist: `/api/auth/*`, `/health`, `/openapi.json`, `/docs`, `/redoc`

## Monitoring & Observability

**Error Tracking:**
- None — No external error tracking service (Sentry, etc.) detected
  - Errors logged via Python `logging` module to stdout/stderr

**Logs:**
- Python `logging` configured in `backend/app/main.py` (line 23-26)
  - Format: `%(asctime)s [%(levelname)s] %(name)s: %(message)s`
  - Level configurable via `LOG_LEVEL` env var
  - Docker: logs go to container stdout/stderr

**Health Checks:**
- Endpoint: `GET /health` — Returns status, version, mode
- Endpoint: `GET /api/health` — Alias for health check
- Endpoint: `GET /api/intraday/status` — Real-time quote service status

## CI/CD & Deployment

**Hosting:**
- **Docker** — Primary deployment method (single container)
  - Registry: `ghcr.io` (GitHub Container Registry)
  - Image: `ghcr.io/{repository}` — multi-arch: `linux/amd64`, `linux/arm64`
  - Docker Compose with persistent data volume
- **Desktop** — Standalone installers for Windows (exe via Inno Setup), macOS (DMG via create-dmg), Linux (tar.gz)
  - Built with PyInstaller packaging

**CI Pipeline:**
- **GitHub Actions** — Two workflows:
  - `.github/workflows/docker.yml` — Build and push Docker image to ghcr.io on push to main / v* tag
  - `.github/workflows/release.yml` — Manual desktop client release workflow (cross-platform: Windows, macOS Apple Silicon, Linux)

**Environment Configuration:**
- `.env` file for secrets and settings
- Docker: `env_file` directive + `environment` overrides
- Secrets stored in `data/user_data/secrets.json` (chmod 600)

## Webhooks & Callbacks

**Incoming:**
- None — The system does not expose webhook endpoints for external callbacks

**Outgoing:**
- **Feishu Group Webhook** — Push alert events and market review reports
- **WeChat Work Group Webhook** — Push alert events and market review reports
- **WeChat Work Smart Bot** — Bidirectional WebSocket (connection incoming, messages outgoing)
- Triggered by: monitor rule engine alerts (`backend/app/strategy/monitor.py`), scheduled market review reports
- Channel configuration per alert rule: `webhook_channels` field in `MonitorRule` (`['feishu', 'wecom']`)

## Endpoint Discovery

**Endpoints Manifest:**
- Remote: `tickflow.org/endpoints.json` — Proxied via backend (`/api/settings/endpoints`) to avoid CORS
- Fallback: built-in list if remote unavailable
- Test: `POST /api/settings/test_endpoint` — Multi-round latency probing with median calculation

## Optional Plugin Integrations

**Plugin System:**
- Architecture: `backend/app/plugins/` directory
  - Each plugin has `plugin.yaml` with name, runtime, entry point, datasets
  - Current: `stocksdk` (Node.js, free A-share data)
  - Detection: `available` flag checks if deps installed
  - Install/Uninstall: via settings UI API (`/api/settings/plugins/{name}/install`)

---

*Integration audit: 2026-07-10*
