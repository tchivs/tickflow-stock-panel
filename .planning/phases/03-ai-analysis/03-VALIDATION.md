---
phase: 03
slug: ai-analysis
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-07-11
---

# Phase 03 - Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | `pytest>=8.0` + `pytest-asyncio>=0.23`; Playwright `@playwright/test` 1.61.1 |
| **Config file** | `backend/pyproject.toml`; `frontend/playwright.config.ts` |
| **Quick run command** | `cd backend && uv run pytest tests/test_analysis_evidence.py tests/test_analysis_service.py -q` |
| **Full suite command** | `cd backend && uv run pytest -q && cd ../frontend && pnpm exec playwright test e2e/phase3-ai-analysis.spec.ts --project=desktop-chromium` |
| **Estimated runtime** | ~120 seconds |

---

## Sampling Rate

- **After every task commit:** Run targeted backend tests and `cd frontend && pnpm run build` after TypeScript changes.
- **After every plan wave:** Run the backend suite and the Phase 3 desktop Playwright scenario.
- **Before `/gsd-verify-work`:** Full suite must be green, including desktop and mobile evidence-first scenarios.
- **Max feedback latency:** 120 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 03-W0-01 | TBD | 0 | ANLY-01 | T-03-01 | Deterministic grades, source independence, period/unit normalization, and material-number conflicts remain visible. | unit | `cd backend && uv run pytest tests/test_analysis_evidence.py -q` | ❌ W0 | ⬜ pending |
| 03-W0-02 | TBD | 0 | ANLY-02 | T-03-02 | Fixed graph, strict generated body, citation whitelist, and valuation applicability fail closed. | unit | `cd backend && uv run pytest tests/test_analysis_graph.py tests/test_analysis_service.py -q` | ❌ W0 | ⬜ pending |
| 03-W0-03 | TBD | 0 | ANLY-03 | T-03-03 | Only authenticated human confirmation changes state; reviews and observations are append-only. | repository + API | `cd backend && uv run pytest tests/test_analysis_lifecycle.py tests/test_analysis_api.py -q` | ❌ W0 | ⬜ pending |
| 03-W0-04 | TBD | 0 | ANLY-01, ANLY-02, ANLY-03 | T-03-04 | Evidence warning, panels, lifecycle history, one-active-run behavior, keyboard and mobile states remain independently usable. | E2E | `cd frontend && pnpm exec playwright test e2e/phase3-ai-analysis.spec.ts --project=desktop-chromium` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠ flaky*

---

## Wave 0 Requirements

- [ ] `backend/tests/test_analysis_evidence.py` - source-grade, independence, normalization, and cross-check fixture matrix.
- [ ] `backend/tests/test_analysis_graph.py` - exact fixed topology and no-tool/no-loop guard.
- [ ] `backend/tests/test_analysis_service.py` - injected offline adapter, schema/citation failures, immutable versions, and one-active-run behavior.
- [ ] `backend/tests/test_analysis_lifecycle.py` and `backend/tests/test_analysis_api.py` - proposal, confirmation/rejection, and append-only outcomes.
- [ ] `frontend/e2e/phase3-ai-analysis.spec.ts` - UI contract coverage at 1440px, 1024px, and 375px.
- [ ] Human-verify `langgraph` and `langgraph-checkpoint-sqlite`, then lock and smoke-test the fixed SQLite-backed graph before domain implementation.

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Package legitimacy approval | ANLY-02 | Required human review of packages flagged `SUS`. | Verify official LangChain ownership, resolved versions, lockfile changes, and the startup graph/checkpointer smoke test before installation is accepted. |
| Domain evidence review | ANLY-01, ANLY-02 | Requires finance-domain judgment beyond structural automation. | Review fixtures for source authority, independence, accounting period, unit, and valuation applicability against the AI-SPEC rubric. |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 120s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
