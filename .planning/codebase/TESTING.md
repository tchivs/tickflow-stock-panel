# Testing Patterns

**Analysis Date:** 2026-07-10

## Test Framework

**Runner:**
- **pytest** `>=8.0` (specified in `backend/pyproject.toml` `[project.optional-dependencies] dev` section)
- **pytest-asyncio** `>=0.23` — async test support with `asyncio_mode = "auto"`
- Config: `backend/pyproject.toml`:
  ```toml
  [tool.pytest.ini_options]
  asyncio_mode = "auto"
  ```

**Frontend:**
- **No test framework detected** — no `jest`, `vitest`, or other test config files found in `frontend/`
- `frontend/package.json` has no test script or test dependencies

**Run Commands:**
```bash
cd backend && uv run pytest              # Run all tests
cd backend && uv run pytest -x           # Stop on first failure
cd backend && uv run pytest -v           # Verbose output
cd backend && uv run pytest -k test_name # Filter by test name
cd backend && uv run pytest tests/backtest/  # Run subdirectory
```

## Test File Organization

**Location:**
- `backend/tests/` — root test directory for the Python backend
- `backend/tests/backtest/` — subdirectory for backtest-specific tests

**Naming:**
- Files: `test_*.py` — e.g., `test_ai_generator_prompt.py`, `test_stocksdk_provider.py`
- Test functions: `test_*` — e.g., `test_max_exposure_sets_target_position_and_caps_count`
- Classes: Not used; all tests are module-level functions

**Structure:**
```
backend/tests/
├── test_ai_generator_prompt.py
├── test_ai_provider.py
├── test_ai_strategy_meta_normalize.py
├── test_backtest_etf.py
├── test_depth_continuous_trading.py
├── test_high_turnover_strategy.py
├── test_monitor_etf.py
├── test_parquet_schema_compat.py
├── test_pipeline_and_monitor_fixes.py
├── test_realtime_turnover_rate.py
├── test_screener_etf.py
├── test_st_limit_and_sharpe.py
├── test_stocksdk_provider.py
├── test_strategy_build_stream.py
├── test_strategy_code_save.py
├── test_strategy_detail_signals.py
├── test_strategy_param_normalize.py
├── test_strategy_realtime_refresh.py
├── test_watchlist_enriched_join.py
├── backtest/
│   ├── test_cost_model.py
│   ├── test_engine_portfolio.py
│   ├── test_full_simulation_tail.py
│   ├── test_optimizer_api.py
│   ├── test_optimizer_grid.py
│   ├── test_optimizer_run.py
│   ├── test_robustness_metrics.py
│   └── test_strategy_backtest_correctness.py
```
Total: 26 test files

## Test Structure

**Suite Organization:**

Tests are pure module-level functions — no test classes, no fixtures framework (minimal use of `@pytest.fixture`).

```python
# From backend/tests/test_ai_generator_prompt.py
from __future__ import annotations

from app.strategy.ai_generator import GUIDE_PATH, AIStrategyGenerator
from app.strategy.prompt_builder import build_step1


def test_ai_strategy_generator_uses_compact_guide():
    assert GUIDE_PATH.name == "strategy-guide-compact.md"
    guide = AIStrategyGenerator()._get_guide()
    assert "AI 策略生成精简指南" in guide
    assert "策略示例" not in guide
    assert len(guide) < 5000


def test_build_step1_keeps_user_prompt_compact():
    prompt = build_step1(
        "测试策略", "测试描述", "long",
        "1. 收盘价站上MA20\n2. 成交量放大\n3. RSI 不过热",
        "ai_test",
    )
    assert "# 步骤 1：根据规则生成完整策略" not in prompt
    assert "策略ID（必须使用此ID）：ai_test" in prompt
    assert len(prompt) < 1000
```

**Patterns:**
- Pure business-logic tests that call functions directly — no HTTP mocking, no integration tests against running services
- Tests import production code directly from `app.xxx`
- Minimal setup — each test constructs its input inline
- Helper factory functions at module level for reusable test data

## Mocking

**Framework:** `monkeypatch` (pytest built-in) — no external mocking library used (no `unittest.mock`, no `pytest-mock`)

**Patterns:**
```python
# From backend/tests/test_stocksdk_provider.py
def _patch_run_job(monkeypatch, mapping):
    """mapping: op -> payload dict(将作为 run_job 返回值)。"""
    def fake(job, timeout=None):
        return mapping[job["op"]]
    monkeypatch.setattr(sp.bridge, "run_job", fake)


def test_get_daily_normalizes_and_echoes_symbol(monkeypatch):
    _patch_run_job(monkeypatch, {
        "daily": {"ok": True, "op": "daily", "rows": {
            "600519.SH": [
                {"date": "2026-01-05", "open": 1385.0, ...},
            ],
        }},
    })
    df = StockSDKProvider().get_daily(...)
    assert df.columns == ["symbol", "date", "open", ...]
    assert df.height == 2
```

**What to Mock:**
- External subprocess calls (`subprocess.run`, node bridge)
- Network I/O (bridge runs, API calls)
- Side effects (file writes, environment checks)
- Availability checks in plugin loading

**What NOT to Mock:**
- Business logic transformation (normalization, filtering, calculation)
- Polars DataFrame operations
- Data structure validation

## Fixtures and Factories

**Test Data:** No `conftest.py` found. Test data is created inline via factory functions defined at the module level.

```python
# From backend/tests/backtest/test_engine_portfolio.py
def _panel(symbols: list[str], days: int = 4, price: float = 10.0,
           overrides: dict[tuple[str, int], dict] | None = None) -> pl.DataFrame:
    overrides = overrides or {}
    start = date(2024, 1, 1)
    rows = []
    for sym in symbols:
        for i in range(days):
            patch = overrides.get((sym, i), {})
            rows.append({
                "symbol": sym, "name": sym,
                "date": start + timedelta(days=i),
                "open": patch.get("open", price),
                "high": patch.get("high", price),
                ...
            })
    return pl.DataFrame(rows).sort(["symbol", "date"])

def _mask(panel: pl.DataFrame, marks: set[tuple[str, int]]) -> pl.Series:
    values = []
    base = date(2024, 1, 1)
    for row in panel.select(["symbol", "date"]).iter_rows(named=True):
        day = (row["date"] - base).days
        values.append((row["symbol"], day) in marks)
    return pl.Series(values, dtype=pl.Boolean)
```

**Other factory patterns seen in the codebase:**
```python
# From backend/tests/test_st_limit_and_sharpe.py
def _two_day(symbol: str, prev_close: float, today_close: float) -> pl.DataFrame:
    """2 日最小输入: 首日平收, 次日收于 today_close。"""
    return pl.DataFrame({...})

# From backend/tests/test_realtime_turnover_rate.py
def _today_rows(turnover_rate: float | None = None) -> pl.DataFrame:
    row = {"symbol": "600000.SH", "open": 10.0, ...}
    if turnover_rate is not None:
        row["turnover_rate"] = turnover_rate
    return pl.DataFrame([row])
```

**Location:** Factory functions are defined within each test file (no shared fixture modules).

## Coverage

**Requirements:** No coverage configuration detected. No `.coveragerc`, `pyproject.toml` coverage config, or coverage dependency found.

**View Coverage:**
```bash
# If needed, install and run:
cd backend && uv add pytest-cov && uv run pytest --cov=app
```

## Test Types

**Unit Tests:**
- **Scope:** Pure logic, single-function/module tests
- **Approach:** Import production functions, pass test data, assert on results
- **Examples:** `test_ai_generator_prompt.py`, `test_strategy_param_normalize.py`, `test_parquet_schema_compat.py`
- Heavily tested areas: Backtest engine portfolio simulation (423 lines, 12 tests in `test_engine_portfolio.py`), StockSDK provider (228 lines, 10 tests in `test_stocksdk_provider.py`)

**Integration Tests:**
- **Scope:** Not clearly separated from unit tests; tests that exercise multiple components
- **Examples:** `test_stocksdk_provider.py` tests the full bridge/provider pipeline (with monkeypatched bridge), `test_pipeline_and_monitor_fixes.py` exercises pipeline + monitor interaction
- No dedicated integration test directory

**E2E Tests:**
- **Not used** — no E2E testing framework detected (no Playwright, no Cypress)

## Common Patterns

**Async Testing:**
```python
# From backend/tests/backtest/test_optimizer_api.py
import asyncio

def test_cancel_looks_up_job_by_echoed_key():
    from app.api.backtest import _BacktestJob, _running_jobs, optimize_cancel

    class _Req:
        def __init__(self, body):
            self._body = body
        async def json(self):
            return self._body

    key = "optkey_test_1"
    job = _BacktestJob(key)
    _running_jobs[key] = job
    try:
        res = asyncio.run(optimize_cancel(_Req({"job_key": key})))
        assert res["ok"] is True
        assert job.cancel_event.is_set()
    finally:
        _running_jobs.pop(key, None)
```
- `asyncio_mode = "auto"` allows async test functions (not observed in current tests — all use `asyncio.run()` inside synchronous test functions)
- `@pytest.mark.asyncio` not used

**Error Testing:**
```python
# From backend/tests/test_stocksdk_provider.py
def test_bridge_error_degrades_to_empty(monkeypatch):
    def boom(job, timeout=None):
        raise sp.bridge.StockSDKBridgeError("node missing")
    monkeypatch.setattr(sp.bridge, "run_job", boom)
    assert StockSDKProvider().get_daily(["600519.SH"], None, None).is_empty()
    assert StockSDKProvider().get_realtime() == []
    assert StockSDKProvider().get_instruments("stock") == []
```

```python
# From backend/tests/test_stocksdk_provider.py
def test_builtin_not_editable():
    from app.data_providers import custom as cs
    assert cs.get_config_dict("stocksdk") is None
    for fn in (lambda: cs.save_config("stocksdk", {}), lambda: cs.delete_config("stocksdk")):
        try:
            fn()
            raise AssertionError("expected ValueError for builtin")
        except ValueError:
            pass
```

**Data Validation Testing:**
```python
# From backend/tests/test_parquet_schema_compat.py
def test_partitioned_daily_scan_tolerates_added_quote_ts(tmp_path):
    # Creates two parquet partitions with different schemas, verifies scan merges them
    ...
    df = scan_daily_parquet(str(tmp_path / "kline_daily" / "**" / "*.parquet")).sort("date").collect()
    assert df.height == 2
    assert df.schema["volume"] == pl.Float64
    assert df.schema["quote_ts"] == pl.Int64
    assert df["quote_ts"].to_list() == [None, 1783560600000]
```

**Schema Validation Testing — `tmp_path` fixture:**
- Tests write temporary parquet files to `tmp_path` and verify reading/scanning logic is tolerant of schema drifts
- Used in `test_parquet_schema_compat.py` for backward compatibility tests

## Key Test Characteristics

| Property | Pattern |
|----------|---------|
| Test types | Pure unit tests; no E2E or dedicated integration tests |
| Fixtures | Module-level factory functions, no conftest.py |
| Mocking | `monkeypatch` only (no unittest.mock or pytest-mock) |
| Async | `asyncio.run()` inside sync test functions |
| Data | Polars DataFrames constructed inline |
| Assertions | Plain `assert` statements |
| Test isolation | `try/finally` for cleanup (not fixtures) |
| External deps | Node.js required for some bridge tests (skipped if absent via `shutil.which("node")`) |

---

*Testing analysis: 2026-07-10*
