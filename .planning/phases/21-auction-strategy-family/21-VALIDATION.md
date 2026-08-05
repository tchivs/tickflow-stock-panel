---
phase: 21
slug: auction-strategy-family
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-08-05
---

# Phase 21 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.
> Phase 21 = 竞价策略族 (STRAT-04..09): 引擎 seam + 受管列 `auction_volume_ratio` + 六策略 + 文档计数对账。两计划 Wave 1 并行、文件零重叠（21-01 = 引擎 seam + P1 三策略；21-02 = P2 三策略 + docs）。

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest >=8.0 (`--import-mode=importlib`, `asyncio_mode=auto`) |
| **Config file** | `backend/pyproject.toml` `[tool.pytest.ini_options]` |
| **Quick run command** | `.venv/bin/python -m pytest tests/test_auction_strategy_family.py -x` (21-01) / `tests/test_auction_strategy_family_p2.py -x` (21-02) |
| **Full suite command** | `.venv/bin/python -m pytest -x` (from `backend/`; sampling per wave) |
| **Estimated runtime** | ~60 seconds (targeted) / ~10 min (full) — 两测试文件均为 hermetic 单测，抽样 <90s |

---

## Sampling Rate

- **After every task commit:** Run `.venv/bin/python -m pytest tests/test_auction_strategy_family.py -x` (21-01) or `tests/test_auction_strategy_family_p2.py -x` (21-02)
- **After every plan wave:** Run `.venv/bin/python -m pytest tests/test_auction_strategy_family.py tests/test_auction_strategy_family_p2.py -x`
- **Regression gates (must stay green):** `.venv/bin/python -m pytest tests/test_auction_probe.py tests/test_auction_columns.py tests/test_auction_sync.py tests/test_auction_strategies.py -x`
- **Before `/gsd:verify-work`:** Full suite `.venv/bin/python -m pytest -x` must be green (incl. `test_pool_hub.py` POOL-03 guard regressions)
- **Max feedback latency:** < 90 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 21-01-01 | 01 | 1 | STRAT-04/05/06 (seam) | T-21-01 / T-21-03 | engine requires_auction_data short-circuit + minute single-point truncation + time_window validation | unit | `pytest tests/test_auction_strategy_family.py -x -q` | ❌ W0 | ⬜ pending |
| 21-01-02 | 01 | 1 | STRAT-04 (column) | T-21-04 | auction_volume_ratio prior-5d managed column; PIT-safe (excludes today EOD); registry discipline | unit | `pytest tests/test_auction_strategy_family.py -x -q` | ❌ W0 | ⬜ pending |
| 21-01-03 | 01 | 1 | STRAT-04/05/06 | T-21-02 / T-21-06 / T-21-07 | P1 三策略 fail-closed + branch exclusivity + scoring weights + golden_230 post_close label | unit | `pytest tests/test_auction_strategy_family.py -x -q` | ❌ W0 | ⬜ pending |
| 21-02-01 | 02 | 1 | STRAT-09 | T-21-01 / T-21-05 | intraday minute truncation + time_factor 240/elapsed (09:45→15→16.0); minute-absent empty pool | unit | `pytest tests/test_auction_strategy_family_p2.py -x -q` | ❌ W0 | ⬜ pending |
| 21-02-02 | 02 | 1 | STRAT-07/08 | T-21-04 / T-21-08 | allround whitelist + t1_flash no-lookahead (pool = T-day signals only) | unit | `pytest tests/test_auction_strategy_family_p2.py -x -q` | ❌ W0 | ⬜ pending |
| 21-02-03 | 02 | 1 | STRAT-03 沿续 | — | docs count reconciliation 21→27 / 18→27 + strategy-guide contract fields | doc/grep | `grep -c "27 个内置策略" docs/features.md docs/strategy.md` | ✅ existing | ⬜ pending |
| 21-R-01 | — | — | DATA-04/05/06 回归 | — | probe/columns/sync 既有竞价面不回归（engine.py setdefault 保持既有策略默认） | unit | `pytest tests/test_auction_probe.py tests/test_auction_columns.py tests/test_auction_sync.py tests/test_auction_strategies.py -x` | ✅ existing | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `backend/tests/test_auction_strategy_family.py` — engine seam (short-circuit / minute truncation / time_window validation) + auction_volume_ratio + P1 三策略 + STRAT-03 回归 (21-01, STRAT-04/05/06)
- [ ] `backend/tests/test_auction_strategy_family_p2.py` — P2 三策略 + 截断/time_factor 回归 (21-02, STRAT-07/08/09)
- [ ] Reuse `backend/tests/test_auction_strategies.py` `_governed_fixture`/`_engine`/`_run_auction` helpers + `test_auction_columns.py` `repo_env`/`_patch_probe`/`_write_auction_partition` (existing, extendable)

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| 策略卡片/API 透传 `time_window`/`evaluation_time`/`requires_auction_data` 的可视呈现 | STRAT-04..09 | UI rendering; e2e Playwright | Phase 23 owns the frontend surface; Phase 21 keeps backend DTO contract green (`list_strategies()` 透传新 META 字段由 test_no_third_registry 断言) |

*If none: "All phase behaviors have automated verification."*

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 90s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** {pending / approved YYYY-MM-DD}
