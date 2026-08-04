---
phase: 10-factor-library-multi-factor-model
plan: 10-04
subsystem: research
tags: [pit-universe, survivorship-bias, membership-fingerprint, signal-chain, manifest]
requires: [10-01, 10-02]
provides: [universe_resolution-manifest, per-date-membership-filter, membership-fingerprint]
affects: [10-05, 10-06, 11, 12, 13, 14]
tech-stack:
  added: []
  patterns:
    - "append-only membership events -> as-of resolution (qlib Instrument/UpdateMode contract)"
    - "per-date membership inner join AFTER the single governed load_panel (seam byte-identical)"
    - "sha256 membership fingerprint over the sorted per-date [symbol,date] frame"
key-files:
  created:
    - backend/app/research/universe.py
  modified:
    - backend/app/research/repository.py
    - backend/app/research/signal_chain.py
    - backend/tests/research/test_universe_resolution.py
    - backend/tests/research/test_signal_chain.py
    - backend/tests/research/test_factor_evaluation.py
decisions:
  - "membership_fingerprint = sha256 over the sorted per-date [symbol,date] frame (method factor_universe_membership/v1); config-symbols fallback hashes the sorted symbol tuple"
  - "resolve_universe_daily resolves over [start-warmup, end] so warmup bars participate in the universe"
  - "excluded_delisted = requested config symbols never members over the window"
  - "seed_membership is idempotent: UNIQUE collisions are treated as already-seeded"
  - "close_membership is an explicit delist-event appender; symbols_lagging never auto-delists (RESEARCH A4)"
metrics:
  duration: ~45m
  completed: 2026-08-01
status: complete
---

# Phase 10 Plan 4: PIT Universe Resolver + Manifest Summary

**One-liner:** Append-only `factor_universe_membership` resolved per evaluation date through `research/universe.py` (seed from `listing_date` with first-bar fallback, close by confirmed delist events), applied as a per-date inner join AFTER the single governed `BacktestEngine.load_panel`, and fingerprinted into every evaluation manifest — closing the survivorship-bias gap (144 listed-after-start instruments measured in RESEARCH) for Phases 11-13.

## What was built

### `research/universe.py` (new)
- `resolve_universe(repo, *, universe_name, as_of, asset_type="stock") -> (frozenset[str], str)` — latest event per symbol with `effective_date <= as_of` must be `listed`; returns symbols + `membership_fingerprint` (sha256 over sorted symbol tuple).
- `resolve_universe_daily(repo, *, universe_name, start, end, asset_type) -> pl.DataFrame[symbol, date]` — per-symbol `listed` intervals clipped to the window, dates exploded Polars-natively (`pl.date_range` per interval) without importing a market calendar; a `delisted` event closes the interval as-of (append-only, never an UPDATE).
- `seed_membership(repo, instruments, enriched, *, universe_name, source="instruments-sync")` — `effective_date = listing_date` (String `'YYYY-MM-DD'` cast normalization, Open Question 5) else first-bar date from the enriched lake; idempotent (UNIQUE collisions skipped); returns inserted count.
- `close_membership(...)` — appends a `delisted` row on confirmed delist; `symbols_lagging` (suspension heuristic) is deliberately NOT a delist trigger.
- `UniverseResolver(repo)` adapter exposing the module functions with the chain's injection-seam signature.

### `repository.py`
- `list_universe_memberships(*, universe_name, asset_type=None)` — ordered append-only event history needed for interval construction (reuses `insert_universe_membership` / `resolve_universe_memberships` landed by 10-02; no schema change).

### `signal_chain.py`
- `_resolve_membership` now resolves `resolve_universe_daily` over `[start-warmup, end]`; union symbol set passed to the single `load_panel`; per-date membership inner join applied AFTER the governed read (`load_panel` byte-identical).
- `FactorSignalFrame.resolved_universe` carries `{method: factor_universe_membership/v1, membership_fingerprint, per_date_symbol_counts {min,median,max}, excluded_delisted, pre_filter_counts}`.
- `membership_fingerprint` for the membership path is sha256 over the sorted per-date `[symbol,date]` frame (reproducible across runs); config-symbols fallback hashes the sorted symbol tuple.
- `excluded_delisted` = requested `config.symbols` never members over the window.

### `evaluation.py`
- No code change needed: `_manifest` already consumes `resolved_universe` (landed by 10-01); the production resolver now populates it with `factor_universe_membership/v1`, a 64-hex fingerprint, per-date counts, and excluded delists.

## Tests

| File | Result |
|------|--------|
| `tests/research/test_universe_resolution.py` (8) | green — listed-after-start excluded per date; delist closes membership as-of; fingerprint changes with membership; daily frame columns; delist closure in daily frame; seed listing_date + first-bar fallback + idempotency; deterministic fingerprint; close_membership append-only + no auto-delist |
| `tests/research/test_signal_chain.py` (8) | green — binding, per-date membership filter, cross-consumer equality, PanelCache dedup, live as-of, real-resolver per-date exclusion, fingerprint-change |
| `tests/research/test_factor_evaluation.py` (12) | green — evidence metrics, coverage pre-filter, manifest `universe_resolution` block (resolver + config-symbols fallback) |

**Per-plan gate:** `pytest tests/research/test_universe_resolution.py tests/research/test_signal_chain.py tests/research/test_factor_evaluation.py -q --tb=short` → **28 passed**.

**Regression:** full `tests/research` suite → **89 passed** (includes admission, models, catalog, pipeline).

## Commits

- `e15b019` feat(10-04): PIT universe resolver with seed/close rules
- `9dd55a0` test(10-04): turn universe resolution scaffold green
- `bd39531` refactor(10-04): wire real PIT resolver into signal chain
- `7f2edfa` test(10-04): real resolver integration + manifest fingerprint
- `7560d8d` style(10-04): drop obsolete noqa on resolved universe import

## Deviations from Plan

None - plan executed as written. Decisions within planner discretion:
- `membership_fingerprint` hashes the per-date frame (plan task 4: "sha256 of the per-date membership frame") rather than the symbol set for the membership path; the config-symbols fallback keeps the symbol-tuple hash.
- Added `close_membership` and `UniverseResolver` adapter as the explicit delist/seed and chain-injection surfaces (the plan references close rules and the injection seam; these are the concrete spellings).
- `resolve_universe_daily` expands `listed` intervals over calendar dates and relies on the `load_panel` inner join for actual trading dates — no market-calendar dependency, matching the plan's "no second datastore / load_panel unchanged" constraints.

## Success Criteria

- [x] Per-date universe membership resolved from the append-only table, applied after the single governed read.
- [x] `membership_fingerprint` recorded in every evaluation manifest with per-date counts and excluded delists.
- [x] `symbols_lagging` never auto-delists; pre-Phase-10 historical delists remain an Open Question (forward-fix only).

## Self-Check: PASSED
- `backend/app/research/universe.py` exists; `backend/app/research/repository.py`, `signal_chain.py`, and the three test files modified.
- Commits `e15b019`, `9dd55a0`, `bd39531`, `7f2edfa`, `7560d8d` present in `git log`.
- Per-plan gate 28/28 green; full research suite 89/89 green.
