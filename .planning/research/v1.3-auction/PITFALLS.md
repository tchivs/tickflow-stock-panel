# v1.3 Auction Pitfalls

## Data-Source Pitfalls

1. **No 集合竞价 match data.** Minute-K bars start 09:30 (`_minute_ts` start-of-day anchor `093000`; `_bucket_minutes` morning session = 09:30+). The 9:15–9:25 auction match (竞价量/金额/虚拟成交) is absent. **Prevention:** Phase 1 probe; if absent, scope to derived open-gap factors and mark true-auction columns future. Never label the 09:30 bar "竞价量".
2. **Free source stability.** Free stockdb and reverse endpoints are hobby-grade; 9:15–9:25 is a narrow window. **Prevention:** capability gate + fail-closed skip (existing `skipped_stages` pattern); data-quality annotations rather than fabricated values.
3. **Minute sync cost.** Minute K over full universe is heavy; `sync_and_persist_minute` currently resolves the full CN universe. **Prevention:** limit minute sync to the auction strategy's pool/spot set; keep daily-K-derived factors primary.

## Strategy-Design Pitfalls

4. **Reference names ≠ factor definitions.** 竞价多头/陈星量化/早盘之星 are product labels with no public spec. Copying the name while inventing different factors is misleading. **Prevention:** author first-principles strategies with honest names/descriptions; do not claim parity with a proprietary recipe.
5. **Third strategy track.** `PRESET_STRATEGIES` (screener.py) and `strategy/builtin/*.py` already coexist; adding auction strategies as yet another registry creates drift. **Prevention:** land new strategies in `strategy/builtin/` only; handle preset dedup in the strategies API.
6. **Open-gap lookahead.** `open vs prev_close` must use the same day's open and prior day's close — easy to cross days accidentally in Polars joins. **Prevention:** unit-test the factor contract on a known fixture.
7. **Scoring weight sum.** Engine normalizes scoring weights to 1.0; auction strategies with many factors must keep weights sum-stable or scores become arbitrary. **Prevention:** follow existing builtin strategy pattern (`strong_open.py`).

## Product Pitfalls

8. **Guest masking must be server-authoritative.** Client-side masking is bypassable. **Prevention:** apply 脱敏 at the API DTO boundary based on session/VIP state, never in the frontend.
9. **Docs drift.** `docs/features.md` says 20 builtin strategies, source has 18. Adding more without reconciling worsens it. **Prevention:** reconcile docs in the same milestone.
10. **Pool counts vs results mismatch.** A strategy card shows 股池 N but clicking shows a different count if results are cached per-date (as_of drift). **Prevention:** single as_of source of truth (existing `strategy_cache`), no client-side recompute.

## Which Phase Should Address It

- 1–3 → Phase 1 (data layer)
- 4–7 → Phase 2 (strategy family)
- 8 → Phase 4 (frontend/guest)
- 9–10 → Phase 5 (docs/verification)
