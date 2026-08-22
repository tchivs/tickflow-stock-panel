---
phase: 55
slug: websocket
# status lifecycle: draft (seeded by plan-phase) → validated (set by validate-phase §6)
# audit-milestone §5.5 distinguishes NOT-VALIDATED (draft) from PARTIAL (validated + nyquist_compliant: false) (#2117)
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-08-21
---

# Phase 55 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest (backend) / vitest 3.2.7 (frontend) / Playwright (e2e) |
| **Config file** | backend/pytest.ini, frontend/vitest.config.ts, e2e/playwright.config.ts |
| **Quick run command** | `cd backend && python -m pytest tests/ -x -q` |
| **Full suite command** | `cd backend && python -m pytest tests/ -q && cd ../frontend && npx vitest run && cd ../e2e && npx playwright test` |
| **Estimated runtime** | ~60 seconds (backend unit), ~30s (frontend unit), ~3min (e2e) |

---

## Sampling Rate

- **After every task commit:** Run `cd backend && python -m pytest tests/ -x -q`
- **After every plan wave:** Run full suite
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 60 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 55-01-01 | 01 | 1 | WS-01 | T-55-01 | Cookie session auth on WS handshake | unit | `pytest tests/test_ws_endpoint.py -k auth` | ❌ W0 | ⬜ pending |
| 55-01-02 | 01 | 1 | WS-01 | T-55-01 | Connection lifecycle audit (scope=ws) | unit | `pytest tests/test_ws_endpoint.py -k audit` | ❌ W0 | ⬜ pending |
| 55-02-01 | 02 | 2 | WS-02 | — | Seq ring buffer resume after reconnect | unit | `pytest tests/test_ws_stream.py -k resume` | ❌ W0 | ⬜ pending |
| 55-02-02 | 02 | 2 | WS-02 | — | SSE stream migration (walkforward/optimizer/mining/quote) | e2e | `npx playwright test websocket.spec.ts` | ❌ W0 | ⬜ pending |
| 55-03-01 | 03 | 2 | WS-03 | — | Multi-channel multiplexing on single connection | unit | `pytest tests/test_ws_stream.py -k multiplex` | ❌ W0 | ⬜ pending |
| 55-04-01 | 04 | 3 | WS-04 | — | Client exponential backoff reconnect | unit | `npx vitest run useWsStream.reconnect` | ❌ W0 | ⬜ pending |
| 55-04-02 | 04 | 3 | WS-04 | — | Connection status visible to user | e2e | `npx playwright test connection-status.spec.ts` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `backend/tests/test_ws_endpoint.py` — stubs for WS-01 (endpoint, auth, audit)
- [ ] `backend/tests/test_ws_stream.py` — stubs for WS-02/WS-03 (seq resume, multiplex)
- [ ] `frontend/src/lib/useWsStream.test.ts` — stubs for WS-04 (reconnect, status)
- [ ] `e2e/tests/websocket.spec.ts` — stubs for e2e WS stream migration
- [ ] Existing vitest + pytest infrastructure covers framework needs

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Connection status UI visible | WS-04 | Visual rendering check | Open browser, verify connected/reconnecting/disconnected indicator |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 60s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
