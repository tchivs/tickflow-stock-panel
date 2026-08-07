---
phase: 43-tday-auction-sidecar
plan: 01
subsystem: database
tags: [stockdb, ticks, staging, parquet, fetch-on-miss, auction, reconciliation]

# Dependency graph
requires: []
provides:
  - StockDBProvider.get_ticks (GET /v1/ticks/{sym}?date=YYYYMMDD, 60/min 对齐, typed 异常, 请求必带 date=T)
  - auction_capture: capture_auction_window + _validate_tick_window + resolve_sidecar_pool + _write_staging_partition + _write_manifest
  - data/tick_staging/date={T}/part.parquet 10 列契约 + manifest.json (completeness/reconciliation 键集)
  - auction_reconcile: reconcile_match + reconcile_window (三重对账, end=T+1, 重试 pending)
  - preferences auction_sidecar_symbols 白名单键
  - canned 夹具 tests/fixtures/ticks/sh600519_20260807_window.json (冻结 2026-08-07 live 实测体)
affects: [43-02 promote (读 staging + manifest gate), 43-03 sidecar 调度/告警, verify-work UAT]

# Actuals (#2632) — pairs with the plan's `estimate` to calibrate future estimates.
# Same estimateTokens scale (chars/4 over the realized diff), never a harness token count.
actuals:
  tokens: 33109
  tasks: 3
  commits: 3

# Tech tracking
tech-stack:
  added: []
  patterns:
    - fetch-on-miss 单次 GET 全窗口采集 (绝无盘中轮询)
    - staging 独立湖 + manifest 键集 + temp+os.replace 原子写 + _DATE_RE 路径守卫
    - 三重完整性校验 fail-closed (归属日==T ∧ 09:25:00 num_trades>0 ∧ 窗口 ≥40)
    - 采集池 pool-gated (白名单≤200 默认自选池, 归一失败诚实)
    - 三重对账 (price 1e-6 / vol 恒等 / amount 仅 OHLC 全等派生) + end=T+1 端日语义

key-files:
  created:
    - backend/app/services/auction_capture.py
    - backend/app/services/auction_reconcile.py
    - backend/tests/test_auction_capture.py
    - backend/tests/test_auction_reconcile.py
    - backend/tests/fixtures/ticks/sh600519_20260807_window.json
  modified:
    - backend/app/data_providers/stockdb_provider.py (get_ticks)
    - backend/app/services/preferences.py (auction_sidecar_symbols 键)
    - backend/tests/test_stockdb_provider.py (get_ticks 契约测试)

key-decisions:
  - "get_ticks 返回原始 TickBar list 零归一化 — 归一化单点收敛到 capture 层 (staging 契约唯一转换点)"
  - "manifest.completeness = {ok: bool, by_symbol: {...}} 双形 — 43-02 gate 读 ok, 43-03 告警读 per-symbol"
  - "manifest pool_size = 池总数 (含归一失败/截断前原始条目数), truncated 布尔单独标记"
  - "reconcile 对账字段用 provider.get_minute canonical 列名 (close/volume 元/手), 非 RESEARCH 骨架 volume_hand"
  - "reconcile_window 顶层 status 聚合 (closed/mismatch/pending/staging_missing) + per-symbol checks; pending 带顶层 reason='no_0930_bar'"
  - "tick 档位 60/min 用独立 _TICKS_RPM 分桶, 与 daily/minute 120/min 共享限速器分离"

patterns-established:
  - "采集驱动镜像面: 09:26 单次 GET 触发 fetch-on-miss 全窗口; 完整性校验 fail-closed; staging 独立湖 10 列 + manifest"
  - "三重对账镜像面: 两条独立端点互证; amount 仅 OHLC 全等派生 (22,639,818 闭合); 缺失重试 1 次后 pending"
  - "夹具扩展面: 冻结 live 实测体 canned JSON; _FakeTickProvider/_RecordingMinuteFetch 注入; 全部零网络 hermetic"

requirements-completed: [SDC-01]

coverage:
  - id: D1
    description: "StockDBProvider.get_ticks — GET /v1/ticks/{sym}?date=YYYYMMDD 原始 TickBar list; 请求必带 date=T (Pitfall 3); typed 异常; 60/min 对齐"
    requirement: SDC-01
    verification:
      - kind: unit
        ref: "backend/tests/test_stockdb_provider.py#test_get_ticks_requests_date_and_returns_raw_list"
        status: pass
      - kind: unit
        ref: "backend/tests/test_stockdb_provider.py#test_get_ticks_accepts_suffix_input"
        status: pass
    human_judgment: false
  - id: D2
    description: "capture_auction_window 端到端 — tick_staging/date={T}/part.parquet 10 列 TickBar 全保留 + manifest.json (trade_date/captured_at/pool_size/symbols_ok/symbols_failed/completeness)"
    requirement: SDC-01
    verification:
      - kind: unit
        ref: "backend/tests/test_auction_capture.py#test_capture_single_symbol_writes_staging"
        status: pass
    human_judgment: false
  - id: D3
    description: "完整性 fail-closed 三拒 — 昨日归属日 / 缺 09:25 撮合行 / 窗口 <40 行 → 不落分区; 全失败无分区不 mkdir"
    requirement: SDC-01
    verification:
      - kind: unit
        ref: "backend/tests/test_auction_capture.py#test_validate_window_rejects_wrong_trade_date"
        status: pass
      - kind: unit
        ref: "backend/tests/test_auction_capture.py#test_validate_window_rejects_missing_match_row"
        status: pass
      - kind: unit
        ref: "backend/tests/test_auction_capture.py#test_validate_window_rejects_short_window"
        status: pass
      - kind: unit
        ref: "backend/tests/test_auction_capture.py#test_capture_all_failed_no_partition"
        status: pass
    human_judgment: false
  - id: D4
    description: "采集池解析 (A2) — 白名单 auction_sidecar_symbols 优先默认 watchlist 自选池; ≤200 硬 cap + 截断注记; 归一失败进 failed (unparsable_symbol); 部分失败 ok/failed 计数 + manifest symbols_failed"
    requirement: SDC-01
    verification:
      - kind: unit
        ref: "backend/tests/test_auction_capture.py#test_resolve_pool_whitelist_wins"
        status: pass
      - kind: unit
        ref: "backend/tests/test_auction_capture.py#test_resolve_pool_default_watchlist"
        status: pass
      - kind: unit
        ref: "backend/tests/test_auction_capture.py#test_resolve_pool_caps_at_200"
        status: pass
      - kind: unit
        ref: "backend/tests/test_auction_capture.py#test_capture_partial_failure_semantics"
        status: pass
    human_judgment: false
  - id: D5
    description: "三重对账闭合 — 09:25 撮合行 vs /v1/minute 09:30 bar: price 1e-6 / vol 恒等 / amount 仅 OHLC 全等派生 (173×100×1308.66=22,639,818); mismatch/pending 语义; end=T+1 端日语义; 09:30 bar 缺失重试 1 次后 pending; manifest.reconciliation 原子更新"
    requirement: SDC-01
    verification:
      - kind: unit
        ref: "backend/tests/test_auction_reconcile.py#test_reconcile_closed_anchor"
        status: pass
      - kind: unit
        ref: "backend/tests/test_auction_reconcile.py#test_reconcile_amount_unknown_non_closed_ohlc"
        status: pass
      - kind: unit
        ref: "backend/tests/test_auction_reconcile.py#test_reconcile_window_uses_minute_end_plus_1"
        status: pass
      - kind: unit
        ref: "backend/tests/test_auction_reconcile.py#test_reconcile_window_retry_then_pending"
        status: pass
      - kind: unit
        ref: "backend/tests/test_auction_reconcile.py#test_reconcile_window_manifest_preserves_old_keys"
        status: pass
    human_judgment: false

# Metrics
duration: 24min
completed: 2026-08-07
status: complete
---

# Phase 43: T-day 竞价采集 sidecar — Wave 1 (43-01) Summary

**盘中竞价窗口 live 采集: StockDBProvider.get_ticks (fetch-on-miss 单次 GET) + auction_capture 采集驱动 (三重完整性校验 fail-closed → tick_staging 10 列原子写 + manifest) + 池解析 (白名单≤200 默认自选池) + auction_reconcile 三重对账 (22,639,818 闭合)**

## Performance

- **Duration:** 24 min
- **Started:** 2026-08-07T01:52:00Z (approx)
- **Completed:** 2026-08-07T02:16:00Z (approx)
- **Tasks:** 3
- **Files modified:** 8 (3 commits)

## Accomplishments
- `get_ticks` 扩展: GET /v1/ticks/{symbol}?date=YYYYMMDD (请求必带 date=T 防昨日回退, Pitfall 3), 原始 TickBar list 透传零归一化, 60/min 独立档位对齐, typed 异常走 `_get_json` 唯一请求面
- `capture_auction_window` 端到端: 逐 symbol GET → `_validate_tick_window` 三重门 (归属日==T ∧ 09:25:00 num_trades>0 ∧ 窗口 ≥40) → 归一化 10 列 (trade_date aware Asia/Shanghai / fetched_at·ingested_at UTC) → temp+os.replace 原子写 `tick_staging/date={T}/part.parquet` + manifest.json; 全失败无分区不 mkdir (fail-closed)
- `resolve_sidecar_pool` (A2): preferences `auction_sidecar_symbols` 白名单优先 → watchlist 自选池缺省; 硬 cap 200 + 截断注记; suffix→prefix 归一失败进 failed (unparsable_symbol 不猜)
- `auction_reconcile`: `reconcile_match` 三重闭合 (price 1e-6 / vol 恒等 / amount 仅 OHLC 全等派生, 实测锚定 173×100×1308.66=22,639,818) + `reconcile_window` (end=T+1 端日语义, 09:30 bar 缺失 300s 重试 1 次 → pending, manifest.reconciliation 原子更新, trading_day_confirmed 数据在场判定)
- 夹具冻结 2026-08-07 live 实测体 (87 行窗口: 84 快照 + 09:25:00 撮合 + 09:25:01 回显 + 09:25:04 重复撮合 + 3 畸形子集); 全部测试 canned 零网络

## Task Commits

Each task was committed atomically:

1. **Task 1: 采集契约 (RED)** - `e652734` (test: 夹具冻结 + 端到端 staging + 三重完整性门, 红: ImportError)
2. **Task 1+2: get_ticks + 采集驱动 + 池解析 (GREEN)** - `e6adde7` (feat: get_ticks + capture_auction_window + staging 原子写 + manifest + 采集池解析)
3. **Task 3: 三重对账** - `5bd1da5` (feat: 三重对账 — 09:25 撮合行 vs 09:30 bar 闭合 22,639,818 / mismatch / pending)

## Files Created/Modified
- `backend/app/data_providers/stockdb_provider.py` - 新增 `get_ticks(symbol, trade_date)` + `_TICKS_RPM=60` 档位常量
- `backend/app/services/auction_capture.py` - 采集驱动: `_validate_tick_window` / `resolve_sidecar_pool` / `capture_auction_window` / `_normalize_rows` / `_write_staging_partition` / `_write_manifest`
- `backend/app/services/auction_reconcile.py` - 三重对账: `reconcile_match` / `reconcile_window` / `_fetch_0930_bar` / `_update_manifest_reconciliation`
- `backend/app/services/preferences.py` - 新增 `get/set_auction_sidecar_symbols` (镜像 auction_sync_symbols 形态)
- `backend/tests/fixtures/ticks/sh600519_20260807_window.json` - 冻结 2026-08-07 live 实测体 + 3 畸形子集
- `backend/tests/test_auction_capture.py` - 12 契约测试 (staging/manifest/三拒/池/失败语义)
- `backend/tests/test_auction_reconcile.py` - 10 契约测试 (闭合/mismatch/UNKNOWN/end+1/重试 pending/原子更新)
- `backend/tests/test_stockdb_provider.py` - 2 新增 get_ticks 契约测试

## Decisions Made
- **get_ticks 零归一化**: 返回原始 TickBar list, 归一化单点收敛到 capture 层 (staging 契约唯一转换点, provider 不重复实现)
- **manifest.completeness 双形** `{ok: bool, by_symbol: {...}}`: 43-02 gate 读 `completeness.ok`, 43-03 告警可读 per-symbol (与 ExecP4302/ExecP4303 对齐确认)
- **manifest pool_size = 池总数** (配置/自选原始条目数, 含归一失败与截断前), truncated 布尔单独标记 — 截断事实由调用方 job 进台账
- **对账字段用 canonical 列名** (close/volume 元/手) 而非 RESEARCH 骨架的 volume_hand — Phase 40 契约 volume 恒等 ×1
- **reconcile_window 聚合语义**: 顶层 status ∈ {closed, mismatch, pending, staging_missing}; per-symbol checks 保留 reconcile_match 结果或 pending 标记; pending 带顶层 reason='no_0930_bar'
- **tick 60/min 独立分桶** (`_TICKS_RPM`): 与 daily/minute 120/min 共享限速器分桶, 偏保守绝不超速

## Deviations from Plan

### Auto-fixed Issues

**1. [Test data] reconcile OHLC 不全等用例 close 值错误**
- **Found during:** Task 3 (三重对账测试)
- **Issue:** `test_reconcile_amount_unknown_non_closed_ohlc` 初版 bar close=1308.60 而 match price=1308.66 → price_eq 先于 amount 语义失败, 用例无法锁定「OHLC 不全等但 price/vol 全等」的 UNKNOWN 语义
- **Fix:** close 改为 1308.66 (与 price 全等), 仅 high/low 偏离 → amount_reason='ohlc_not_closed' + status='mismatch' 断言成立
- **Files modified:** backend/tests/test_auction_reconcile.py
- **Verification:** `pytest tests/test_auction_reconcile.py -q` 10 passed
- **Committed in:** 5bd1da5 (Task 3 commit)

**2. [Fixture] 快照行数 83 → 84 (末行 09:24:28 而非 09:24:58)**
- **Found during:** Task 1 (夹具生成)
- **Issue:** gap 循环先 append 后 advance → 83 行, 末行 09:24:28, 与 RESEARCH 实测「09:24:58 前全 num_trades=0」不符
- **Fix:** 循环后补 append 末行 → 84 快照行 @ 09:24:58, 窗口 87 行 (85 窗口 + 回显 + 重复撮合)
- **Files modified:** backend/tests/fixtures/ticks/sh600519_20260807_window.json
- **Verification:** 夹具断言 + 全部采集测试绿
- **Committed in:** e652734 (Task 1 commit)

---

**Total deviations:** 2 auto-fixed (2 test-data/fixture correctness)
**Impact on plan:** 全部为测试夹具/用例数据修正, 生产代码与计划逐字一致。无 scope creep。

## Issues Encountered
- 无 — 实现按计划落地, 唯一波折为上述两处测试数据修正 (计划内 auto-fix 范畴)

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- **43-02 (promote) 输入就绪**: staging 10 列契约 + manifest.completeness.ok + reconciliation.status (closed/mismatch/pending) 全部冻结, ExecP4302 已确认 gate 键集
- **43-03 (调度/告警) 输入就绪**: capture_auction_window/reconcile_window/resolve_sidecar_pool 签名冻结, ExecP4303 已确认; trading_day_confirmed 数据在场判定同源
- 回归保持: test_stockdb_provider / test_auction_probe / test_auction_sync / test_auction_columns 零改动全绿 (88 passed, 1 skipped)
- 零新增运行时依赖 (httpx/polars/zoneinfo stdlib); Watchlist.tsx 零触碰 (pre-existing user modification 未纳入任何 commit)

---
*Phase: 43-tday-auction-sidecar*
*Completed: 2026-08-07*
