# Phase 19: 游客/VIP 脱敏 + 前端 (Guest Access & Frontend) - Context

**Gathered:** 2026-08-04
**Status:** Ready for planning
**Mode:** Auto-generated (autonomous smart discuss — user requested automated GSD flow)

<domain>
## Phase Boundary

**Goal**: Guests see only 涨跌幅 and 概念板块 with stock code/name masked server-authoritatively; VIP sessions see明文; the frontend pool page composes cards, lists, filtering, and resonance into one workspace.

**Depends on**: Phase 18 (pool hub API + PoolHubPage)

**Success Criteria** (must be TRUE):
1. Guest session responses mask stock code/name (`******`) at the API DTO boundary and expose only 涨跌幅/概念板块; VIP responses are明文. No client-side masking is trusted.
2. Masking is display-only — underlying factor computation and strategy results remain unmasked and correct for all sessions.

</domain>

<decisions>
## Implementation Decisions

### Claude's Discretion — Authorized Constraints

1. **Server-authoritative masking (GUEST-01).** Masking is applied at the API DTO boundary based on session/VIP state — NEVER in the frontend. The pool-hub API (and any strategy-result API that returns stock code/name) masks `code`/`name`/`symbol` fields for guest sessions. (PITFALL #8)
2. **Display-only, engine-correct (GUEST-02).** Masking never touches the strategy engine's factor computation or persisted strategy results. Only the serialized response shape for guest sessions is masked. Internal correctness unchanged.
3. **VIP = authenticated non-guest session.** Session state determines masking. Existing auth/identity layer (`session`/token) drives it.
4. **Masked format:** stock code/name → `******` (6 asterisks). 涨跌幅/概念板块 remain visible. 关联因子 (strategy names) remain visible (they are strategy labels, not PII). 开盘涨幅 — ROADMAP says guests see only 涨跌幅 and 概念板块; open_gap is derived from the same data class as change_pct but the success criterion explicitly lists only 涨跌幅+概念板块 visible. Decide: mask 开盘涨幅 for guests too (conservative) OR keep it (it's an anonymous market factor). Follow the ROADMAP letter: guests see ONLY 涨跌幅 and 概念板块.
5. **Frontend pool page** (Phase 18 PoolHubPage) renders whatever the API returns — guest sessions simply receive masked rows, so no client masking code exists anywhere.
6. **No new datastore.** Masking is a serialization transform at the API boundary; no schema change, no persisted masked copy.

</decisions>

<code_context>
## Existing Code Insights

- `backend/app/api/pool.py` — Phase 18 GET /api/pool/hub (the DTO that must mask for guests).
- `backend/app/services/pool_hub.py` — build_pool_hub projection (unchanged; masking happens at the API layer).
- Auth/identity: `backend/app/api/auth.py` (setup_password/verify_and_create_session), session token mechanism.
- `frontend/src/pages/PoolHubPage.tsx` — Phase 18 frontend; renders rows from the API (no client masking).
- Phase 18 test conventions: `backend/tests/test_pool_hub.py`, `frontend/e2e/pool-hub.spec.ts`.

</code_context>

<specifics>
## Specific Ideas

- Backend: a small masking helper at the API DTO boundary (`mask_guest_row` / DTO serializer) applied in `pool.py` when the request session is non-VIP. Guest: code/name/symbol → `******`, only 涨跌幅/概念板块 (+ 关联因子?) exposed; VIP: unchanged 明文.
- Tests: guest session response masks code/name, keeps change_pct/concept; VIP response 明文; engine results internally unmasked; no client masking code in frontend (grep guard).
- Frontend: verify PoolHubPage renders masked rows exactly as the API returns (no client re-derivation); e2e for guest session showing `******`.

</specifics>

<deferred>
## Deferred Ideas

- 日期导航 (per-day historical pool browsing) → POOL-04 (v2)
- True auction match data columns → DATA-04 (v2)
- Additional auction strategies → STRAT-04/05 (v2)
</deferred>
