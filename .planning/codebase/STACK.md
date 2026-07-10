# Technology Stack

**Analysis Date:** 2026-07-10

## Languages

**Primary:**
- Python >=3.11 — Backend API, data processing, scheduling, strategy engine (`backend/app/`)
- TypeScript 5.5 — Frontend SPA (`frontend/src/`)
- JavaScript (Node.js) — stock-sdk bridge plugin (`backend/app/plugins/stocksdk/bridge.mjs`)

**Secondary:**
- CSS (TailwindCSS v3) — Frontend styling (`frontend/src/index.css`, `tailwind.config.ts`)
- HTML — Single entry point (`frontend/index.html`)
- Shell (bash) — Dev scripts (`dev.sh`)
- PowerShell — Dev scripts for Windows (`dev.ps1`)

## Runtime

**Environment:**
- Backend: CPython 3.11+ (slim-bookworm in Docker), also 3.12 for desktop builds
- Frontend: Node.js 20 (for build), runs in browser via React SPA
- Node.js 18+ runtime inside Docker container for stock-sdk plugin

**Package Manager:**
- Backend: `uv` (astral-sh) — Fast Python package installer (`backend/pyproject.toml`, `backend/uv.lock`)
- Frontend: `pnpm` 9.10.0 with lockfile (`frontend/package.json`, `frontend/pnpm-lock.yaml`)
- Plugin: `npm` (stock-sdk bridge, `backend/app/plugins/stocksdk/package-lock.json`)

## Frameworks

**Core Backend:**
- FastAPI >=0.115 — Async web framework (`backend/app/main.py`)
- Uvicorn >=0.30 — ASGI server
- Pydantic >=2.7 / pydantic-settings >=2.4 — Data validation and settings management
- SSE-Starlette >=2.0 — Server-Sent Events for real-time push

**Core Frontend:**
- React 18.3 — UI library
- React Router DOM 6.26 — Client-side routing
- @tanstack/react-query 5.55 — Server state management, caching, invalidation
- Vite 5.4 — Build tool and dev server
- TailwindCSS 3.4 — Utility-first CSS framework
- tailwindcss-animate — Animation utilities
- class-variance-authority 0.7 — Component variant management
- clsx / tailwind-merge — Classname utilities

**Data Processing:**
- Polars >=1.0 — High-performance DataFrame library (primary data tool)
- DuckDB >=1.0 — Embedded analytical SQL engine
- PyArrow >=16.0 — Arrow columnar format
- Pandas >=2.2 — Limited use in BacktestService boundary
- fastexcel >=0.10 — Excel file reading via Polars

**Testing:**
- Pytest >=8.0 — Test runner
- pytest-asyncio >=0.23 — Async test support
- Ruff >=0.5 — Linter and formatter
- MyPy >=1.10 — Static type checking

**Charts:**
- ECharts 5.5 (via echarts-for-react) — Candlestick, intraday, financial charts
- lightweight-charts 4.2 — TradingView-style charts

## Key Dependencies

**Critical Backend:**
- `tickflow[all]>=0.1.23` — Official TickFlow SDK for A-share market data (primary data source)
- `openai>=1.40` — OpenAI-compatible AI provider adapter
- `httpx>=0.27` — HTTP client for AI, webhooks, custom data sources
- `apscheduler>=3.10` — Scheduling for daily pipeline, sync jobs
- `pyyaml>=6.0` — YAML parsing for tiers.yaml
- `python-dotenv>=1.0` — .env loading
- `python-multipart>=0.0.6` — File upload support

**Critical Frontend:**
- `@dnd-kit/core` 6.3 / `@dnd-kit/sortable` 10.0 — Drag-and-drop for column customizer
- `framer-motion` 11.5 — Animation library
- `lucide-react` 0.439 — Icon library

**Optional Dependencies:**
- `vectorbt>=0.26` — Backtesting engine (via `--extra backtest`)
- `pywebview>=5.0` — Desktop client window (via `--extra desktop`)
- `polars[rtcompat]>=1.0` — Legacy CPU compatibility (via `--extra legacy-cpu`)
- `winotify>=1.1` — Windows native notifications (sys_platform == 'win32')
- `plyer>=2.1` — Cross-platform desktop notifications (macOS/Linux fallback)

## Configuration

**Environment:**
- `.env` file at project root — Loaded by `python-dotenv` and `pydantic-settings`
- `backend/app/config.py::Settings` — Pydantic BaseSettings reading environment variables
- `backend/app/secrets_store.py` — User-editable secrets persisted in `data/user_data/secrets.json`
- Secrets precedence: `secrets.json` > `.env` > defaults

**Key env vars (`.env.example`):**
- `TICKFLOW_API_KEY` — A-share market data API key (empty = free mode)
- `AI_PROVIDER` — `openai_compat` | `ollama` (default: `openai_compat`)
- `AI_BASE_URL` — OpenAI-compatible endpoint (default: `https://api.deepseek.com/v1`)
- `AI_API_KEY` — AI provider API key
- `AI_MODEL` — Model name (default: `deepseek-chat`)
- `HOST` / `PORT` — Server binding (default: `0.0.0.0:3018`)
- `LOG_LEVEL` — Logging level (default: `INFO`)
- `AUTH_PASSWORD` — One-time password bootstrap (optional)
- `DATA_DIR` — Data storage path (default: `./data`)
- `BACKEND_EXTRAS` — Optional Docker build extras (`legacy-cpu`)

**Build configs:**
- `backend/pyproject.toml` — Hatchling build, Ruff lint config, pytest config
- `frontend/vite.config.ts` — Vite config with path aliases (`@/` → `./src/`), dev proxy to `:3018`, chunk splitting (echarts, lightweight-charts)
- `frontend/tsconfig.json` — TypeScript strict mode, ES2022 target, JSX react-jsx
- `frontend/tailwind.config.ts` — TailwindCSS configuration
- `frontend/postcss.config.js` — PostCSS with TailwindCSS + Autoprefixer
- `Dockerfile` — Multi-stage build (frontend → stock-sdk → Python runtime)

## Platform Requirements

**Development:**
- Python >=3.11 with `uv` installed
- Node.js >=18 with `pnpm` 9
- For stock-sdk plugin: `cd backend/app/plugins/stocksdk && npm install`
- For desktop builds: PyInstaller, optionally Inno Setup (Windows) or create-dmg (macOS)

**Production:**
- Docker (recommended) with Docker Compose
- Single-container deployment: FastAPI serves API + frontend static files
- `data/` volume mounted for persistence
- `tiers.yaml` volume mounted for capability tier configuration
- Cross-platform: linux/amd64 and linux/arm64 Docker images published to `ghcr.io`
- Desktop versions available for Windows (exe installer), macOS (Apple Silicon DMG), Linux (tar.gz)

---

*Stack analysis: 2026-07-10*
