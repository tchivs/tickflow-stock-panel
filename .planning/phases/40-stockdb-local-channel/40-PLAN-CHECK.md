# Phase 40 Plan Check — stockdb 本地通道接入 (Local Source Channel)

**Checked:** 2026-08-07 · **Plans:** 40-01 / 40-02 / 40-03 (commit 445369b) · **Method:** goal-backward (gsd-plan-checker), 只读评审, 零代码修改, 零 commit
**参照物:** REQUIREMENTS.md LOCAL-01..04 · ROADMAP Phase 40 (5 success criteria) · RESEARCH.md (497 行) · PATTERNS.md · 既有源码/测试逐条核实 (chain.py / preferences.py / kline_sync.py / normalizer.py / rate_limits.py / api/settings.py / auction_probe.py / stockdb schemas.py / test_ifzq / test_provider_chain / test_xyz / test_pool_hub / test_auction_backfill / test_daily_pipeline_refresh)

---

## Verdict: ~~BLOCKED~~ → **EXECUTABLE** (amendments applied 2026-08-07)

**Original:** 1 blocker, 6 warnings, 3 info — blocker: 40-03 Task 2 引用不存在的 `kline_sync.sync_daily` (实际 `sync_and_persist_daily_batch`; RESEARCH 同错)。

**Amendments (orchestrator, evidence-based, commit 待定):**
- **B-1 RESOLVED**: 40-03-PLAN.md 全部 `sync_daily` → `sync_and_persist_daily_batch(symbols, repo, capset, count=...)` (源码核实 kline_sync.py:210 签名); RESEARCH.md repository.py → tickflow/repository.py 路径修正 (:78/:255)。
- **W-1 RESOLVED**: 40-01 T1 verify 去 `| head -3` (grep 退出码不再被掩)。
- **W-2 RESOLVED**: 40-03 T3 verify 去重复 `cd backend`。
- **W-3 RESOLVED**: RESEARCH.md Open Questions Q1/Q2/Q3 全部加 **RESOLVED** 注记 (Q1 恒等 ×1 已修需求文本; Q2 默认链首仅 _BUILTIN_CHAIN; Q3 quotes 旁路 scope out)。
- **W-4 RESOLVED**: 40-03 T1 新增 `test_chain_local_stockdb_heads_minute_gap_merge` (LOCAL-04 分钟链级 gap-merge 用例, 镜像 daily 面)。
- **W-5 RESOLVED**: 40-01 分钟夹具行补 `freq` 字段 (适配器输出形状 symbol/datetime/open/high/low/close/volume/amount/freq)。
- **W-6 NOTED (non-blocking)**: 40-VALIDATION.md — 仓库惯例无此文件 (v2.4 phases 用 VERIFICATION.md/SUMMARY.md/PLAN-CHECK.md); 8a-8d 实质由三文件覆盖, 不新增。

---

## D1 — Goal-backward: 每 success criterion → 可观测验收 (反向无孤儿)

| ROADMAP Success Criterion | 覆盖 Plan/Task | 可观测验收 | 状态 |
|---|---|---|---|
| SC1: `_get_provider("local_stockdb")` lazy 单例; auction=False 不进竞价链 | 40-02 T1; 40-01 T2 | test_get_provider_local_stockdb_returns_singleton (同 id); capabilities 声明 auction=False; auction_probe.py:110 按 `capabilities.auction` 枚举 (已核实源码) | ✅ |
| SC2: config 键 + env 注入; X-API-Key header-only; sleep_between_batches 对齐档位; 429 Retry-After | 40-02 T1; 40-01 T2/T3; 40-03 T3 | config 默认值/env 覆盖断言; `_get_json` 唯一请求面 headers dict; rpm==120 断言; Retry-After 头解析断言; AST 守卫 D (api_key 仅 headers) | ✅ |
| SC3: 三差异契约锁死; 写湖仅经既有路径 | 40-01 T1/T2; 40-03 T2 | symbol=="600519.SH"、volume==42689.0 且 !=4268900.0、date naive + pl.Date; append_daily 冒烟 | ✅ (见 BLOCKER-1 的函数名修正) |
| SC4: daily/minute 链首 gap-merge 经 kline_sync 写路径; 双源守卫沿用; 湖无 provenance; 通道身份进台账 | 40-03 T1/T2 | gap-merge 去重/空帧回退/异常跳过断言; 链首 daily+minute; 幂等写; schema 无 provenance 列; caplog "local_stockdb" 链日志 | ⚠️ (分钟链级合并仅到链位断言, 见 W-5; 写路径冒烟引用错误函数名, BLOCKER-1) |
| SC5: 零新增依赖; hermetic + live 冒烟 | 三 plan | 零新增依赖 (threat T-40-SC N/A); 夹具冻结零网络; live 冒烟环境门控 honest skip | ✅ |

**反向孤儿检查:** 全部 9 任务可回溯到 LOCAL-01..04 / SC1..5 (40-01→LOCAL-01/03, 40-02→LOCAL-02, 40-03→LOCAL-04 + LOCAL-01 AST 复核 + SC5 全量回归)。无孤儿任务。Requirements 覆盖: LOCAL-01✅ 02✅ 03✅ 04✅。

## D2 — 依赖/顺序

- 40-01 (wave 1, `depends_on: []`) → 40-02 (wave 2, `[40-01]`) → 40-03 (wave 3, `[40-02]`): 契约→实现→注册→集成, 顺序正确, 无环, 无前向引用, 与 ROADMAP "Depends on: Nothing" 一致。
- 40-03 T1 的链首/白名单断言依赖 40-02 的注册落地 — 依赖边正确; 40-02 的 chain.py 分支 import stockdb_provider 依赖 40-01 — 正确。
- 40-02 T2 "四处同改单次提交" 防白名单半完成态 — 正确的原子性设计。

## D3 — 风险覆盖 (RESEARCH 遗留逐项)

| RESEARCH 遗留 | PLAN 处理 | 状态 |
|---|---|---|
| Q1 量单位 (需求原稿 ×100 vs 实测恒等 ×1) | REQUIREMENTS LOCAL-03 已修正 ×1; 40-01 夹具锚点 42689.0 + `!= 4268900.0` 双断言锁死 | ✅ |
| Q2 链首插槽行为 (已配置用户链) | 40-02 T3 test_user_chain_override_position_wins: 用户链不自动插链首 (get_provider_chain 已核实: 存储链经 `_sanitize_chain` 保序) | ✅ |
| Q3 quotes 旁路 | 明确出范围, capabilities.realtime=False 诚实声明 (40-01 T2) | ✅ |
| Pitfall 3 分钟端日语义不对称 | 40-01 T2 end+1day; T3 test_minute_end_excludes_end_day 断言 params["end"]=="2026-08-06" | ✅ |
| 批端点 ≤200 分页 (DAILY-02) | chunked(symbols, batch_size=200 参数化) + T3 分批断言 (3 symbols/batch=2 → 2 次调用) | ✅ |
| Pitfall 4 白名单漏注册静默回 tickflow | 40-02 T2 白名单同波提交 + T3 白名单/链首断言 + 40-03 T1 可切换回归锁 | ✅ |
| Pitfall 2 吞错链 (P2 catch-all) | 40-01 T2 禁 except Exception 兜底; typed 异常按状态码; 200+[] 才是真空 | ✅ |
| Pitfall 5 body 跨部署不一致 | 分类只依状态码, body 仅日志; 测试禁断言 body 具体内容 | ✅ |
| Pitfall 6 容器内 127.0.0.1 不通 | 40-03 T3 live 冒烟环境门控 honest skip (记录原因, 不伪造); base_url 可配置 | ✅ |
| Pitfall 7 flush vs merge 双路径 | 40-03 T2 仅走 append_daily merge 路径, 不改 flush 语义, 双路径现状记录 | ✅ |
| ETag/304 (Pattern 3) | RESEARCH 明示 "v1 可不实现"; 适配器不发送条件头 → 304 结构性不可达, 无风险 | ✅ (INFO-1) |

## D4 — 可执行性

- 任务粒度: 3/3/3 任务, 全部含 files/action/verify/done (gsd-tools verify.plan-structure 三 plan 全 valid, 0 error 0 warning)。
- 动作具体性: 达到断言级 (逐测试名 + 断言值 + 注入面); 夹具内容逐字段冻结, 锚点值明示 (42689 / 1306.45 / 2026-08-05T00:00:00+08:00)。
- 验收命令可运行性: 多数 pytest 路径真实存在 (已核实 test_stockdb_provider 为新增、test_local_stockdb_registration 为新增、既有测试文件均存在); **例外见 BLOCKER-1 (函数名) 与 W-3 (重复 cd)**。
- 夹具 hermetic: 冻结 JSON + 注入 fake transport (镜像 test_ifzq_provider.py:16-41 已核实), CI 零网络; live 冒烟环境门控。
- Smart-zone 估算 (estimate-check --calibrated): 40-01 60000 / 40-02 50000 / 40-03 55000 tokens, budget 100000, ratio 0.60/0.50/0.55, 全部 `over_budget: false`; confidence=low (尚无已完工 phase 实际值, 未校准) — 无超预算警告。

## D5 — 回归面

- test_xyz_provider.py:126-137 空帧契约: 零触碰; 40-03 回归清单 `pytest tests/test_xyz_provider.py -x` 保持绿 (已核实该测试存在, 语义=空载荷/异常→空 df 不抛)。
- test_ifzq_provider.py (×100 手→股口径): 零触碰; 回归清单保持绿; 口径不一致为既有隐患, RESEARCH 记录不修, 与计划一致。
- kline_sync 测试 / 链测试: 40-03 T1 仅**扩展** test_provider_chain.py / test_data_source_selection.py (镜像 _FakeProvider 面, 已核实), 既有用例不修改; 回归清单逐项跑。
- test_minute_timestamp_convention.py (naive 契约): 回归清单。
- 零改动门: kline_sync.py / base.py / normalizer.py / repository.py — 40-01 T2 done 复核 + 40-03 T2 verify `git diff --name-only` 空; frontend/src/pages/Watchlist.tsx — 40-03 verification 含 `grep Watchlist` 空门 (本评审亦未读取该文件)。
- 全量回归: 40-03 T3 `pytest tests/ -x`, 失败则记录清单不静默跳过。

## 附加标准维度 (gsd-plan-checker 全维度)

- **结构有效性:** 3 plan `verify.plan-structure` 全 valid; 任务数 3/3/3 (目标 2-3), 文件 6/6/4 (目标 5-8) — 无 scope 超标。
- **must_haves:** 三 plan 均有 truths/artifacts/key_links; truths 为用户可观测断言级, 非实现细节。
- **Context Compliance (D7):** 无 CONTEXT.md → SKIPPED (REQUIREMENTS 定稿文本即锁, 三差异 ×1 已按修正版执行)。
- **Architectural Tier (7c):** RESEARCH Responsibility Map 全部能力归 API/Backend; 三 plan 全部任务落 backend 文件 → PASS。
- **Cross-Plan Data Contracts (D9):** 适配器输出列 ↔ normalize_daily 湖内规范列 (DAILY_COLS 已核实) ↔ append_daily 合并键 (symbol,date) ↔ 湖 parquet 无 provenance 断言 — 各 plan 转换一致, volume 手口径三 plan 同源 → PASS。
- **Pattern Compliance (D12):** PATTERNS.md 映射的 analog 全部真实存在且行号基本吻合 (chain.py:20-27/31-38/62-88/147-179、preferences.py:159、config.py、test_ifzq:16-41、test_provider_chain:24-56、test_pool_hub:951-972、test_auction_backfill:494-527、test_daily_pipeline_refresh:1-40)。**一处刻意偏离 (正向):** health probe 用 `get_daily(["SH600519"])` 而非 RESEARCH/PATTERNS 的 `["000001"]` — 服务端 schemas.py:25 正则 `^(SH|SZ|BJ)\d{6}$` 要求前缀形态, 裸码会 400 误报 error, plan 修正正确。
- **CLAUDE.md (D10):** 无 CLAUDE.md → SKIPPED。
- **Verify 命令格式 (#1478/#1479):** 无 `2>/dev/null || echo` 喂比较、无 `^` 锚定包管理输出 grep; 数值断言 (42689/1306.45/267 行) 均溯源 RESEARCH live 实测 (provenance 在案)。仅 40-01 T1 的 `| head -3` 掩盖 grep 退出码 (W-4)。
- **Research Resolution (D11):** 三开放问题实质均已闭环并被 plan 采纳 (Q1→REQUIREMENTS 修正, Q2→40-02 T3 测试, Q3→出范围声明), 但文件缺少 (RESOLVED) 标记 (W-2)。
- **Nyquist (D8):** 40-VALIDATION.md 缺失 (W-1); 8a-8d 实质检查全过 — 每任务均有 `<automated>` pytest 命令、无 watch 模式、采样连续性 3/3 全验证、无 MISSING 标记。

---

## Blockers (must fix)

**1. [executability] 40-03 Task 2 引用不存在的 `kline_sync.sync_daily` — 写路径冒烟无法照写**
- Plan: 40-03, Task 2
- 证据: `backend/app/services/kline_sync.py` 无 `def sync_daily(` (全库 grep 核实)。实际写路径入口是 `sync_and_persist_daily_batch(symbols, repo, capset, count=..., start_date=..., end_date=...)` (kline_sync.py:210-268), 其内部即 `_build_chain("daily")` → `fetch_with_chain` → `repo.append_daily(merged)` → 返回行数 — 与 plan 意图完全吻合但函数名/参数不同 (需 repo: KlineRepository + capset: CapabilitySet)。RESEARCH.md "kline_sync.py:225-254 (sync_daily → …)" 同样错名, plan 继承之。
- 影响: LOCAL-04 的核心可观测 (写路径冒烟) 首跑即 AttributeError; executor 需自行考古真实 API, 或降级成绕过 append_daily 的弱测试。
- Fix: 40-03 T2 改为 `kline_sync.sync_and_persist_daily_batch(symbols, repo, capset, count=...)`, 用 test_daily_pipeline_refresh 配方的 tmp_path 真 repo + 空 `CapabilitySet()`; 或直接 `chain.fetch_with_chain("daily", fetch, providers=["local_stockdb"])` + `repo.append_daily(merged)`。同步修正 RESEARCH.md 同错函数名 (审计溯源)。

## Warnings (should fix)

**1. [nyquist] 40-VALIDATION.md 缺失 (Dimension 8 gate; 本版 gsd-core W009)**
- 证据: phase 目录无 `*-VALIDATION.md`; RESEARCH.md 含完整 "## Validation Architecture" (Test Framework / Req→Test Map / Sampling Rate / Wave 0 Gaps), plan-phase 应据此生成 VALIDATION.md 且缺失时 STOP。本版 gsd-core 的 verify.cjs/health.md 将同条件归类为 **W009 warning** (非 blocker); 且 8a-8d 实质全过 (每任务均有 automated 命令) → 按 WARNING 处理, 不阻塞目标达成。
- Fix: `/gsd-plan-phase 40 --research` 重新生成 40-VALIDATION.md (或执行后由 `/gsd:validate-phase` State B 生成)。执行期 Nyquist 采样以 RESEARCH §Validation Architecture + 各 plan `<automated>` 为准。

**2. [research_resolution] RESEARCH.md "## Open Questions" 缺 (RESOLVED) 标记**
- 三问题实质均已闭环并被 plan 采纳 (Q1: REQUIREMENTS LOCAL-03 已修正 ×1, 契约断言锁定; Q2: 40-02 T3 test_user_chain_override_position_wins; Q3: realtime=False 出范围声明), 但文件头与各问无 RESOLVED 标注, 审计痕迹陈旧。
- Fix: RESEARCH.md 节标题改 `## Open Questions (RESOLVED)` 并在 Q1/Q2/Q3 补行内 RESOLVED 说明 (引用 REQUIREMENTS 修正行 / plan 测试名)。

**3. [executability] 40-03 T3 verify 命令重复 `cd backend`, 第二次 cd 失败中断全量回归**
- 原文: `cd backend && pytest tests/test_stockdb_provider.py -x && cd backend && pytest tests/ -x` — 第二条 `cd backend` 已在 backend 内执行 → "No such file or directory" → 全量套件永不运行, verify 假失败。
- Fix: 删除第二个 `cd backend` (或先 `cd ..`)。

**4. [executability] 40-01 T1 verify 管道 `| head -3` 掩盖 grep 退出码 → 红态检查空洞**
- `pytest … | grep -E … | head -3` 的管道退出码恒为 head 的 0, grep 未命中也 pass → 无法区分"红态正确"与"误绿"。
- Fix: 改用 `grep -qE "ImportError|ModuleNotFoundError"` 直接以 grep 退出码判据 (或断言 pytest 退出码 != 0 且输出含 ImportError)。

**5. [requirement_coverage] LOCAL-04 分钟旁路只验证到链位断言, 无 fetch_with_chain("minute") 链级合并用例**
- 40-03 T1 仅对 "daily" 做 gap-merge 合并用例; minute 侧只断言 `chain_for("minute")[0]=="local_stockdb"` + 适配器级分钟契约 (end+1day / naive)。LOCAL-04 明示 "daily/minute 流经新通道进链首 gap-merge"。
- Fix: 40-03 T1 加一个 `fetch_with_chain("minute", get_minute)` 用例 (镜像 test_chain_merges_gaps_across_sources, _FakeProvider 已带 get_minute), 或明示分钟湖为空 (A2) 故链级分钟合并仅到机制共享 + 链位断言。

**6. [fixture_fidelity] 40-01 T1 分钟夹具行缺 `freq` 字段, 与 live MinuteBar 形状不符**
- 证据: stockdb schemas.py MinuteBar 含 `freq: int` (1|5|15|30|60) + SourceStamp (source/fetched_at/schema_version); plan 夹具行只含 symbol/bar_time/OHLC/volume_hand/amount_yuan。适配器 freq 列取自请求串 (不读响应), 测试仍绿, 但违反 must_haves truth "夹具冻结 live 实测体" 的保真度。
- Fix: 分钟夹具行补 `"freq": 1` (+ SourceStamp 字段), 与 DailyBar 夹具同保真度。

## Info (suggestions)

1. ETag/304: RESEARCH 已明示 v1 可不实现; 适配器不发 If-None-Match → 304 结构性不可达。可在 plan 注明以闭环审计。
2. 40-02 T3 settings builtin 测试 action 中 "monkeypatch settings_api.settings 局部替换 base_url?" 有不确定性措辞 — 实测 list_data_sources 函数内 `from app.config import settings`, monkeypatch 模块属性无效; 计划已给 fallback (断言与 app.config.settings.local_stockdb_url 相等), 建议直接删掉 "?" 分支只留 fallback。
3. 40-01 T1 `_JsonTransport` 路由键形状 (url+params 分离 vs RESEARCH 骨架 "path?query") 由 executor 定夺; 建议 action 注明按 (url, params) 匹配以避免骨架歧义。

---

## 结论

计划整体质量高: goal-backward 覆盖完整、风险逐项闭环、注册原子性设计正确、回归面明确、hermetic 纪律一致、估算全在预算内。唯一 blocker 是函数名错引 (40-03 T2 + RESEARCH 同错), 修正后即可执行。

**修复路径:** 改 40-03 T2 入口为 `sync_and_persist_daily_batch(symbols, repo, capset, count=...)` (或直接 fetch_with_chain+append_daily), 顺带修正 RESEARCH 函数名 → 返回 planner 修订 1 处 → 复验。
