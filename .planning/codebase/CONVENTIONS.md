# Coding Conventions

**Analysis Date:** 2026-07-10

## Naming Patterns

**Files:**
- **Python:** `snake_case.py` — e.g., `stock_analyzer.py`, `ai_generator.py`
- **TypeScript:** `kebab-case.ts` — e.g., `stock-analysis.ts`, `useSharedQueries.ts`
- **Test files:** `test_*.py` — e.g., `test_ai_generator_prompt.py`, `test_engine_portfolio.py`

**Functions:**
- **Python:** `snake_case` for all functions and methods. Private helpers prefixed with `_`. Examples:
  - `_load_kline()` — private helper in `backend/app/services/stock_analyzer.py`
  - `is_configured()` — public function in `backend/app/services/auth.py`
  - `_normalize_param_defs()` — module-internal in `backend/app/strategy/engine.py`
- **TypeScript:** `camelCase` for functions. Examples:
  - `fmtPrice()`, `fmtPct()`, `formatNumber()` — in `frontend/src/lib/format.ts`
  - `genRuleId()` — in `frontend/src/lib/api.ts`
  - `cn()` — utility in `frontend/src/lib/cn.ts`

**Variables:**
- **Python:** `snake_case` throughout. Module-level constants in `UPPER_SNAKE_CASE`. Examples:
  - `_KLINE_WINDOW = 90`, `_MAX_PERIODS = 4` — constants in `backend/app/services/stock_analyzer.py`
  - `_PBKDF2_ITER = 200_000`, `SESSION_TTL = 30 * 24 * 3600` — in `backend/app/services/auth.py`
- **TypeScript:** `camelCase`. Examples:
  - `isFormData`, `detail`, `msg` — in `frontend/src/lib/api.ts`
  - `symbol`, `open`, `high`, `low`, `close` — interface fields in `frontend/src/lib/api.ts`

**Types:**
- **Python:** `PascalCase` for classes and type aliases. Examples:
  - `Settings(BaseSettings)` — in `backend/app/config.py`
  - `StrategyDef`, `StrategyEngine` — in `backend/app/strategy/engine.py`
  - `MatcherConfig` — dataclass in `backend/app/backtest/engine.py`
  - `AssetType = Literal["stock", "index", "etf"]` — in `backend/app/data_providers/base.py`
- **TypeScript:** `PascalCase` for interfaces and types. Examples:
  - `interface BacktestResult` — in `frontend/src/lib/api.ts`
  - `type LevelType = 'sr' | 'pivot' | 'extreme' | ...` — in `frontend/src/lib/api.ts`
  - `interface PriceLevel` — in `frontend/src/lib/api.ts`

## Code Style

**Formatting:**
- **Python (ruff):** Line length 100, target version py311
  - Config: `backend/pyproject.toml` — `[tool.ruff] line-length = 100, target-version = "py311"`
  - Lint rules: `select = ["E", "F", "I", "N", "UP", "B", "SIM", "RUF"]`, ignores `E501` (line-length delegated to formatter)
- **TypeScript:** TypeScript strict mode enabled in `frontend/tsconfig.json`:
  ```
  "strict": true,
  "noUnusedLocals": true,
  "noUnusedParameters": true,
  "noFallthroughCasesInSwitch": true,
  "noUncheckedSideEffectImports": true
  ```
- **Frontend:** No ESLint or Prettier config files found (package.json has `"lint": "eslint ."` script but no config). No prettier detected.

## Import Organization

**Python:**
1. Standard library imports first (module-level `from __future__ import annotations` always first)
2. Third-party library imports
3. Application imports (relative `from app.xxx import yyy`)

Example from `backend/app/services/stock_analyzer.py`:
```python
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import AsyncIterator

import polars as pl

from app.indicators.levels import compute_levels, summarize_levels
from app.services.financial_sync import get_financial_df
```

**TypeScript:**
1. External library imports
2. Local/relative imports (using `@/` path alias)

Example from `frontend/src/lib/api.ts`:
```typescript
import { toast } from '@/components/Toast'
```

**Path Aliases:**
- TypeScript: `@/` maps to `./src/` (configured in both `tsconfig.json` and `vite.config.ts`)

## Error Handling

**Python Pattern — Logged graceful degradation:**
Errors are caught broadly, logged as warnings, and allowed to proceed rather than crashing the app. Used extensively in startup code.

```python
# From backend/app/main.py — startup sequence
try:
    from app.services import auth as auth_service
    auth_service.bootstrap_from_env()
except Exception as e:  # noqa: BLE001
    logger.warning("auth bootstrap failed: %s", e)
```

**Backend error handling conventions:**
- Broad `except Exception` catches are annotated with `# noqa: BLE001` (suppresses ruff's "Do not catch exceptions" rule)
- Always log the error with `logger.warning()` or `logger.exception()`
- Services return graceful fallback values (empty DataFrames, `None`, etc.) instead of crashing
- HTTP middleware returns structured JSON error responses with status codes
- Business logic uses custom exceptions (e.g., `CapabilityDenied` → 403)

**TypeScript Error Handling:**
- Fetch wrapper in `api.ts` parses FastAPI error responses and throws `Error` with message
- 401 responses are silently swallowed (no toast), handled globally via React Query error handler
- HTTP non-ok responses show toast via `toast(msg, 'error')`
- Global React Query `onError` catches 401/403 to redirect to login page
- Error responses are parsed from multiple possible shapes: `j.detail`, `j.message`, or array

## Logging

**Framework:**
- **Python:** Standard library `logging` module with `logging.getLogger(__name__)` at module level

**Patterns:**
```python
logger = logging.getLogger(__name__)

# Info for normal events
logger.info("ready; %d capabilities active", len(capset.all()))

# Warning for recoverable errors (no BLE suppression needed for WARNING level)
logger.warning("custom data sources init failed: %s", e)

# Exception for unexpected errors with traceback
logger.exception("AI stock analysis failed for %s: %s", symbol, e)
```
- Logging configured in `backend/app/main.py` with `basicConfig` format: `"%(asctime)s [%(levelname)s] %(name)s: %(message)s"`
- **TypeScript:** No logging framework; uses `toast()` for user-facing notifications and JavaScript `try/catch` blocks with inline error handling

## Comments

**When to Comment:**
- Module-level docstrings describe responsibility, scope, and design rationale (Chinese)
- Inline comments explain "why" not "what" — design decisions, edge cases, ADR references
- Performance notes and migration paths documented inline
- Comments use a mix of Chinese (user-facing explanations) and English (technical rationale)

**Docstring Pattern (Python):**
```python
"""Screener 服务(§6.3)。

性能优化:
  - enriched parquet 仅存 14 列基础数据, 指标和信号即时计算
...
"""
```

**"知道/不知道" responsibility annotation:**
A distinguishing convention. Module docstrings list what the module knows and doesn't know:
```python
"""AI 策略生成器 — 读取策略开发文档 + 调用 LLM 生成策略代码。

职责: 接收用户自然语言描述 → ... → 返回策略代码。
不知道: HTTP、API、前端、配置持久化、回测。
"""
```

**Section separators:**
```python
# ================================================================
# 数据加载
# ================================================================

# ── 自定义信号缓存 ─────────────────────────────────────
```

**ADR references in code comments:**
- `# ADR-19` — references architecture decisions inline
- `# §7.4` — section references to design documents

**TypeScript Comments:**
- Module-level comments describe module purpose (Chinese or English)
- `//` for single-line, `/** */` for JSDoc-style on constants and complex types
- Section comments with emoji or visual markers: `// ===== Capabilities =====`, `// ===== Screener =====`
- Inline documentation of design decisions and edge cases

## Function Design

**Size:** No enforced limits observed. Functions range from 3-120 lines. Larger functions typically are orchestrators with clear section comments.

**Parameters:**
- Python: Typed parameters, often with `| None` union types for optional params
- TypeScript: Optional params use `?` suffix, default params in signature
- Keyword-only parameters used rarely; positional params dominate

**Return Values:**
- Python: Typed return values, `None` for no return, empty `pl.DataFrame` for no data
- TypeScript: Typed Promise returns; `[key: string]: any` used for extensible interfaces
- Services return empty structures (empty DataFrames, `[]`, `{}`) rather than raising exceptions for missing data

## Module Design

**Python Backend Modules:**
- Each module has a single responsibility, documented in the module docstring
- Modules use relative imports within the `app` package
- Circular imports are avoided by using late imports (inside functions/methods). Common pattern in `backend/app/main.py` where services are imported inside the `lifespan` function
- Module-level `_lock = threading.Lock()` for thread-safe singleton state
- Module-wide caches: `_history_cache: dict`, `_custom_signal_exprs: dict | None`, `_sessions: dict[str, float]`

**TypeScript Frontend Modules:**
- Barrel files not observed
- Pages are lazy-loaded via `React.lazy()`
- Shared logic lives in `src/lib/` (stores, utilities, API client)
- Components live in `src/components/`
- Pages live in `src/pages/`
- Named exports preferred over default exports

## Exports

**Python:**
- No `__all__` observed; all public functions implicitly exported
- Private functions prefixed with `_` (not imported externally)

**TypeScript:**
- Named exports throughout (no default exports except lazy-loaded page components)
- `export const` for functions and constants
- `export interface` for types

---

*Convention analysis: 2026-07-10*
