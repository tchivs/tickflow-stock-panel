---
phase: 02-factor-and-strategy-research
plan: 04
subsystem: research-api-and-hypothesis-workflow
status: complete
commits:
  - 987fb10
  - 8f16e0f
  - 442b21f
---

# Phase 02 Plan 04 Summary

Implemented the existing-host research workflow without granting natural-language providers persistence or execution authority.

## Delivered

- Proposal-only factor hypothesis service with strict provider JSON validation, DSL revalidation, deterministic offline gateway, provider/model/template/timestamp provenance, and transient issued-draft verification.
- Typed `/api/research` routes for DSL validation/options, manual immutable factor revisions, similarity discovery, hypothesis drafting/reviewed promotion, validated factor evaluation, experiment history/detail, explicit retention, candidates, and side-by-side comparison.
- Reviewed drafts require the issued draft ID, exact canonical expression/explanation/provenance, and `reviewed: true`; promotion embeds model provenance in the immutable revision.
- Factor evaluation reuses the existing backtest range/symbol guard and records completed evidence snapshots as unretained until an explicit retain action.
- Existing `/api/backtest/strategy/run` and strategy SSE now allocate a server execution handle, capture only server-generated registered-strategy results and immutable artifact checksums, and expose strategy retention solely through the handle. Failed and cancelled results remain non-comparable.
- Research catalog history is available through its domain interface; comparison remains completed-and-retained-only and exposes compatibility warnings without selecting a winner.

## Verification

Ran offline from `backend/`:

```text
uv run --extra dev pytest tests/research/test_research_api.py tests/research/test_hypothesis_workflow.py tests/research/test_strategy_experiment_handoff.py -q
8 passed, 2 warnings in 1.75s
```

The two warnings are existing Polars `DataFrame.pivot(columns=...)` deprecation warnings from `app/backtest/factor.py`; they do not affect the tested contracts.

## Deviations

None.
