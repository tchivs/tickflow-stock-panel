---
phase: 20
slug: auction-data
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-08-05
---

# Phase 20 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest >=8.0 (`--import-mode=importlib`, `asyncio_mode=auto`) |
| **Config file** | `backend/pyproject.toml` `[tool.pytest.ini_options]` |
| **Quick run command** | `uv run pytest tests/test_auction_probe.py tests/test_auction_sync.py -x` |
| **Full suite command** | `uv run pytest -x` (from `backend/`; sampling per wave) |
| **Estimated runtime** | ~90 seconds (targeted) / ~10 min (full) |

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest tests/test_auction_sync.py tests/test_auction_columns.py -x`
- **After every plan wave:** Run `uv run pytest tests/test_auction_probe.py tests/test_auction_sync.py tests/test_auction_columns.py tests/test_minute_sync_verify.py -x`
- **Before `/gsd:verify-work`:** Full suite `uv run pytest -x` must be green (incl. `test_pool_hub.py` POOL-03 guard regressions)
- **Max feedback latency:** ~90 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 20-01-01 | 01 | 1 | DATA-05 | T-20-01 / — | lake write only real window rows; 09:30 structurally excluded | unit | `pytest tests/test_auction_sync.py::test_0930_excluded -x` | ❌ W0 | ⬜ pending |
| 20-01-02 | 01 | 1 | DATA-04 | T-20-02 / — | probe-gated column registry; non-available → absent | unit | `pytest tests/test_auction_columns.py -x` | ❌ W0 | ⬜ pending |
| 20-01-03 | 01 | 1 | DATA-06 | T-20-03 / — | unmatched proxy derived only with delegation input; else absent | unit | `pytest tests/test_auction_sync.py::test_unmatched_proxy -x` | ❌ W0 | ⬜ pending |
| 20-02-01 | 02 | 2 | DATA-03 | T-20-04 / — | probe×column matrix fail-closed (4 states) | unit | `pytest tests/test_auction_probe.py -x` | ✅ existing | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `backend/tests/test_auction_sync.py` — lake write/partition/atomicity/09:30 exclusion/unmatched proxy (DATA-05, DATA-06)
- [ ] `backend/tests/test_auction_columns.py` — enriched-column registry + probe×column matrix + unit normalization 手→股 (DATA-04)
- [ ] Reuse `backend/tests/test_auction_probe.py` `FakeAuctionProvider` pattern (existing, no new fixtures needed)

*If none: "Existing infrastructure covers all phase requirements."*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Data page 竞价列可用性 section 视觉呈现 | DATA-04 | UI rendering; e2e Playwright | Phase 23 owns the frontend surface; Phase 20 keeps backend DTO contract green |

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
