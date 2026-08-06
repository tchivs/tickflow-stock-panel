# 盘前预览 × 监控告警引擎 — v2.2 research

**研究问题:** v2.1 盘前预览股池 (`premarket_results`) + 竞价列能否喂给监控告警规则引擎 (4 类规则 → alerts → Feishu), 构成"盘前异动 / 竞价强度"告警。

**结论:** **可行 (YES)** — 推荐新增统一引擎下的 `preopen` 规则类型 + 专用 `evaluate_premarket()` 入口 + 09:26 预览 job 尾段接线。复用现有 DataFrame 条件匹配 / cooldown / 持久化 / SSE / 飞书投递全链路, 零执行权限、诚实 provisional 标注、与 15:30 EOD 管道及盘中监控零碰撞。

---

## 现状 (current state with code anchors)

### 1. 监控规则引擎 (4 类规则 + ladder + position)

- **规则存储/校验:** `backend/app/strategy/monitor_rules.py`
  - `RULE_TYPES = {"strategy", "signal", "price", "market", "ladder", "position"}` (`:29`)
  - `validate()` (`:101`) 按 type 分支校验; `normalize()` (`:203`) 补默认字段。
  - 规则持久化 `user_data/monitor_rules/{rule_id}.json` (`:48-55`)。
- **引擎:** `backend/app/strategy/monitor.py` `class MonitorRuleEngine` (`:329`)
  - `evaluate(df: pl.DataFrame, asset_type="stock", reset_strategy_results=True)` (`:497`) — 输入是**实时 enriched 行情 DataFrame**, 按 `asset_type` 过滤规则。
  - `_evaluate_rule` (`:617`) 按 `rule["type"]` 分派: `strategy` → `_match_strategy` (跑策略选股 + **池 diff**), `ladder` → 封单, 其余 (signal/price/market) → `_match_conditions` (`:903`, 经 `_build_condition_mask` 按 `conditions + logic` 过滤)。
  - cooldown 去重 key = `(rule_id, symbol)` (`_last_fire`, `:617-661`); 批量事件用 `(rule_id, _<ev_type>_batch)`。
  - `_strategy_pools: dict[(sid, asset_type), set[symbol]]` 是策略池 diff 的内存基线, `_latest_strategy_results` 供 `/api/screener/cached` 回显。
- **评估触发点 (关键!):** `backend/app/services/quote_service.py`
  - `_is_continuous_trading()` (`:1146-1160`) 严格限定 **9:30-11:30 / 13:00-15:00 工作日连续竞价** — 集合竞价指示价 (9:15-9:30)、午休、收盘缓冲一律不评估监控。
  - `_evaluate_monitors()` (`:1169-1353`) 只在此窗口内跑: `engine.evaluate(df, asset_type="stock")` → ETF 轮 → position 轮 → `operational.record_alert_event()` (`:1266`, 落 SQLite `alert_events`, 持久化优先) → `_broadcast_alerts()` (SSE) → `_maybe_send_webhook()` (`:1356`, 飞书/Telegram 经 `notifications/delivery.py`)。
  - **没有"15:30 监控评估"** — 15:30 是 EOD 数据管道 (`daily_pipeline._pipeline_then_refresh`: 日K同步 + enriched + 视图刷新), 监控引擎不参与。
- **告警读取:** `backend/app/api/alerts.py:18-46` — 优先 `operational.list_alert_events` (SQLite), 未初始化才回退 `alert_store.list_recent` (`alerts.jsonl`)。
- **规则 API:** `backend/app/api/monitor_rules.py` — `RuleModel` (`:59`), `/options` (`:82-143`) 下发 `threshold_fields` (来自 `ALLOWED_FIELDS`)、`types`、`scopes`、`operators`。

### 2. 盘前预览 (v2.1, PM-01)

- **Job:** `backend/app/jobs/daily_pipeline.py`
  - 常量 `_PREMARKET_JOB_ID = "premarket_pool_preview"`, 固定 **09:26** (mon-fri, Asia/Shanghai, `:966-970`), `scheduler.add_job` (`:1145-1153`), `misfire_grace_time=1800`。
  - `_premarket_pool_preview()` (`:1017-1061`): 复用 `ScreenerService.run_all_with_hits(as_of=T)` → `build_premarket_preview` → `persist_premarket_snapshot` → `premarket_results/date={T}/part.json`。**绝不写** `strategy_cache` / `screener_results` (PM-01 铁律)。
- **服务:** `backend/app/services/premarket_pool.py:30` `build_premarket_preview()` — payload 含 `window:"pre_open"` / `computed_at` / `provisional:true` / `degraded` / `probe` / `strategy_version` / `results` (dict: `{sid: {total, as_of, rows}}`, 行含 `open_gap`/`change_pct`/`auction_*`/`hit_factors`/`name`/`symbol` 等)。空结果 → `available:false, degraded:true` 诚实空态。
  - `backend/app/services/premarket_snapshot.py` `persist_premarket_snapshot` (`:48`, 原子写 + 路径穿越防护 `_DATE_RE`) / `load_premarket_snapshot` (`:83`) / `list_premarket_dates` (`:101`)。
- **API:** `backend/app/api/pool.py:118-176` `GET /api/pool/premarket` — 只读 (POOL-03 零执行), 固定今日, `_project_hub` 投影 (`services/pool_hub.py:83-188`) + `window/provisional/degraded/probe` 透传 + `mask_guest_hub` (`services/guest_masking.py:20`, 身份掩码 + 剥离 `open_gap`/`auction_*`)。
- **竞价列:** `backend/app/services/auction_columns.py:90-131` `attach_auction_columns` — **probe×分区双闸门**: `resolve_auction_probe().status == available` 且 `kline_auction/date={T}` 有行才注入 `auction_volume`/`auction_amount` (real) + 派生 `auction_volume_ratio`/`auction_unmatched_amount` (derived); 任一闸门不过 → 列缺席 (诚实缺列, 绝不 0 填/派生兜底)。pre_open 策略集 (`strategy/builtin/auction_*`, `t1_flash`) 消费这些列, 缺列 → 空池 (fail-closed)。

### 3. 关键错位 (现状 gap)

| 维度 | 监控引擎 | 盘前预览 |
|---|---|---|
| 输入 | 实时 enriched **DataFrame** (`evaluate(df)`) | **JSON payload** (`{sid: {total, as_of, rows}}`) |
| 时间窗口 | 仅连续竞价 9:30-15:00 | 09:26 单次 job |
| 字段 | `ALLOWED_FIELDS` (含 EOD 列 `change_pct`/`close`/`vol_ratio_5d`) | pre_open 白名单 (禁 EOD 列) |
| 语义 | 盘中价格/信号 | provisional (开盘前非最终) |

→ 引擎**不能**直接 `evaluate(premarket_results)` (输入形状不同), 但 `_match_conditions` / `_build_condition_mask` / cooldown 的**匹配机制可复用**, 只需新增输入适配 + 调度入口。

---

## 方案选项 (2-3 options with tradeoffs)

### 选项 A: 统一引擎新增 `preopen` 规则类型 (推荐)

**做法:** `RULE_TYPES` 增加 `"preopen"`; `MonitorRuleEngine` 新增 `evaluate_premarket(payload) -> list[dict]` — 把 `payload.results` 全部策略 rows 抽 symbol 去重建 Polars DataFrame (列: `symbol`/`name`/`open_gap`/`auction_volume`/`auction_amount`/`auction_volume_ratio`/`auction_unmatched_amount`/`hit_factors`/`source_strategies`; `change_pct` 置 None 诚实缺列), 复用 `_apply_scope`/`_build_condition_mask`/`_match_conditions` + `_last_fire` cooldown, 事件携带 `window=pre_open` / `provisional=true` / `degraded` / `probe`。调度: `_premarket_pool_preview` 尾段 (同一 `_run_tracked` 单飞内, persist 之后) 调 `_evaluate_premarket_alerts(app_state, payload)`, 复用 `quote_service._evaluate_monitors` 的持久化/SSE/飞书序列。

**优点:**
- 单一规则引擎 + 统一告警管线 (operational 持久化 → SSE → 飞书), 用户可配、可 cooldown、可 severity。
- 零 EOD/盘中污染: 独立 source、独立 eval 入口、不触碰 `_strategy_pools`/`_latest_strategy_results`。
- 诚实 provisional 结构化强制: payload 元数据直接进事件字段。
- 零执行: 只读 premarket_results, 不写 strategy_cache/screener_results (PM-01 铁律延续)。
- 竞价列 fail-closed 天然成立: 列缺席 → `_build_condition_mask` 无命中 → 不告警。

**缺点:**
- 引擎耦合中等: 新增 rule type + validate/normalize 分支 + eval 入口 + API options + 前端类型 (5 处)。
- 需在 `_premarket_pool_preview` 尾段接线, 或在 daily_pipeline 加第二个 job (09:27) — 推荐尾段避免竞态。

### 选项 B: 复用现有 type=strategy 路径指向盘前行

**做法:** 让 type=strategy 规则消费 premarket rows (把预览池当"当前选股池"跑 diff 或条件)。

**缺点 (否决):**
- `_match_strategy` (`monitor.py:736`) 会**重跑策略引擎** (`engine.run(sid, precomputed=df)`) — 09:26 帧与盘中帧不同, 结果可能与预览 payload 漂移; 且 `strategy_cache`/`screener_results` 铁律禁止把预览帧喂选股缓存。
- **`_strategy_pools[(sid, at)]` 池 diff 基线污染**: 09:26 把预览池写入 `prev_pool`, 09:30 盘中首轮 diff 会把"预览有、开盘后无"的股票当作 `dropped` 触发伪"移出"告警 (反之 `new_entry`) — 正是要避免的 EOD/盘中污染。
- 语义错配: strategy 规则语义是"新入选/移出" (new_entry/dropped), 盘前想要的语义是"出现在预览 + 竞价强度阈值命中", 两者不是同一概念。
- 结论: **复用路径会污染盘中的策略池基线, 否决。**

### 选项 C: 独立盘前告警 hook (不接规则引擎)

**做法:** 在 daily_pipeline 尾段写一个独立函数, 读 payload, 用少量硬编码阈值 (open_gap/auction_volume_ratio) 直接 `alert_store`/投递。

**优点:** 实现最快、引擎零耦合。

**缺点 (否决):**
- 绕过统一规则 schema/UI — 用户无法配置/开关/设 severity/cooldown。
- 第二套"监控范式"与告警格式、持久化路径重复, 长期与 `operational.alert_events` 分叉 (如 `alert_store.jsonl` 旧路径)。
- 硬编码阈值 = 产品化死路, 违背"决策闭环"目标 (用户可配置是闭环的前提)。
- 结论: **作为 v2.2 临时垫片可接受, 但作为目标方案否决。**

---

## 推荐方案

**选项 A — 统一引擎 `preopen` 规则类型 + `evaluate_premarket()` + 09:26 预览 job 尾段接线。**

**Why:**
1. **复用最大化, 分叉最小化**: 条件匹配/cooldown/scope/持久化/SSE/飞书全部现成, 只新增"输入适配 + 调度入口"。
2. **零污染**: 独立 `source=preopen`、独立 eval 入口、不碰 `_strategy_pools`, 与 09:30+ 盘中监控互不干扰。
3. **诚实性结构化**: `provisional=true`/`degraded`/`probe` 从 payload 直通事件, 前端可展示"盘前非最终"徽标; 竞价列缺失 → fail-closed 不告警 (诚实缺列, 绝不 0 填/派生兜底)。
4. **零执行与铁律延续**: 评估只读 premarket_results, 不写 strategy_cache/screener_results, 不 import 执行族 — 与 PM-01/POOL-03 一致。

**调度设计 (关键决策):**
- 在 `_premarket_pool_preview` **尾段** (persist 之后, 同一 `_run_tracked` 单飞内) 调 `_evaluate_premarket_alerts(app_state, payload)` — 内存直接拿 payload, 免二次读盘、免新增 job 的调度依赖/竞态。
- 若希望"预览失败也可独立补跑告警", 可退化为独立 09:27 job (`_PREMARKET_ALERT_HOUR, _MINUTE = 9, 27`, `misfire_grace_time=600`) 经 `load_premarket_snapshot` 读盘 — 二选一, 推荐尾段。
- **时间碰撞检查**: 09:26/09:27 与 15:30 EOD 管道 (`daily_pipeline`) 相隔 ~6h, 无碰撞; 与 09:30+ 连续竞价监控 (`_is_continuous_trading`) 不重叠; 与 09:26 预览 job 本身由 `_run_tracked` 单飞保证不并发。共享资源 (operational.db / SSE 队列 / delivery 队列) 均为线程安全追加, 无冲突。
- **cooldown 域**: preopen 规则用独立 rule_id, cooldown key `(rule_id, symbol)` 与盘中规则天然隔离 — 盘前命中不会压制盘中同规则。

**诚实边界 (必须遵守):**
- `change_pct`/`close`/`vol_ratio_5d`/`amount` 等 EOD 列在 09:26 无意义 (pre_open 策略明确禁 EOD 列), preopen 规则**白名单只允许** `open_gap`/`auction_volume`/`auction_amount`/`auction_volume_ratio`/`auction_unmatched_amount`; 评估 DataFrame 中 `change_pct` 置 None 兜底 fail-closed。
- degraded=true 或 probe 非 available → 竞价列依赖规则自然无命中 (不告警), 但**不静默**: 事件/UI 透传 degraded 状态, 用户可理解"为什么没报"。
- 游客脱敏: preopen 告警经任何游客可见表面渲染时身份掩码 + 剥离 open_gap/auction_* (复用 `mask_guest_hub`); 飞书为所有者通道不受 guest 掩码约束。

---

## 需求草案 (MON-0x: verifiable requirement drafts)

### MON-01 — 新增 `preopen` 规则类型 (schema/校验/规范化)
- `RULE_TYPES` (`monitor_rules.py:29`) 增加 `"preopen"`。
- `validate()` 增加分支: type=preopen 必须有 `conditions` (1-8 条); `op` 仅 `OPS` (阈值比较), **禁止 `op=truth`** (pre-open 无布尔信号列); 阈值 `field` 必须落在 pre-open 白名单 `{"open_gap", "auction_volume", "auction_amount", "auction_volume_ratio", "auction_unmatched_amount"}`; 白名单外 (如 `change_pct`/`close`/`vol_ratio_5d`/`amount`) 抛 `ValueError` (镜像 builtin pre_open 策略禁 EOD 列)。
- `scope` 仅 `symbols`/`all` (sector 可后续); `normalize()` 补默认 (severity 默认 `info`, cooldown 默认 600)。
- **验证:** 单测构造 preopen 规则: 合法字段保存成功; `field=change_pct` / `op=truth` 抛 `ValueError`; 缺 conditions 抛错。

### MON-02 — `MonitorRuleEngine.evaluate_premarket(payload)` 入口
- 新增方法: 从 `payload["results"]` 全部策略 rows 抽 `symbol` 去重构建 Polars DataFrame (列: `symbol`/`name`/`open_gap`/`auction_volume`/`auction_amount`/`auction_volume_ratio`/`auction_unmatched_amount`/`hit_factors`/`source_strategies`; `change_pct` 一律置 None)。
- 只评估 enabled 且 `type=preopen` 规则; 复用 `_apply_scope` / `_build_condition_mask` / `_match_conditions` / `_last_fire` cooldown。
- 事件字段: `source="preopen"`、`type="preopen"`、`window="pre_open"`、`provisional=True`、`degraded=payload.get("degraded")`、`probe=payload.get("probe")`、`strategy_ids=[命中的盘前策略 sid]`。
- **绝不触碰** `_strategy_pools` / `_latest_strategy_results` / `_building_strategy_results` (与盘中隔离)。
- **验证:** 单测注入构造 payload: 断言事件字段 (provisional/degraded/probe/source)、cooldown 生效、`_strategy_pools` 为空、`latest_strategy_results()` 不变。

### MON-03 — 调度接线 (09:26 预览 job 尾段)
- `_premarket_pool_preview` (`daily_pipeline.py:1017`) persist 之后调用 `_evaluate_premarket_alerts(app_state, payload)`; 同一 `_run_tracked` 单飞内, 不新增并发 job。
- `_evaluate_premarket_alerts` 复用 `quote_service._evaluate_monitors` 的持久化/广播/投递序列: `operational.record_alert_event` → `_broadcast_alerts` (SSE) → `_maybe_send_webhook` (飞书); `operational` 未初始化则降级 `alert_store.append_many` + 跳过投递 (镜像 `:1266-1271`)。
- 预览 `available:false` → 不评估、不告警 (诚实空态)。
- **验证:** fixture 模式集成测试: 注入内存 payload → 断言 `alert_events` 表新增记录、投递队列入队; 断言与 15:30 `daily_pipeline` job 定义无时间重叠。

### MON-04 — 诚实 provisional / degraded 标注
- 每个 preopen 事件携带 `window/provisional/degraded/probe`; 前端告警记录 (alerts 页) 对 `source=preopen` 展示"盘前·非最终"徽标。
- `degraded=true` 或 probe 非 available: 依赖竞价列的规则 fail-closed 无命中 (绝不 0 填/派生兜底); 事件不产生, 但 UI 透传 degraded 状态。
- **验证:** 构造 `degraded=true` payload + 竞价列规则 → 0 事件; 非 degraded → 命中且事件含 `provisional=true`。

### MON-05 — 零执行 / 存储隔离
- preopen 评估只读内存 payload 或 `load_premarket_snapshot`; **绝不**调 `strategy_cache.write_cache` / `pool_snapshot.persist_point_snapshot` / 写 `screener_results`; 不 import 执行族模块 (broker/order/trade/execution/portfolio/position/account/transaction) 与 `strategy_cache`。
- **验证:** AST 守卫测试 (镜像 `tests/test_pool_hub.py` E3 形) 锁定 preopen 评估模块的 import 白名单。

### MON-06 — 游客脱敏边界
- preopen 告警经任何游客可见表面 (SSE / alerts 历史页) 渲染时, `symbol`/`name`/`code` 掩码为 `******` 且剥离 `open_gap`/`auction_*` (复用 `mask_guest_hub` 语义, `guest_masking.py:20`); 飞书/Telegram 为所有者通道不受 guest 掩码约束。
- **验证:** 快照测试断言 guest 可见字段集合不含 `open_gap`/`auction_*`/身份。

### MON-07 — 规则 API / 前端选项
- `/api/monitor-rules/options` (`api/monitor_rules.py:82`) `types` 增加 `{"key": "preopen", "label": "盘前异动"}`; 下发 `preopen_threshold_fields` (白名单字段 + 中文标签, 复用 `ENRICHED_COLUMNS` 语义); `operators` 沿用。
- 前端规则编辑器: preopen 类型展示白名单字段下拉 + conditions 复用现有组件 (镜像 signal/price 表单)。
- **验证:** `GET /api/monitor-rules/options` 返回含 preopen 类型与白名单字段; 前端组件测试渲染。

---

## 风险 / 开放问题

| # | 风险 | 级别 | 缓解 |
|---|------|------|------|
| R1 | **change_pct 口径**: 09:26 pre-open enriched 帧的 `change_pct` 语义未直接核实 (可能=0 或=open_gap)。若前端/规则误用会产生误导告警。 | 高 | MON-01 白名单禁 EOD 列; MON-02 DataFrame 置 None; 实施时需核实 pre-open 帧计算口径 `[INFERENCE]`。 |
| R2 | **告警噪音/重复**: 盘前命中 + 开盘后同股同策略盘中命中, 用户可能觉得重复。 | 中 | preopen 规则默认 `severity=info` + 独立 cooldown; 前端徽标区分 pre_open/盘中。 |
| R3 | **degraded 时"静默不报"**: 用户困惑为何没告警。 | 中 | 盘前页已有 degraded 状态; alerts 页可显示 preopen 未触发原因 (开放问题: 是否落"未触发日志")。 |
| R4 | **选项 B 的池基线污染** 若被误采。 | 高 | 本方案已否决 B; roadmap 需明确禁止 type=strategy 指向盘前行。 |
| R5 | **probe 状态变化**: 09:26 probe available 但 09:30 变化 (kline_auction 补写) — 预览是 09:26 冻结, 不回溯。 | 低 | 事件携带冻结 probe 快照; 预览语义即"当时快照"。 |

**开放问题:**
1. pre-open enriched 帧 `change_pct`/`close` 的具体计算口径 (需实施时读 `indicators/pipeline.py compute_enriched_today` + quote_service preopen flush 确认)。
2. preopen 规则是否支持 `scope=sector` (板块 JOIN 已实现, 可复用, 但白名单字段需同步)。
3. 是否需要在 alerts 历史页对 `source=preopen` 做"预览基线 vs 实际开盘"对比 (决策闭环价值, 属 v2.2 后续或 v2.3)。
4. 与 ResearcherRecap/ResearcherConcept 的衔接: 盘前异动告警是否直接喂复盘 (recap) 或概念共振 (concept) 待跨研究确认。

---

## 关键锚点 (exact files/symbols/lines for planning)

| 目标 | 文件 | 符号 / 行 |
|---|---|---|
| 规则类型集合 | `backend/app/strategy/monitor_rules.py` | `RULE_TYPES` `:29`; `validate` `:101-201`; `normalize` `:203-241` |
| 引擎入口 | `backend/app/strategy/monitor.py` | `MonitorRuleEngine` `:329`; `evaluate` `:497`; `_evaluate_rule` 分派 `:617-700`; `_match_conditions` `:903`; `_strategy_pools` 污染点 `:736-900` |
| 盘中评估触发 (连续竞价门控) | `backend/app/services/quote_service.py` | `_is_continuous_trading` `:1146`; `_evaluate_monitors` `:1169-1353`; `operational.record_alert_event` `:1266`; `_broadcast_alerts`; `_maybe_send_webhook` `:1356` |
| 盘前 job | `backend/app/jobs/daily_pipeline.py` | `_PREMARKET_JOB_ID/_HOUR/_MINUTE` `:966-970`; `_premarket_pool_preview` `:1017-1061`; `scheduler.add_job` `:1145-1153`; `_run_tracked` 单飞 `:723` |
| 盘前 payload 构造 | `backend/app/services/premarket_pool.py` | `build_premarket_preview` `:30-100` (window/provisional/degraded/probe) |
| 盘前存储 | `backend/app/services/premarket_snapshot.py` | `persist_premarket_snapshot` `:48`; `load_premarket_snapshot` `:83`; `_DATE_RE` `:31` |
| 竞价列注入 (probe×分区双闸门) | `backend/app/services/auction_columns.py` | `attach_auction_columns` `:90-131` |
| 盘前 API / 投影 / 脱敏 | `backend/app/api/pool.py` | `GET /premarket` `:118-176`; `services/pool_hub.py:_project_hub` `:83-188`; `services/guest_masking.py:mask_guest_hub` `:20` |
| 告警持久化 / 读取 | `backend/app/operational/repository.py` | `record_alert_event` `:345-391`; `api/alerts.py:list_alerts` `:18-46` |
| 规则 API / 选项 | `backend/app/api/monitor_rules.py` | `RuleModel` `:59`; `/options` `:82-143` |
| 引擎装配 | `backend/app/main.py` | monitor_engine 装配 `:625-703` |
| pre_open 策略集 (白名单参照) | `backend/app/strategy/builtin/` | `auction_allround.py:10`, `auction_alpha.py:17`, `auction_fast_grab.py:16`, `t1_flash.py:10` (禁 EOD 列, 缺列空池) |
