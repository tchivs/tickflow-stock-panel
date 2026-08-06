---
phase: 31-auction-recap
plan: 1
subsystem: services
tags: [auction, recap, polars, read-only, deterministic-panel, pytest]

# Dependency graph
requires: []
provides:
  - "build_auction_recap(repo, as_of, engine=None, *, probe_resolver, now) -> dict — 只读三块装配 (real_auction_activity / open_gap_snapshot / preopen_signal_quality) + data_completeness 单头标签 + 逐块 note/source, 全 JSON 可序列化"
  - "render_auction_recap_markdown(panel) -> str — dict→markdown 纯函数 (含「确定性数据，非 AI 生成」标记)"
  - "build_auction_slice(panel) -> str — 同一 panel dict→LLM 切片, 与 render 构造性单源"
affects: [31-02 recap-market-delta, 31-03 market-recap-auction-endpoint, test_auction_recap_guard]

# Actuals (#2632) — pairs with plan estimate (50k tokens / 3 tasks).
# estimateTokens scale: chars/4 over realized diff (git diff d415ae8~1 1172dad, 62456 chars).
actuals:
  tokens: 15614
  tasks: 3
  commits: 7

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "只读装配服务: probe_resolver/now 注入形 + per-block fail-closed try/except + JSON 消毒 (NaN/Inf→None)"
    - "probe 解析一次仅透传 provenance; 历史 as_of 分区存在性主闸门, 今日 probe×分区双闸门"
    - "读侧窗口谓词 [09:15,09:25] + keep='last' 回归锁 (09:30+ bar 永不进竞价列)"
    - "EOD 口径 join (R6 铁律): 收盘兑现率/收阳率一律 enriched change_pct/close/open, 预览行 change_pct 绝不作来源"
    - "render/slice 双纯函数消费同一 panel dict (构造性单源, REV-04 验收 6 前置)"

key-files:
  created:
    - backend/app/services/auction_recap.py
    - backend/tests/test_auction_recap.py
  modified: []

key-decisions:
  - "pre_eod 判别用分钟算术 (now.hour*60+now.minute) vs (sched hour*60+minute) — W-2 修复, 避免 tz-aware/naive time TypeError"
  - "preferences 懒 import 用 from app.services.preferences import get_pipeline_schedule — W-1 修复, 匹配 31-03 守卫白名单 app.services.preferences"
  - "enriched 帧单次装载供 Block 2/3 复用 (同一 _load_enriched_for_date 帧); 盘前预览单次装载供 label + Block 3 共用"
  - "data_completeness lake_ok = real 块 present (分区存在且有窗口内行): 今日 probe 非 available / 窗口零行 → 诚实降级 no_auction_lake"
  - "Task 1 测试断言取计划允许的 B 形 (present:false + note 含「湖」), 与 Task 2 装配后最终行为一致"

patterns-established:
  - "只读铁律 docstring 用概念词 (绝不出现禁调用 token 字面串); import 面 ⊆ 31-03 白名单 (11 前缀 + stdlib 精确枚举, 无 math/json)"
  - "诚实缺项词汇常量 _SIGNAL_NOTE_* 统一注记; null-not-zero (镜像 auction_validation._null_metric)"

requirements-completed: [REV-01, REV-02, REV-03]

# Coverage metadata (#1602) — deterministic UAT routing.
coverage:
  - id: D1
    description: "build_auction_recap 只读装配: 三块 (real_auction_activity 分区读+窗口谓词+keep-last / open_gap_snapshot 读时计算 / preopen_signal_quality 族∩预览+EOD join) + data_completeness 优先级标签 + 逐块 note/source + JSON 可序列化"
    requirement: REV-01
    verification:
      - kind: unit
        ref: "backend/tests/test_auction_recap.py#test_no_auction_partition_omits_block"
        status: pass
      - kind: unit
        ref: "backend/tests/test_auction_recap.py#test_history_partition_block_present"
        status: pass
      - kind: unit
        ref: "backend/tests/test_auction_recap.py#test_today_double_gate_probe_x_partition"
        status: pass
      - kind: unit
        ref: "backend/tests/test_auction_recap.py#test_json_safe_nan_auction_amount"
        status: pass
      - kind: unit
        ref: "backend/tests/test_auction_recap.py#test_probe_does_not_affect_history_gate"
        status: pass
    human_judgment: false
  - id: D2
    description: "data_completeness 枚举 + pre_eod 判别 + 09:30+ bar 回归锁 + render「确定性数据，非 AI 生成」标记"
    requirement: REV-02
    verification:
      - kind: unit
        ref: "backend/tests/test_auction_recap.py#test_pre_eod_vs_no_auction_lake_discrimination"
        status: pass
      - kind: unit
        ref: "backend/tests/test_auction_recap.py#test_window_predicate_excludes_0931_continuous_bar"
        status: pass
      - kind: unit
        ref: "backend/tests/test_auction_recap.py#test_render_markdown_contains_deterministic_marker"
        status: pass
      - kind: unit
        ref: "backend/tests/test_auction_recap.py#test_data_completeness_full_three_blocks"
        status: pass
    human_judgment: false
  - id: D3
    description: "preopen_signal_quality 族∩预览策略集 + EOD 口径 join + n_missing + display_limit/pre-EOD/degraded 注记 + resonance; build_auction_slice 与 render 单源"
    requirement: REV-03
    verification:
      - kind: unit
        ref: "backend/tests/test_auction_recap.py#test_signal_quality_family_intersection"
        status: pass
      - kind: unit
        ref: "backend/tests/test_auction_recap.py#test_signal_quality_eod_join_n_missing"
        status: pass
      - kind: unit
        ref: "backend/tests/test_auction_recap.py#test_signal_quality_pre_eod_honest"
        status: pass
      - kind: unit
        ref: "backend/tests/test_auction_recap.py#test_signal_quality_resonance_and_slice_single_source"
        status: pass
    human_judgment: false

# Metrics
duration: 7min
completed: 2026-08-06
status: complete
---

# Phase 31 Plan 1: 竞价复盘确定性装配服务 (auction_recap.py) Summary

**只读竞价复盘装配服务 auction_recap.py — build_auction_recap 三块 (real_auction_activity / open_gap_snapshot / preopen_signal_quality) + data_completeness 枚举 + pre_eod 分钟算术判别 + render/slice 同 dict 纯函数单源, 18 项验收测试全绿**

## Performance

- **Duration:** 7 min
- **Started:** 2026-08-06T14:56:59Z
- **Completed:** 2026-08-06T15:03:19Z
- **Tasks:** 3
- **Files modified:** 2

## Accomplishments
- REV-01: `build_auction_recap(repo, as_of, engine=None, *, probe_resolver=None, now=None)` 只读装配服务 — 历史 as_of 分区存在性主闸门 (probe 不参与), 今日 probe×分区双闸门; 零写盘/零执行 (docstring 铁律概念词表述, 模拟 31-03 AST 守卫通过: import 白名单/无写路径/无禁调用 token)
- REV-02: data_completeness 单头标签按优先级 (pre_eod > no_auction_lake > no_premarket_preview > partial > full); pre_eod 分钟算术判别 (W-2 修复, 懒 import `from app.services.preferences import get_pipeline_schedule`, W-1 修复); 读侧窗口谓词 [09:15,09:25] + keep='last' 回归锁 (09:31 连续竞价 bar 永不进面板); render 含「确定性数据，非 AI 生成」标记
- REV-03: preopen_signal_quality 策略集 = `_AUCTION_FAMILY_IDS` (import 单一事实源) ∩ 预览 keys; EOD 口径 join (R6 铁律, 预览 change_pct 绝不作收盘兑现率) + n_missing 计数; display_limit / pre-EOD / degraded 注记; resonance 子块; build_auction_slice 与 render 同一 panel dict 构造性单源 (REV-04 验收 6 前置)
- 18 项验收测试全绿 (REV-01/02/03), 相邻套件回归绿 (test_attach_auction_columns_range + test_premarket_pool 27 passed), Watchlist.tsx 零触碰

## Task Commits

Each task committed atomically (TDD test → feat):

1. **Task 1: build_auction_recap 垂直切片 (签名/注入 + data_completeness + Block 2 + render)** - `d415ae8` (test) + `16288f9` (feat)
2. **Task 2: Block 1 real_auction_activity (分区读 + 窗口谓词回归锁 + 双闸门 + 量比)** - `48e601c` (test) + `295a02a` (feat)
3. **Task 3: Block 3 preopen_signal_quality + build_auction_slice 单源收尾** - `5f2ad52` (test) + `1172dad` (feat)

**Plan metadata:** final docs commit (this SUMMARY + STATE/ROADMAP/REQUIREMENTS)

## Files Created/Modified
- `backend/app/services/auction_recap.py` - 只读竞价复盘装配服务: build_auction_recap / render_auction_recap_markdown / build_auction_slice + 私有块装配 (_build_real_auction_activity / _build_open_gap_snapshot / _build_preopen_signal_quality / _build_ratio_subblock / _build_resonance / _json_safe)
- `backend/tests/test_auction_recap.py` - 18 项验收测试: repo_env / _FakeRepo / _write_auction_partition / _auction_rows (含 09:31 变体) / _write_premarket_preview / _preview_payload / _fake_verdict 三态 + 冻结 now 注入

## Decisions Made
- **W-2 修复 (PLAN-CHECK)**: pre_eod 判别用分钟算术 `(now.hour*60+now.minute) < (sched['hour']*60+sched['minute'])`, 绝不比较 tz-aware cn_now() 与 naive time (生产路径 TypeError 预防)
- **W-1 修复 (PLAN-CHECK)**: preferences 懒 import 形为 `from app.services.preferences import get_pipeline_schedule` — 模块名 ∈ 31-03 守卫白名单 (app.services.preferences), 避免 Wave-3 守卫失败
- **N-3 应用 (PLAN-CHECK)**: Block 1 闸门语义以 RESEARCH §2.2 为准 (面板构建与闸门在装配侧, 无「或 meta 之后」歧义 — 本计划不含 meta 集成)
- 策略集 import `_AUCTION_FAMILY_IDS` 单一事实源 (零硬编码漂移); enriched 帧单次装载供 Block 2/3 复用
- Task 1 测试断言取计划允许的 B 形 (present:false + note 含「湖」), 与 Task 2 装配后最终行为一致 (计划原文 "不在 blocks (或 present:false + 中文 note 含「湖」)")
- 服务模块避免 `import math`/`import json` (不在 31-03 `_IMPORT_EXACT`), NaN/Inf 判定用 `v != v or v in (inf, -inf)` — 守卫白名单纪律前置遵守

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing verification] Added full-label lock test**
- **Found during:** Task 3 (preopen_signal_quality 收尾)
- **Issue:** 计划 Task 3 done 标准要求「三块全装配后 data_completeness 可判 'full'」, 但 Task 3 测试清单未显式覆盖该路径 (分区+预览+enriched 齐 → 'full')
- **Fix:** 新增 `test_data_completeness_full_three_blocks` (probe available + 分区 + 预览 + enriched → data_completeness=='full' 且三块全 present)
- **Files modified:** backend/tests/test_auction_recap.py
- **Verification:** 全套 18 passed; 手工脚本确认三块 present → 'full' 标签
- **Committed in:** 1172dad (Task 3 commit)

**2. [Rule 1 - Internal refactor] Removed dead probe_status in build_auction_recap**
- **Found during:** Task 2 (Block 1 装配接线)
- **Issue:** 头标签判别改为 lake_ok = real 块 present 后, 顶层 probe_status 赋值不再被使用 (probe 判定已下沉进 _build_real_auction_activity)
- **Fix:** 删除顶层 `probe_status` 赋值; probe 判定保持单一实现于 Block 1 闸门内
- **Files modified:** backend/app/services/auction_recap.py
- **Verification:** 全套 18 passed
- **Committed in:** 295a02a (Task 2 commit)

---

**Total deviations:** 2 auto-fixed (1 missing verification, 1 cleanup)
**Impact on plan:** 两项均为计划内完成度/整洁度修正, 无范围蔓延; W-1/W-2/N-3 按指示应用, 非偏差。

## Issues Encountered
- 无阻塞问题。`test_no_auction_partition_omits_block` 断言需从「键缺席」演进为「present:false + note」以匹配 Task 2 装配后的最终行为 (计划明文允许两形, 取最终形)。

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- 31-02 (recap_market_stream delta 插入) 可直接消费 `build_auction_recap` / `render_auction_recap_markdown` / `build_auction_slice` 契约 (panel dict `{as_of, data_completeness, blocks, built_at}`)
- 31-03 (REV-05 端点) 消费 `build_auction_recap`; 服务 import 面已按 31-03 守卫白名单编写 (模拟守卫通过), docstring 铁律概念词表述就位
- 无已知阻塞

## Self-Check: PASSED

- Files: backend/app/services/auction_recap.py ✓, backend/tests/test_auction_recap.py ✓, 31-01-SUMMARY.md ✓
- Commits: d415ae8 / 16288f9 / 48e601c / 295a02a / 5f2ad52 / 1172dad 全部存在 ✓
- Final suite run: 18 passed ✓

---
*Phase: 31-auction-recap*
*Completed: 2026-08-06*
