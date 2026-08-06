---
phase: 31-auction-recap
verified: 2026-08-06T18:20:00Z
status: passed
score: 10/10 must-haves verified
behavior_unverified: 0 # 行为依赖 truth 均有命名测试覆盖不变量 (事件序/双闸门/窗口谓词/退化/R8/已存偏好保留), orchestrator spot-check 确认通过 (acceptance 禁止本验证器重跑测试)
overrides_applied: 0
human_verification:
  - test: "真实交易日 15:35+ (竞价同步 15:30 + 股池持久化 15:35 之后) 触发定时复盘 (或手动生成): 确认 Review 页复盘正文尾部出现「📊 竞价复盘(确定性数据，非 AI 生成)」面板, 三块 (真实竞价活跃度 / 开盘涨幅快照 / 盘前信号质量) 均 present, 带逐块注记与来源行; 归档报告与飞书推送同含面板"
    expected: "面板三块全亮、确定性标记与来源行可见; 归档 content 与推送文本含面板小节; data_completeness == 'full'"
    why_human: "真实调度时序 + SSE 流式渲染 + 归档/外部投递的运行时行为, 静态验证无法执行"
  - test: "真实后端用户流 (浏览器 + API): PUT /preferences/recap-auction-commentary {enabled:true} 后手动生成复盘, 观察 AI 正文是否引用竞价切片数值且仅在切片范围内; 再置 false 确认 AI 输出不含竞价节"
    expected: "开启时 AI 引用切片数值 (无编造数值), 数据缺失时明说「今日无竞价数据」; 关闭时输出与既有版一致"
    why_human: "LLM 生成行为 + 前后端联通需要真实模型调用确认"
  - test: "真实后端用户流 (浏览器): 未登录/guest 会话访问 GET /api/market-recap/auction, 确认返回掩码视图 (身份 ******、竞价值剥离、聚合统计保留、无 markdown)"
    expected: "guest 视图无任何逐标的身份/竞价值明文; vip 视图含 markdown 与明文"
    why_human: "鉴权中间件与真实渲染面的端到端确认"
---

# Phase 31: 竞价复盘 (Auction Recap) Verification Report

**Phase Goal:** The post-close recap gains a deterministic auction dimension — a read-only `auction_recap.py` assembles real auction activity / `open_gap` snapshot / premarket signal-quality blocks from frozen assets, appended as a delta before the `done` event (SSE/archive/Feishu all receive it); honest `data_completeness` enum + `pre_eod` degradation; optional AI commentary defaults OFF; default recap schedule moves to 15:40.
**Verified:** 2026-08-06T18:20:00Z
**Status:** passed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| #   | Truth   | Status     | Evidence       |
| --- | ------- | ---------- | -------------- |
| 1   | REV-01 只读三块装配: `build_auction_recap(repo, as_of, engine=None, *, probe_resolver=None, now=None)` 从冻结资产 (kline_auction 分区 / premarket_results 预览 / enriched 读时计算) 装配 real_auction_activity / open_gap_snapshot / preopen_signal_quality; 历史 as_of 分区存在性主闸门 (probe 不参与), 今日 probe×分区双闸门; 零写盘零执行 | ✓ VERIFIED | `auction_recap.py:389-563` — 分区存在性 `part.exists()` 主闸门 + `as_of == today and probe_status != "available"` 双闸门; `_build_real_auction_activity` :180-260; 禁 token grep 全净 (无 run_all/run_preset/write_cache/persist_point_snapshot/save_report); 命名测试: test_history_partition_block_present / test_probe_does_not_affect_history_gate / test_today_double_gate_probe_x_partition / test_no_auction_partition_omits_block / test_json_safe_nan_auction_amount |
| 2   | REV-02 诚实注解: `data_completeness` 枚举 {full, no_auction_lake, no_premarket_preview, pre_eod, partial} 按优先级 pre_eod > no_auction_lake > no_premarket_preview > partial > full 取单头标签; 缺失块 `{present:false, note, source}` 显式注记; 09:30+ 连续竞价 bar 永不进竞价列 (窗口谓词 [09:15,09:25] + keep='last'); pre_eod 分钟算术判别; render 含「确定性数据，非 AI 生成」标记 | ✓ VERIFIED | `_DATA_COMPLETENESS_VALUES` :45; 标签判别 :548-556; `_AUCTION_WINDOW_START/END_MIN=555/565` :47-48 + filter + `unique(subset=["symbol"], keep="last")` :216-231; pre_eod 分钟算术 :521-526 (W-2 修复); render 表头「📊 竞价复盘(确定性数据，非 AI 生成)」 :596-600; 命名测试: test_pre_eod_vs_no_auction_lake_discrimination / test_window_predicate_excludes_0931_continuous_bar / test_render_markdown_contains_deterministic_marker / test_data_completeness_full_three_blocks |
| 3   | REV-03 盘前信号质量块: 策略集 = `_AUCTION_FAMILY_IDS` (import 单一事实源) ∩ 预览 results keys (只含实际有行策略); 逐策略 {n, avg open_gap, avg change_pct, 开盘兑现率, 收盘兑现率, 收阳率}; 收盘兑现率/收阳率一律 EOD enriched 帧 change_pct/close/open 左联 (预览行绝不作来源); n_missing 计数不填充; display_limit/pre-EOD/degraded 注记 + resonance 子块 | ✓ VERIFIED | `_build_preopen_signal_quality` :317-399 — 族∩预览 :351-354, EOD join :336-340, n_missing :371-372; `_build_resonance` :401-446; 命名测试: test_signal_quality_family_intersection / test_signal_quality_eod_join_n_missing / test_signal_quality_pre_eod_honest / test_signal_quality_resonance_and_slice_single_source / test_signal_quality_display_limit_note |
| 4   | REV-04 事件序: `recap_market_stream` 面板 delta 插在 AI try/except 之后、`done` 之前 (meta → AI delta* → 面板 delta → done); AI 失败 error+return 不发面板兜底 (R8); 面板全缺席 → 退化纯 AI 报告 (协议不破坏); 面板构建异常 → 记日志按无面板处理 | ✓ VERIFIED | `market_recap.py:304-314` (面板构建 as_of 校验后/meta 前), :371-380 (面板 delta AI 后 done 前), :356-366 (AI 失败 error+return), :371 (any present 才发); 命名测试: test_recap_stream_panel_delta_before_done (断言 types == ["meta","delta","delta","delta","done"]) / test_all_blocks_absent_no_panel_delta_pure_ai / test_ai_failure_error_return_no_panel / test_as_of_missing_first_event_error_no_panel / test_panel_build_exception_stream_survives / test_recap_once_content_includes_panel_after_ai |
| 5   | REV-04 可选 AI 点评: `recap_auction_commentary` 默认 False (get/set) + settings PUT no-job 变体 + GET 透传; 开启时 `build_auction_slice(panel)` 喂 prompt (同 dict 构造性单源) + 护栏行追加局部 system 串 (`_SYSTEM_PROMPT` 不动) | ✓ VERIFIED | `preferences.py:498-512` (默认 False), `settings.py:1482-1495` (PUT) + :422 (GET 透传); `market_recap.py:340-351` (流时读取 + 切片 + 护栏组装), `_AUCTION_GUARDRAIL` :134-139 独立常量; 命名测试: test_commentary_pref_default_false_roundtrip / test_settings_put_get_commentary / test_stream_guardrail_only_when_commentary_on / test_slice_and_panel_single_dict_source / test_slice_honest_when_panel_all_absent |
| 6   | REV-04 向后兼容: `_build_user_prompt(overview, news, focus, auction_slice=None)` 可选参默认 None → 既有调用零改动输出逐位一致; 非 None 时 focus 节后追加 `## 竞价复盘数据(确定性切片)` 节 | ✓ VERIFIED | `market_recap.py:184-186` (签名), :235-236 (切片节追加); 回归锚点 `test_hhxg_market.py:158-180` 仍以 3 参调用 :168/:180; 命名测试: test_build_user_prompt_backward_compat_and_slice |
| 7   | REV-04 调度默认 15:40: `get_review_schedule` 默认 literal 两处 minute 10→40 + docstring 理由; 已存偏好保留 (load().get 语义); 15:00 下限不动; Review.tsx:105 兜底字面量 minute 40 (唯一前端触碰点) | ✓ VERIFIED | `preferences.py:433-447` — 默认 dict `{"enabled": False, "hour": 15, "minute": 40}` + `.get("minute", 40)` 回退, set_review_schedule :449-461 15:00 下限保持; `Review.tsx:105` 字面量 `{ enabled: false, hour: 15, minute: 40 }`; 命名测试: test_review_schedule_default_1540 / test_review_schedule_saved_pref_retained / test_review_schedule_floor_unchanged / test_review_tsx_fallback_literal_1540 (读真实文件且断言 minute:10 不存在) / test_get_preferences_schedule_passthrough / test_review_job_registration_consumes_schedule |
| 8   | REV-05 独立只读端点: `GET /api/market-recap/auction` — as_of 严格双重校验 (regex fullmatch + fromisoformat → 400 invalid as_of 绝不 500); 缺省 latest_date / None → 诚实空态; 无 present 块 → 200 {available:false, blocks:{}, reason}; guest 掩码 (身份 ****** + 竞价值剥离 + 聚合/状态标注保留 + probe 剥离 + 无 markdown); vip → markdown | ✓ VERIFIED | `market_recap_auction.py:74-138` — `_AS_OF_RE` + 400 双检 :84-92, 空态 :105-116 + :127-134, `_masked_row/_mask_block/_mask_guest_recap` :44-72, guest/vip 分支 :135-138; `main.py:872-874` 注册 (REV-05 注释); 命名测试: test_as_of_valid_returns_200 / test_empty_returns_available_false / test_full_assembly_vip / test_guest_masking / test_as_of_default_latest_date |
| 9   | POOL-03 AST 守卫 6 项: 两守卫目标存在非空 / 无执行族 import + 禁 import token (auction_sync\|pool_snapshot\|pool_backfill) / GET-only / 无写路径 + 禁调用 token (run_all\|run_preset\|write_cache\|persist_point_snapshot\|save_report) / 无 strategy_cache / import 白名单与实装 imports 吻合 | ✓ VERIFIED | `test_auction_recap_guard.py` 6 test 全在; 实装 import 面逐一核对 ⊆ 白名单 (auction_recap.py: stdlib logging/datetime/typing + polars + app.market_time + app.services.{auction_columns,auction_probe,auction_validation,premarket_snapshot,screener,preferences}; market_recap_auction.py: stdlib + fastapi + app.services.{auction_recap,guest_masking,screener}); 两文件源码 grep 零禁 token 命中; W-1 修复确认 (懒 import 形为 `from app.services.preferences import get_pipeline_schedule`) |
| 10  | 零触碰 + 文档: Watchlist.tsx 全程零触碰; docs/features.md 竞价复盘节 (三块/data_completeness/pre_eod/事件序/15:40/点评默认关/REV-05/POOL-03) | ✓ VERIFIED | `git log d415ae8~1..HEAD -- frontend/src/pages/Watchlist.tsx` 零提交; Review.tsx 仅 3888951 (1 行字面量); `docs/features.md:143-170` 完整节 (读实文确认) |

**Score:** 10/10 truths verified (0 present, behavior-unverified)

### Required Artifacts

| Artifact | Expected    | Status | Details |
| -------- | ----------- | ------ | ------- |
| `backend/app/services/auction_recap.py` | 只读装配服务 build_auction_recap / render_auction_recap_markdown / build_auction_slice (REV-01/02/03) | ✓ VERIFIED | 700 行, 三块 + 枚举 + 双闸门 + 窗口谓词 + EOD join + 渲染/切片纯函数; 零禁 token; import 面 ⊆ 白名单 |
| `backend/tests/test_auction_recap.py` | 18 项验收测试 | ✓ VERIFIED | 18 test 函数实查在列 (含 09:31 变体、probe 三态、冻结 now 注入、repo_env fixture) |
| `backend/app/services/market_recap.py` | recap_market_stream 面板 delta + _build_user_prompt 可选参 + 护栏常量 | ✓ VERIFIED | 事件序实现 + `auction_slice=None` 签名 + `_AUCTION_GUARDRAIL` 独立常量 |
| `backend/app/services/preferences.py` | recap_auction_commentary 默认 False + get_review_schedule 15:40 | ✓ VERIFIED | :498-512 开关, :433-447 默认 15:40 两处 literal + docstring 理由, 15:00 下限 :449-461 |
| `backend/app/api/settings.py` | PUT /preferences/recap-auction-commentary + GET 透传 | ✓ VERIFIED | RecapAuctionCommentaryIn :1482 + no-job PUT :1486-1495 + GET :422 |
| `frontend/src/pages/Review.tsx` | :105 兜底字面量 minute 40 (唯一前端触碰) | ✓ VERIFIED | :105 `{ enabled: false, hour: 15, minute: 40 }` |
| `backend/app/api/market_recap_auction.py` | GET /api/market-recap/auction 只读端点 | ✓ VERIFIED | 138 行, GET-only, as_of 双重校验, 诚实空态, guest 掩码 DTO |
| `backend/app/main.py` | market_recap_auction.router 注册 | ✓ VERIFIED | import :31-32 + include_router :874 (market_recap.router :872 后) |
| `backend/tests/test_auction_recap_guard.py` | 6 项 POOL-03 AST 守卫 | ✓ VERIFIED | 6 test 全在, 白名单与实际 imports 逐项吻合 |
| `backend/tests/test_auction_recap_endpoint.py` | 端点集成测试 5 项 | ✓ VERIFIED | 200/400/空态/guest 掩码/latest_date 缺省 |
| `backend/tests/test_market_recap_delta.py` | 18 项 REV-04 验收 | ✓ VERIFIED | 事件序/退化/R8/切片单源/护栏/调度默认 全在 |
| `docs/features.md` | 竞价复盘节 (REV-01..05) | ✓ VERIFIED | :143-170 独立节, 覆盖全部要点 |

### Key Link Verification

| From | To  | Via | Status | Details |
| ---- | --- | --- | ------ | ------- |
| `services/auction_recap.py` | `services/auction_validation.py` | `from app.services.auction_validation import _AUCTION_FAMILY_IDS` (:32) | ✓ WIRED | 单一事实源, 零硬编码 |
| `services/auction_recap.py` | `services/premarket_snapshot.py` | `load_premarket_snapshot(repo.store.data_dir, as_of.isoformat())` (:560) | ✓ WIRED | 预览装载, None → 块省略 |
| `services/auction_recap.py` | `services/screener.py` | `ScreenerService(repo)._load_enriched_for_date(as_of)` (:534) + `_strategy_display_name` (:33) | ✓ WIRED | EOD 口径 + 显示名 |
| `services/auction_recap.py` | `services/auction_columns.py` | `attach_auction_columns_range(panel, as_of, as_of, repo)` (:275) | ✓ WIRED | 量比分母复用 |
| `services/auction_recap.py` | `services/preferences.py` | 懒 import `get_pipeline_schedule()` (:343, :521) | ✓ WIRED | pre_eod 判别, W-1 修复形 |
| `services/auction_recap.py` | `services/auction_probe.py` | `resolve_auction_probe` 注入点 (:31, :518) | ✓ WIRED | 今日双闸门 + provenance |
| `services/market_recap.py` | `services/auction_recap.py` | `build_auction_recap` (:307) + `render_auction_recap_markdown` (:374) + `build_auction_slice` (:346) | ✓ WIRED | 与 AI 复盘同日 (as_of 单一来源) |
| `services/market_recap.py` | `services/preferences.py` | `get_recap_auction_commentary()` (:344) | ✓ WIRED | 流时读取点评开关 |
| `frontend/Review.tsx` | `services/preferences.py` | :105 兜底字面量 minute 40 对齐后端默认 | ✓ WIRED | prefs 拉取失败兜底 |
| `api/settings.py` | `services/preferences.py` | `set_recap_auction_commentary(req.enabled)` (:1494) | ✓ WIRED | no-job PUT 变体 |
| `api/market_recap_auction.py` | `services/auction_recap.py` | `build_auction_recap` + `render_auction_recap_markdown` (:27-28, :119, :138) | ✓ WIRED | 与 REV-04 面板构造性同源 |
| `api/market_recap_auction.py` | `services/guest_masking.py` | `MASKED_IDENTITY` (:28) | ✓ WIRED | guest 掩码 DTO |
| `app/main.py` | `api/market_recap_auction.py` | `include_router(market_recap_auction.router)` (:874) | ✓ WIRED | market_recap.router 后注册 |
| `tests/test_auction_recap_guard.py` | 两守卫目标文件 | AST 存在性断言 (:60-67) | ✓ WIRED | 防守卫悬空 |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
| -------- | ------------- | ------ | ------------------ | ------ |
| `auction_recap.py` Block 1 | df (竞价行) | `repo.store.data_dir / "kline_auction" / date={as_of} / part.parquet` read_parquet | ✓ 真实分区读 + 窗口谓词过滤 | ✓ FLOWING |
| `auction_recap.py` Block 2 | enriched_df.open_gap | `ScreenerService(repo)._load_enriched_for_date(as_of)` 读时计算 | ✓ 真实 enriched 帧 (open_gap 派生列) | ✓ FLOWING |
| `auction_recap.py` Block 3 | preview.results | `load_premarket_snapshot(data_dir, as_of)` | ✓ 真实盘前预览分区 (None → 块省略, 无静态占位) | ✓ FLOWING |
| `auction_recap.py` Block 3 EOD join | eod_map change_pct/close/open | 同一 enriched 帧按 symbol 左联 | ✓ 真实 EOD 口径, 预览行绝不作收盘兑现率 | ✓ FLOWING |
| `market_recap_auction.py` 空态 | available/blocks | present 块过滤 (`v.get("present")`) | ✓ 诚实空态 200, 绝无 0 填/静态假数据 | ✓ FLOWING |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
| -------- | ------- | ------ | ------ |
| 事件序 meta→AI→面板→done | 命名测试 `test_recap_stream_panel_delta_before_done` (断言 types == ["meta","delta","delta","delta","done"]) | 存在; executor/orchestrator 报告通过 (1686 全量 + 47 定向 spot-check) | ✓ PASS |
| 09:30+ bar 排除回归锁 | `test_window_predicate_excludes_0931_continuous_bar` (fixture 注入 09:31 行) | 存在; 报告通过 | ✓ PASS |
| pre_eod vs no_auction_lake 判别 | `test_pre_eod_vs_no_auction_lake_discrimination` (冻结 now 注入) | 存在; 报告通过 | ✓ PASS |
| 历史闸门 probe 不参与 | `test_probe_does_not_affect_history_gate` | 存在; 报告通过 | ✓ PASS |
| AI 失败不发面板 (R8) | `test_ai_failure_error_return_no_panel` | 存在; 报告通过 | ✓ PASS |
| 全缺席退化纯 AI | `test_all_blocks_absent_no_panel_delta_pure_ai` (content == "AI-1AI-2" 逐位一致) | 存在; 报告通过 | ✓ PASS |
| 已存偏好保留 + 15:00 下限 | `test_review_schedule_saved_pref_retained` / `test_review_schedule_floor_unchanged` | 存在; 报告通过 | ✓ PASS |
| 向后兼容 3 参调用 | `test_hhxg_market.py:158-180` 回归锚点 + `test_build_user_prompt_backward_compat_and_slice` | 存在; 报告通过 | ✓ PASS |
| guest 掩码 | `test_guest_masking` | 存在; 报告通过 | ✓ PASS |
| 切片同 dict 单源 | `test_slice_and_panel_single_dict_source` (对象同一性) + `test_signal_quality_resonance_and_slice_single_source` | 存在; 报告通过 | ✓ PASS |

> 注: acceptance 禁止本验证器重跑测试 (不修改源码/不运行构建/测试)。上述命名测试的存在性与断言内容由直接阅读确认, 通过状态以 executor 全量 1686 passed + 2 skipped + 前端 build 报告及 orchestrator 47 项定向 spot-check 为据 (与 Phase 28/30 验证器同规约)。

### Probe Execution

| Probe | Command | Result | Status |
| ----- | ------- | ------ | ------ |
| — | 本阶段未声明 probe 脚本 (PLAN/SUMMARY 均无 probe-*.sh; 验收以 pytest 命名测试承载) | — | SKIPPED (无 probe 声明) |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
| ----------- | ---------- | ----------- | ------ | -------- |
| REV-01 | 31-01 | 只读装配服务 + 分区存在性主闸门 (今日双闸门) + 零执行 | ✓ SATISFIED | Truth 1, Artifacts 1-2, guard 6 项 |
| REV-02 | 31-01 | data_completeness 枚举 + 缺块注记 + 09:30+ 排除 + pre_eod + 确定性标记 | ✓ SATISFIED | Truth 2, 命名测试 4 项 |
| REV-03 | 31-01 | 信号质量块族∩预览 + EOD 口径 join + n_missing | ✓ SATISFIED | Truth 3, 命名测试 5 项 |
| REV-04 | 31-02 | 面板 delta 事件序 + 点评默认关 + 向后兼容 + 调度 15:40 | ✓ SATISFIED | Truths 4-7, test_market_recap_delta 18 项 |
| REV-05 | 31-03 | 独立只读 GET 端点 + 诚实空态 + guest 掩码 + 守卫 + 文档 | ✓ SATISFIED | Truths 8-10, endpoint 5 + guard 6 项 |

无孤儿需求: REQUIREMENTS.md 中 Phase 31 映射的 REV-01..05 全部被计划声明且全部满足。

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
| ---- | ---- | ------- | -------- | ------ |
| — | — | 无 (TBD/FIXME/XXX/PLACEHOLDER/TODO 全零命中; 无 stub/空实现/硬编码空数据; 禁调用 token 零命中于守卫目标; 全 phase 文件 git 已提交) | — | — |

### Human Verification Required

项目惯例 (Phase 28/30): 运行时/视觉类项目随 passed 报告列出并路由至 `31-UAT.md`, 不阻塞 passed 判定 (确定性验收由命名测试锁定):

### 1. 真实调度时序 + 面板端到端渲染

**Test:** 真实交易日 15:35+ (竞价同步 15:30 + 股池持久化 15:35 之后) 触发定时复盘 (或手动生成): 确认 Review 页复盘正文尾部出现「📊 竞价复盘(确定性数据，非 AI 生成)」面板, 三块均 present, 带逐块注记与来源行; 归档报告与飞书推送同含面板。
**Expected:** 面板三块全亮、确定性标记与来源行可见; 归档 content 与推送文本含面板小节; data_completeness == 'full'。
**Why human:** 真实调度时序 + SSE 流式渲染 + 归档/外部投递的运行时行为, 静态验证无法执行。

### 2. 可选 AI 点评真实调用

**Test:** PUT /preferences/recap-auction-commentary {enabled:true} 后手动生成复盘, 观察 AI 正文是否引用竞价切片数值且仅在切片范围内; 再置 false 确认 AI 输出不含竞价节。
**Expected:** 开启时 AI 引用切片数值 (无编造), 数据缺失时明说「今日无竞价数据」; 关闭时输出与既有版一致。
**Why human:** LLM 生成行为需要真实模型调用确认。

### 3. Guest 掩码端到端

**Test:** 未登录/guest 会话访问 GET /api/market-recap/auction, 确认返回掩码视图 (身份 ******、竞价值剥离、聚合统计保留、无 markdown)。
**Expected:** guest 视图无任何逐标的身份/竞价值明文; vip 视图含 markdown 与明文。
**Why human:** 鉴权中间件与真实渲染面的端到端确认。

### Gaps Summary

无 gaps。全部 10 项 must-have 真值 (4 条 ROADMAP 成功准则 + REV-01..05) 均在代码中实现并被命名测试覆盖; 守卫白名单与实际 imports 逐项吻合; Watchlist.tsx 零触碰经 git log 证实; 唯一偏差 (W-1/W-2/W-3 PLAN-CHECK 警告) 均已按修复指示落地并确认。

---

_Verified: 2026-08-06T18:20:00Z_
_Verifier: Claude (gsd-verifier)_
