---
phase: 39-deploy-verification
verified: 2026-08-07T12:30:00Z
status: passed
score: 4/4 DV requirements — DV-01/02/03/04 verified (real trading-day observations are deploy-gated, see behavior_unverified)
behavior_unverified: 3 — (1) 200-body verification of the 3 new endpoints (POST /api/kline/auction/backfill, GET /api/research/backtest/{run_id}, GET /api/research/auction/validation) is auth-gated (login cookie) and NOT observable in sandbox: only route registration (openapi 301 paths, 3/3 new routes) and the 401 gate on the two protected endpoints were proven, POST backfill never sent. (2) Real trading-day observations D1 (09:26 premarket cron + isolation), D2 (15:30 EOD + cache refresh + 15:35 pool persist), D4 (monitor payload/close + delivery incl. OQ-1 first real close semantics), D5 (15:40 recap + panel, LLM next-day enable), D7 (drift probe ≥5 consecutive trading days + weekly report) require a real trading day post-deploy — all scheduled in 39-03-OBSERVATION-WINDOW.md. (3) D3 tier-2 real auction columns + lake flow + BT-07 re-eval are gated on an external real-time auction source (auction_unmatched_volume + auction_virtual_price inputs; not configured → fail-closed pass state). Full-universe campaign (~2h quota window, ≤40 symbols/burst, rpm 30, full 5537 ≈ weeks, 36-02-SUMMARY:127-128) is an operator continuation, never a single-session sandbox deliverable.
overrides_applied: 0 — no REQUIREMENTS.md/ROADMAP.md text changed; DV-01..04 delivered as planned (W1-W4 warnings applied inside evidence files, not requirement text)
human_verification: 4 items (deploy-time 200-body for the 3 new endpoints, real trading-day D1/D2/D4/D5/D7 observations, D3 external source gate, full-universe quota campaign) — sandbox cannot assert; labeled deploy-verified per standing policy
---

# Phase 39 Verification — 部署验证与残留 (DV-01..04)

**Verifier:** VerifierP39 · **Date:** 2026-08-07 · **Scope:** `.planning/REQUIREMENTS.md` DV-01..04 (Phase 39) — D8 部署配方预检 (build + boot + endpoint/md5 parity), 部署验证清单 v2.4 实测刷新, P2 诚实缺口汇总, P2 部署后观测窗口日历.
**Method:** Behavior-level, evidence-file verification — re-read of RUN-EVIDENCE-39-01.md (T1–T6 rows with exact values), deploy-verification.md v2.4 section (+25/-0 diff), 39-03-GAPS.md (4 gaps × 4 fields), 39-03-OBSERVATION-WINDOW.md (8 rows + 5 constraints + template); live read-only re-checks (docker ps/exec/inspect, ss, curl, sentinels, git log/diff/status); cross-checks (a) stale-container md5 re-read via `docker exec` vs RUN-EVIDENCE stale column, (b) `grep -c '^## ' docs/deploy-verification.md` == 10. All claims re-derived by this verifier, not taken from SUMMARY text. **Real trading-day observations remain deploy-gated** — recorded honestly in `behavior_unverified`, never claimed.

## Verdict: **PASSED**

All four DV requirements verified: DV-01 evidence file complete and honest (build 66s exit 0 / boot 18s /health 200 v1.2.0 / 3 new routes + 401 gate / md5 parity 4/4 — stale 3018 re-read by this verifier, 4/4 byte-identical to the evidence table / zero-write sentinels + cleanup); DV-02 v2.4 section appended +25/-0 with ≥8 sourced measured facts, `## ` count 10, banner intact, HEAD 2453366 recorded; DV-03 GAPS.md 4 gaps × 4 fields with grep-verifiable anchors (15 anchors spot-checked by this verifier, all verbatim) and honest fail-closed pass states; DV-04 observation calendar 8 rows + 5 explicit sequencing constraints + fill-in template aligned with runbook. Zero code changes, zero new deps, Watchlist untouched, stale 3018 container untouched (running since 2026-08-04, Restarts=0, md5s still the stale set). The only unobservable acceptances (deploy-time 200-bodies, real trading-day observations, D3 external gate, full-universe campaign) are documented deploy-side items — no needs-fix in code or evidence.

---

## 1. Residue checks (executor duty 1 — re-run by this verifier, read-only)

| Check | Result |
|---|---|
| `docker ps -a --filter name=athenaquant-preflight` | **empty** — no preflight container residue |
| `docker ps` athenaquant lines | only stale `cb9800570dde` `athenaquant` Up 2 days `0.0.0.0:3018->3018/tcp` |
| `ss -tlnp` :3020 | **free** (no listener); `curl localhost:3020/health` fails (no listener) |
| `docker inspect athenaquant` | `Status=running StartedAt=2026-08-04T06:59:16Z Restarts=0` — untouched since preflight |
| `/tmp/preflight-data` | **removed** (does not exist) |
| Sentinels | `data/kline_auction` = 248, `data/*.tmp` = 0 — identical to pre-run values in RUN-EVIDENCE §Baseline/§Cleanup |
| `data/premarket_results` | absent (G1 live re-check, matches GAPS claim) |
| `data/kline_minute` | 0 entries (G3 live re-check, matches GAPS claim) |

Note (inert, not residue): image `athenaquant-app:preflight` `70bcda0bcc2c` remains in the local docker store — a build artifact with no running container, matching RUN-EVIDENCE (which claims container + temp-data + port cleanup, all confirmed; image deletion was never claimed).

## 2. DV-by-DV evidence (executor duty 2)

### DV-01 — D8 部署配方预检 (RUN-EVIDENCE-39-01.md) — **PASS**

- T1 baseline: HEAD `2453366` recorded (W1 honest — not stale 496cafb), docker 29.6.1, image `athenaquant-app:latest 263ceeaa06a8` created 2026-08-04; ports/containers facts; md5 baselines; data sentinels (248 / 0 .tmp); temp-copy permission deviation documented (sudo unavailable → throwaway root container with read-only source mount, 186M copy, auth.json/secrets.json present → is_configured True).
- T2 build: **66s, exit 0**, image `70bcda0bcc2c` (1.59GB), log tail recorded.
- T3 boot: **ready after 18s**, `/health` 200 `{"status":"ok","version":"1.2.0","mode":"free"}`, clean startup logs (warmup done, no exceptions).
- T4 endpoints: openapi **301 paths**, 3/3 new routes present (`/api/kline/auction/backfill` POST, `/api/research/backtest/{run_id}` GET, `/api/research/auction/validation` GET); protected endpoints return **401** (recorded as 401 — `{"detail":"未登录或会话已过期"}`, auth middleware gate) — no fabricated 200s; guest probes recorded verbatim: `pool_hub` 200, `auction/history` bare 422 (missing `symbol`) → unqualified 400 (`invalid symbol`) → qualified `000001.SZ` 200 guest-masked empty state (`available:false`, probe source "xyz", D5 masked); **POST backfill never sent** (route presence via openapi only).
- T5 md5 parity: 4/4 table (stale 3018 vs HEAD vs preflight) complete; preflight == HEAD, stale all DIFFER; planner anchor correction noted (`app/strategy/engine.py`, not `app/engine.py`).
- T6 zero-write + cleanup: pre-cleanup sentinels on temp copy (248 / 0 .tmp; auth.json mtime Aug 6 21:50 untouched); cleanup row (`docker rm -f athenaquant-preflight`, `rm -rf /tmp/preflight-data`, 3020 released, stale :3018 still Up, real-data sentinels 248/0 unchanged).
- Honesty: 5 deviations all documented (HEAD 2453366→99074f0 mid-run with content md5 re-verified identical, temp-copy method, guest probe 422/400/200 verbatim, build faster than estimate, W2 stale-name guard); verdict table MET with per-criterion evidence. Deploy-time 200-body explicitly not claimed.

### DV-02 — 部署验证清单 v2.4 实测刷新 — **PASS**

- Commit `99074f0`: `docs/deploy-verification.md` **+25/-0** (my `git show --stat`), only file touched.
- `### v2.4 实测事实 (2026-08-07)` at line 196; 7 bolded fact paragraphs carrying **≥8 discrete measured facts** (pilot latency mean 0.96s/median 0.82s/p95 1.24s n=20, 28 请求 0×429; 全量校准 3.5-5.5h; 配额 ~2h 窗 + ~70-100/窗 + 冷却 ~2h + burst ≤40 rpm 30 ~90s; 湖覆盖 40/5537 0.72% 10,904 行 248 分区; RC rerun `298d743e8083` 382,398 行 0.67% honest partial 8,951/1,373,176; API detail 0.052s / pushdown 0.015s; 容器 diff md5 4/4 表; 分钟接线状态 11 tests 全绿 + 0 分区 deploy-gated), each with source refs (AUCTION-FULL-BACKFILL.md §3.2 行 59-60/81-84/§3.4, 36-02-SUMMARY:127-129, 37-03-SUMMARY:42-50, RESEARCH.md §3.8, 38-03-SUMMARY §4).
- `grep -c '^## ' docs/deploy-verification.md` → **10** (cross-check b, my own run). `### v2.4` is a ### header, correctly outside the `## ` set; commit's header-drift gate `git show 99074f0 -- docs/ | grep -c '^[+-]## '` → **0** (my run).
- Banner blockquote lines 7-14 intact (Orchestrator 批准 2026-08-06 / Owner+来源纪律 / D3 条件项 / source DEPLOY-CHECKLIST.md).
- HEAD `2453366` recorded in the v2.4 blockquote; md5 table in v2.4 identical to 39-01 evidence (container diff 回退 clause present).

### DV-03 — P2 诚实缺口汇总 (39-03-GAPS.md) — **PASS**

- 4 gaps × 4 fields each (证据 file:line / Owner / 触发条件判定方法 / 诚实通过态): G1 premarket 双门禁 (部署 + live 09:15-09:25), G2 BJ 上游缺口 (333/5537, 上限 94.0%), G3 分钟 live-day gate (接线已落地, 点亮 deploy-gated, 非盘中 09:45), G4 AI-key 默认关 (preferences.py:441 默认关 + skip).
- Anchor spot-checks (this verifier, all **verbatim hits**): RESEARCH.md:15-16, AUCTION-FULL-BACKFILL.md:17/:57-58/:133/:176, tests/test_auction_backfill_honesty.py:262-266, preferences.py:441, daily_pipeline.py:778-781 + :966-968 (09:26 硬边界), secrets_store.py:72-75 (`get_ai_key`, file at `backend/app/secrets_store.py`), 38-03-SUMMARY.md:43, deploy-verification.md:34/:112/:170/:179.
- Pass states honest: `degraded:true` + probe 非 available 也是通过 (fail-closed), coverage ≤0.94 如实呈现绝不 claim 100%, 空湖 `total=0` 诚实通过态, 未启用无 action — 「不可用但如实标注不可用」= 通过, 「装作有数据」= BLOCKER.
- 非缺口项注记 correctly separated (湖覆盖 0.72% / RC rerun 8,951 partial = 进度态非缺陷, 判据 = 数字如实 + 台账 honest partial + 后续动作文档化).

### DV-04 — P2 部署后观测窗口日历 (39-03-OBSERVATION-WINDOW.md) — **PASS**

- 8 calendar rows: N D1 09:26 / N D4 (前置 D1) / N 15:30-15:40 D2+D6 / N 15:40 D5 (前置 D2) / N+1… D7 每日 / N+4 收盘后 D7 周终 / 竞价源接入后 D3 / 重建时 D8 — each with 时刻/项/前置/Owner/判据引用.
- 5 explicit sequencing constraints: ① D4 after D1 (同日上午), ② D5 after D2 (同日 15:40), ③ D7 周终 ≥5 连续交易日, ④ D3 条件触发 (独立, 未接入 = fail-closed), ⑤ D8 随重建动作 (复用 DV-01 配方).
- Date-fill template (部署日 N 回填) with 三态记录纪律 (通过/降级/BLOCKER); runbook alignment with deploy-verification.md:179 (1 D1 → 2 D4 → 3 D2+D6 → 4 D5 → 5 D7 每日 → 6 D7 周终 → 7 D3 → 8 D8) confirmed.

## 3. Guard rails (executor duty 3)

- **Zero code changes in phase-39 commits**: `git log --name-only` for `a0a285e` / `99074f0` / `ea14389` → only `.planning/phases/39-deploy-verification/` docs + `docs/deploy-verification.md`. (Prior commits 0b021a3/2453366 also .planning-only.)
- **Zero new deps**: `git diff 2453366^..ea14389 --stat -- pyproject.toml requirements.txt uv.lock` → empty (my run).
- **Watchlist untouched**: `git status --short` → staged 0, unstaged 1, untracked 0; sole entry `M frontend/src/pages/Watchlist.tsx` (pre-existing user change; never read by this verifier, per instruction).
- **Stale 3018 container untouched**: `docker inspect athenaquant` → `Status=running StartedAt=2026-08-04T06:59:16.79047509Z Restarts=0`; `docker exec athenaquant md5sum` returns the **stale** md5 set (4/4 DIFFER from HEAD) — the container was not rebuilt/restarted by any phase-39 action.

## 4. Cross-check claims (executor duty 4)

- **(a) md5 values in RUN-EVIDENCE vs live stale container** — this verifier re-ran `docker exec athenaquant sh -c 'md5sum …4 files'` → `641003ae8faab1c67201e9d2754da766` / `165b95a71850f71356766c0bb7fb974a` / `72e17c3c2592570a9ec563ab040b631c` / `23122ca0141152875091bdf83c152e46` — **4/4 byte-identical** to RUN-EVIDENCE §Baseline stale-3018 column and to the v2.4 md5 table. **PASS**
- **(b) `## ` count == 10** — `grep -c '^## ' docs/deploy-verification.md` → **10** (my run; D1-D8 = 8 + 时序总览 + 执行顺序总结 = 10). **PASS**
- Extra: 99074f0 diff +25/-0 and header drift 0 re-derived by this verifier; RUN-EVIDENCE T5 preflight md5s (`32468e15…`/`4e33c236…`/`1be3288b…`/`901d11a9…`) equal HEAD md5s from the same evidence file (self-consistent within file; container-side verification is what (a) covers for the stale side).

## 5. SUMMARY cross-checks

- All 3 phase-39 wave commits present and in order: `a0a285e` (39-01 RUN-EVIDENCE), `99074f0` (39-02 deploy-verification.md v2.4), `ea14389` (39-03 GAPS + OBSERVATION-WINDOW + SUMMARY) — surfaces match claims exactly; 39-03 writes only `.planning/phases/39-deploy-verification/`, 39-02 only `docs/deploy-verification.md` (no overlap).
- SUMMARY's DV-01..04 MET table claims match the on-disk artifacts this verifier re-read (build/boot/endpoint/md5 numbers, v2.4 facts, G1-G4 fields, 8-row calendar + 5 constraints).
- SUMMARY's "26/26 file:line 引用 grep 命中" → consistent with this verifier's 15-anchor spot-check, all verbatim hits; no miss found in the sampled set (RESEARCH.md:15/16, AUCTION-FULL-BACKFILL.md:17/57-58/133/176, tests:262, preferences.py:441, daily_pipeline.py:778-781/966-968, secrets_store.py:72-75, 38-03-SUMMARY.md:43, deploy-verification.md:34/112/170/179).

## 6. Honest boundary (behavior_unverified)

**What is verified**: the entire sandbox-executable DV-01 preflight recipe end-to-end (build 66s exit 0 on HEAD, boot 18s /health 200 v1.2.0 on :3020 with temp data, 3/3 new endpoint routes in openapi 301 paths, 401 auth gate on protected endpoints, POST backfill never sent, md5 parity 4/4 preflight==HEAD ∧ stale-3018 all DIFFER — stale values re-read live by this verifier, zero-write sentinels 248/0 unchanged, full cleanup with zero residue); DV-02 v2.4 facts + `## ` set + banner + HEAD record; DV-03 gap matrix with verified anchors and honest pass states; DV-04 observation calendar with explicit sequencing.

**What is NOT verified (behavior_unverified)**: (1) 200-body responses of the 3 new endpoints — auth-gated (login cookie); sandbox proves route registration + 401 gate only. (2) Real trading-day observations D1/D2/D4/D5/D7 — a live trading day's 09:26 premarket cron, 15:30 EOD + 15:35 pool persist, 15:40 recap, monitor payload close semantics, and ≥5 consecutive drift-probe days cannot be produced in sandbox; all are scheduled in 39-03-OBSERVATION-WINDOW.md (operator's calendar). (3) D3 tier-2 real auction columns + lake flow + BT-07 re-eval — gated on an external real-time auction source (not configured → fail-closed pass state, per D3). The phase's committed acceptance is the honest preflight recipe + checklist refresh + gap/observation planning — delivered; runtime confirmations are operator observations, not sandbox artifacts.

## 7. Human items (deploy-verified — not assertable in sandbox)

1. **Deploy-time 200-body verification of the 3 new endpoints**: after rebuild + login (cookie), operator confirms POST /api/kline/auction/backfill, GET /api/research/backtest/{run_id}, GET /api/research/auction/validation return 200 with valid bodies; sandbox evidence is limited to openapi route presence + 401 gate (RUN-EVIDENCE-39-01.md §Endpoint smoke). Never claim 200 in sandbox.
2. **Real trading-day observations D1/D2/D4/D5/D7**: D1 09:26 premarket cron + 落盘隔离 (判据 1-4, deploy-verification.md:34), D2 15:30 EOD + 缓存刷新 + 15:35 股池持久化 (:52), D4 监控 payload/close + 投递 incl. OQ-1 首次真实 close 语义 (:92), D5 15:40 复盘 + 面板 (LLM 次日启用, :112), D7 drift 探针 ≥5 连续交易日 + 周终报告 (:152) — schedule per 39-03-OBSERVATION-WINDOW.md; pass = 通过/降级 (fail-closed)/BLOCKER (装作有数据) 三态, BLOCKER → 立即报回开发.
3. **D3 external source gate**: 外部实时竞价源 (auction_unmatched_volume + auction_virtual_price) 接入前 D3 为 fail-closed 通过态 (probe 非 available → 全链路诚实降级, 系统不报错); 接入后 operator 做 tier-2 真列 + 湖流 + BT-07 复评 (判据 1-5, deploy-verification.md:70).
4. **Full-universe campaign (quota)**: 全量 5537 受上游 ~2h 滚动窗 + 窗口累计 ~70-100 + 冷却 ~2h 配额纪律约束; operator 分块突发 (≤40 symbols, rpm 30, ~90s) + `--only-missing` 续跑, 完成判据 = 湖终态 verify PASS (36-02-SUMMARY:127-129), 不假设单会话完成; 台账/报告 honest partial 口径不变.

## 8. Honesty notes

- All PASS evidence is directly re-observed by this verifier: my own docker ps/exec/inspect/ss/curl runs, my own git log/diff/status/dep-diff runs, my own `grep -c '^## '`, my own reads of RUN-EVIDENCE / v2.4 section / GAPS / OBSERVATION-WINDOW / SUMMARY, my own 15-anchor spot-checks.
- The "8 facts" claim in the DV-02 commit message is satisfied as a floor: the v2.4 section holds 7 bolded paragraphs carrying ≥8 (10+) discrete measured values, all source-referenced. No fabricated or inflated count.
- `secrets_store.py` lives at `backend/app/secrets_store.py` (GAPS cites `secrets_store.py:72-75` — file name correct, path resolved by this verifier; lines 72-75 hold `get_ai_key` exactly as quoted).
- The preflight image `70bcda0bcc2c` remains in the local docker store (inert build artifact, no container) — consistent with RUN-EVIDENCE cleanup claims (container + temp data + port); noted so residue checks stay honest.
- 200-body endpoint verification, real trading-day observations, D3 gate, and full-universe campaign are deliberately **not** marked verified; the phase passes on preflight evidence + checklist refresh + gap/observation planning with deploy-side items recorded — matching the standing honesty policy (never present incomplete work as delivered).
