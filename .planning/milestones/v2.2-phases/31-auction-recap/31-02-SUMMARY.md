---
phase: 31-auction-recap
plan: 2
subsystem: services
tags: [auction, recap, delta-stream, preferences, prompt-guardrail, pytest, frontend-literal]

# Dependency graph
requires:
  - phase: 31-01
    provides: "build_auction_recap / render_auction_recap_markdown / build_auction_slice (panel dict {as_of, data_completeness, blocks, built_at})"
provides:
  - "recap_market_stream 面板 delta 插入 (事件序锁死 meta → AI delta* → 面板 delta → done; 全缺席退化纯 AI; 面板构建异常韧性; AI 失败不发面板 R8)"
  - "_build_user_prompt 可选 auction_slice=None 参数 (R9 向后兼容) + 点评开启时护栏行追加局部 system 串 (_SYSTEM_PROMPT 常量不动)"
  - "preferences.get/set_recap_auction_commentary (默认 False) + settings PUT /preferences/recap-auction-commentary (no-job 变体) + GET 透传键"
  - "get_review_schedule 默认 15:40 (两处默认 literal + docstring 理由) + Review.tsx:105 兜底字面量 minute 40 (唯一前端触碰点)"
affects: [31-03 market-recap-auction-endpoint, verify-work UAT REV-04]

# Actuals (#2632) — pairs with the plan estimate (48k tokens / 3 tasks).
# estimateTokens scale: chars/4 over realized diff (git diff ffbb3b5..HEAD, 33527 chars).
actuals:
  tokens: 8381
  tasks: 3
  commits: 5

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "流内 delta 插入: 面板构建在 meta 前 (as_of 校验后), 面板 delta 在 AI try/except 后 done 前 — 事件序由测试逐项锁死"
    - "lazy import + 源模块 monkeypatch: build_auction_recap/render/build_auction_slice 与 stream_ai_text 均函数内 import, 测试 patch 源模块属性"
    - "可选参向后兼容: _build_user_prompt(..., auction_slice=None) 默认 None 输出逐位一致 (R9), 既有调用零改动"
    - "护栏行局部串: _SYSTEM_PROMPT + '\\n' + _AUCTION_GUARDRAIL 仅点评开启时组装, 常量不可变"
    - "偏好默认向后兼容: load().get('review_schedule', default) 语义 — 已存偏好优先于新默认 (15:40 只影响未设置用户)"

key-files:
  created:
    - backend/tests/test_market_recap_delta.py
  modified:
    - backend/app/services/market_recap.py
    - backend/app/services/preferences.py
    - backend/app/api/settings.py
    - frontend/src/pages/Review.tsx

key-decisions:
  - "面板构建位置: as_of 校验之后、meta 之前 (as_of 缺失 → 面板构建不发生, 首事件 error); 面板 delta 在 AI 成功后、done 之前 (R8: AI 失败不发面板兜底)"
  - "全缺席/构建异常 → 不 yield 面板 delta, 退化为纯 AI 报告 (验收 5 回归锁 + 韧性, 绝不让面板失败拖垮 AI 复盘)"
  - "测试 patch 目标 = 源模块 (app.services.auction_recap / app.services.ai_provider) — 与函数内 lazy import 语义匹配 (计划所述 patch market_recap 模块属性仅对顶层 import 生效)"
  - "切片单源断言用对象同一性: build_auction_slice 收到的 panel is build_auction_recap 返回的 panel (构造性单源)"
  - "护栏行常量 _AUCTION_GUARDRAIL 独立于 _SYSTEM_PROMPT; 点评开关经 get_recap_auction_commentary() 流时读取"

patterns-established:
  - "流式事件序契约以测试锁死 (meta → AI delta* → 面板 delta → done), 归档/SSE/飞书消费面零改动"
  - "偏好 API-first: PUT no-job 变体 (镜像 update_review_push) + GET 透传后端默认 → 前端自动跟随"
  - "向后兼容双保险: 可选参数默认 None + load().get(key, default) 语义, 已存偏好与新默认共存"

requirements-completed: [REV-04]

# Coverage metadata (#1602) — deterministic UAT routing.
coverage:
  - id: D1
    description: "recap_market_stream 面板 delta 事件序 (meta → AI delta* → 面板 delta → done) + 全缺席退化纯 AI + AI 失败不发面板 (R8) + as_of 缺失首事件 error + recap_market_once 累积含面板 + 面板构建异常韧性"
    requirement: REV-04
    verification:
      - kind: unit
        ref: "backend/tests/test_market_recap_delta.py#test_recap_stream_panel_delta_before_done"
        status: pass
      - kind: unit
        ref: "backend/tests/test_market_recap_delta.py#test_all_blocks_absent_no_panel_delta_pure_ai"
        status: pass
      - kind: unit
        ref: "backend/tests/test_market_recap_delta.py#test_ai_failure_error_return_no_panel"
        status: pass
      - kind: unit
        ref: "backend/tests/test_market_recap_delta.py#test_as_of_missing_first_event_error_no_panel"
        status: pass
      - kind: unit
        ref: "backend/tests/test_market_recap_delta.py#test_recap_once_content_includes_panel_after_ai"
        status: pass
      - kind: unit
        ref: "backend/tests/test_market_recap_delta.py#test_panel_build_exception_stream_survives"
        status: pass
    human_judgment: false
  - id: D2
    description: "可选 AI 点评: pref 默认 False + round-trip, settings PUT/GET 透传键, _build_user_prompt 3 参向后兼容 (R9) + 切片节在 focus 后, 护栏行仅点评开启时追加 (_SYSTEM_PROMPT 不动), 切片与面板同 dict 构造性单源, 全缺席切片诚实声明无数据"
    requirement: REV-04
    verification:
      - kind: unit
        ref: "backend/tests/test_market_recap_delta.py#test_commentary_pref_default_false_roundtrip"
        status: pass
      - kind: unit
        ref: "backend/tests/test_market_recap_delta.py#test_settings_put_get_commentary"
        status: pass
      - kind: unit
        ref: "backend/tests/test_market_recap_delta.py#test_build_user_prompt_backward_compat_and_slice"
        status: pass
      - kind: unit
        ref: "backend/tests/test_market_recap_delta.py#test_stream_guardrail_only_when_commentary_on"
        status: pass
      - kind: unit
        ref: "backend/tests/test_market_recap_delta.py#test_slice_and_panel_single_dict_source"
        status: pass
      - kind: unit
        ref: "backend/tests/test_market_recap_delta.py#test_slice_honest_when_panel_all_absent"
        status: pass
    human_judgment: false
  - id: D3
    description: "调度默认 15:40: preferences 默认 (两处 literal + docstring 理由) + Review.tsx:105 兜底字面量 minute 40 + 已存偏好保留 + 15:00 下限不动 + GET 透传联动 + 注册消费零改动"
    requirement: REV-04
    verification:
      - kind: unit
        ref: "backend/tests/test_market_recap_delta.py#test_review_schedule_default_1540"
        status: pass
      - kind: unit
        ref: "backend/tests/test_market_recap_delta.py#test_review_schedule_saved_pref_retained"
        status: pass
      - kind: unit
        ref: "backend/tests/test_market_recap_delta.py#test_review_schedule_floor_unchanged"
        status: pass
      - kind: unit
        ref: "backend/tests/test_market_recap_delta.py#test_review_tsx_fallback_literal_1540"
        status: pass
      - kind: unit
        ref: "backend/tests/test_market_recap_delta.py#test_get_preferences_schedule_passthrough"
        status: pass
      - kind: unit
        ref: "backend/tests/test_market_recap_delta.py#test_review_job_registration_consumes_schedule"
        status: pass
      - kind: unit
        ref: "cd frontend && npm run build (tsc + vite)"
        status: pass
    human_judgment: false

# Metrics
duration: 9min
completed: 2026-08-06
status: complete
---

# Phase 31 Plan 2: 复盘集成 (recap_market_stream 面板 delta + 可选 AI 点评 + 调度默认 15:40) Summary

**REV-04 复盘集成落地 — recap_market_stream 事件序锁死 (meta → AI delta* → 面板 delta → done), 面板经 delta 机制三跳全收零改动; 可选 AI 点评默认 OFF (pref + PUT/GET + 护栏行 + 切片同 dict 单源); 调度默认 15:40 (preferences + Review.tsx:105); 18 项验收测试 + hhxg 回归 + 前端 build 全绿**

## Performance

- **Duration:** 9 min
- **Started:** 2026-08-06T15:05:40Z
- **Completed:** 2026-08-06T15:14:39Z
- **Tasks:** 3
- **Files modified:** 5

## Accomplishments
- REV-04 验收 1/5: `recap_market_stream` 面板构建 (build_auction_recap, 与 overview 同日单源) 在 as_of 校验后、meta 前; 面板 delta (render_auction_recap_markdown) 在 AI try/except 后、done 前 — 事件序锁死, 全缺席 → 不 yield 面板 delta (纯 AI 退化回归锁), 面板构建异常 → 记日志按无面板处理 (流不崩), AI 失败 error+return 不发面板 (R8)
- REV-04 验收 4: 面板经 delta 机制并入 content — `recap_market_once` / 定时 `_stream_review_with_retry` / 前端 reviewStore / 归档 `save_report` / 飞书企微 `_maybe_push_review` 全部零改动即收到面板
- REV-04 验收 6/R9/R3: `_build_user_prompt(overview, news, focus, auction_slice=None)` 可选参 (默认 None 输出逐位一致, test_hhxg_market.py:158-180 回归锚点); preferences `get/set_recap_auction_commentary` 默认 False + settings `PUT /preferences/recap-auction-commentary` (no-job 变体) + GET 透传键; 点评开启时 `build_auction_slice(panel)` 喂 prompt (同 dict 构造性单源) + 护栏行追加局部 system 串 (`_SYSTEM_PROMPT` 常量不动)
- REV-04 验收 7: `get_review_schedule` 默认 minute 10→40 (load().get 默认 + .get 回退两处, docstring 注明 15:30 竞价同步 + 15:35 股池持久化理由); 已存偏好保留; 15:00 下限零改动; Review.tsx:105 兜底字面量 minute 40 (唯一前端触碰点, Watchlist.tsx 零触碰)
- 18 项验收测试全绿 (test_market_recap_delta.py), test_hhxg_market.py 10 项回归绿, 相邻套件 test_auction_recap + test_premarket_pool 31 项回归绿, 前端 `npm run build` (tsc + vite) 通过

## Task Commits

Each task committed atomically (TDD test → feat):

1. **Task 1: recap_market_stream 面板 delta 垂直切片 (事件序 + 全缺席退化回归锁)** - `93b2c85` (test) + `b363bfa` (feat)
2. **Task 2: 可选 AI 点评 (pref + PUT/GET + prompt 可选参 + 护栏 + 切片单源)** - `eb173fe` (test) + `9e46346` (feat)
3. **Task 3: 调度默认 15:40 (preferences + Review.tsx:105 + 回归测试 + 前端 build)** - `3888951` (feat+test)

**Plan metadata:** final docs commit (this SUMMARY + STATE/ROADMAP/REQUIREMENTS)

## Files Created/Modified
- `backend/app/services/market_recap.py` - 面板构建插入 (as_of 校验后/meta 前, try/except 韧性) + 面板 delta 插入 (AI try/except 后/done 前, 全缺席不发) + `_AUCTION_GUARDRAIL` 常量 + `_build_user_prompt` 可选 `auction_slice` 参数 + AI 组装点 (点评切片 + 局部 system 护栏串)
- `backend/app/services/preferences.py` - `get/set_recap_auction_commentary` (默认 False) + `get_review_schedule` 默认 15:40 (两处 literal + docstring 理由)
- `backend/app/api/settings.py` - `RecapAuctionCommentaryIn` + `PUT /preferences/recap-auction-commentary` (no-job 变体) + GET /preferences 透传 `recap_auction_commentary` 键
- `frontend/src/pages/Review.tsx` - :105 兜底字面量 `minute: 10 → 40` (1 行, 唯一前端触碰点)
- `backend/tests/test_market_recap_delta.py` - 18 项验收测试: 事件序 / 全缺席退化逐位一致 / AI 失败 R8 / as_of 缺失 / 累积含面板 / 面板异常韧性 / pref round-trip / PUT+GET / 向后兼容 / 护栏 / 切片单源 / 切片诚实 / 调度默认 15:40 / 已存偏好保留 / 15:00 下限 / Review.tsx 字面量 / GET 透传联动 / 注册消费零改动

## Decisions Made
- **W-3 应用 (PLAN-CHECK)**: 以实测锚点为准 — `recap_market_stream` done 在 :324 (非计划引用的 :354), 插入点按结构定位 (AI try/except 后、done 前), 不依赖行号
- **面板构建位置**: as_of 校验之后、meta 之前 — as_of 缺失 → 面板构建不发生, 首事件 error (验收 4 测试 spy 断言 `calls == []`)
- **测试 patch 目标 = 源模块属性** (app.services.auction_recap / app.services.ai_provider / app.services.hhxg_market): 与生产 lazy import (函数内 `from ... import ...`) 语义匹配 — 计划所述 patch `market_recap.build_auction_recap` 仅对顶层 import 生效, 按实现意图取源模块 patch
- **切片单源断言用对象同一性** (`slice_inputs[0] is received["panel"]`): 构造性单源比内容相等更强 (防双源漂移)
- 护栏行经 `_AUCTION_GUARDRAIL` 常量组装到局部 system 串, `_SYSTEM_PROMPT` 常量逐字不动; 点评开关流时读取 (默认 False)

## Deviations from Plan

None - plan executed exactly as written (W-3 line-anchor refresh applied as directed; no auto-fix deviations).

## Issues Encountered
- 无阻塞问题。RED 阶段 4 项既有行为回归锁 (全缺席退化 / AI 失败 / as_of 缺失 / 面板异常韧性) 在实现前即通过 — 属预期 (它们锁定的是既有/缺失行为, 新行为由事件序 + 累积含面板两测试驱动 RED); 面板异常韧性测试在实现前平凡通过 (面板构建路径尚不存在), 实现后真正生效。

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- 31-03 (REV-05 独立只读端点) 可消费 `build_auction_recap` / `render_auction_recap_markdown` (31-01 契约); 本计划零文件重叠 (31-03 独占 api/market_recap_auction.py + 守卫)
- 消费面零改动铁律保持: `recap_market_once` / `_stream_review_with_retry` / `_maybe_push_review` / `market_recap_reports` / `api/market_recap.py` / `reviewStore.ts` / `Watchlist.tsx` 全部未触碰
- 零新增依赖; `_SYSTEM_PROMPT` 常量不变; 无已知阻塞

## Self-Check: PASSED

- Files: backend/app/services/market_recap.py ✓, backend/app/services/preferences.py ✓, backend/app/api/settings.py ✓, frontend/src/pages/Review.tsx ✓, backend/tests/test_market_recap_delta.py ✓, 31-02-SUMMARY.md ✓
- Commits: 93b2c85 / b363bfa / eb173fe / 9e46346 / 3888951 全部存在 ✓
- Final suite run: test_market_recap_delta 18 + test_hhxg_market 10 + test_auction_recap/test_premarket_pool 31 all passed; frontend build ✓

---
*Phase: 31-auction-recap*
*Completed: 2026-08-06*
