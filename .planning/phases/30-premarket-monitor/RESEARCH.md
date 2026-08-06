# Phase 30 盘前监控告警 (MON-01..07) — RESEARCH.md

**Phase:** 30-premarket-monitor (v2.2, 决策闭环)
**Researched:** 2026-08-06
**Researcher:** ResearcherP30
**Mode:** ecosystem (phase-implementation feasibility)
**Inputs:** `.planning/research/v2.2-decision-loop/MONITOR-PREOPEN.md` (领域研究, 选项 A), `.planning/research/v2.2-decision-loop/SUMMARY.md` (Phase 30 段)
**Overall confidence:** HIGH — 全部锚点本次直接实读源码; 唯一残余不确定项 = 09:26 pre-open enriched 帧 `close` 的精确取值来源 (live API 行为, [INFERENCE], 见 §10 R1)

---

## 1. 现状 (verified anchors, 2026-08-06 实测)

### 1.1 规则存储 / 校验 / 规范化 (`backend/app/strategy/monitor_rules.py`)

- `RULE_TYPES = {"strategy", "signal", "price", "market", "ladder", "position"}` (`:29`) — **preopen 需新增**。
- `validate(rule)` (`:101-201`) 按 type 分支:
  - `strategy` → 需 `strategy_id` + `direction`; `ladder` → `metric`/`threshold`/`direction(up/down)`。
  - 其余 (signal/price/market) → `conditions` 1-8 条; `op` 二选一:
    - `op == "truth"` → `field` 必须 `signal_`/`csg_` 前缀 (`_is_signal_field`, `:96-99`) — **布尔信号列**。
    - `op in OPS` (`{">", ">=", "<", "<=", "==", "!="}`) → `field` 必须 ∈ `ALLOWED_FIELDS` (`custom_signals.py:34-56`) 且 `value` 为数字。
  - `scope` ∈ `SCOPES = {"symbols", "all", "sector", "positions"}`; `symbols` 非空列表; `sector` 需非空板块名/列表 (fail-closed 拒绝空板块); `position` 规则强制 `scope=positions`。
  - 其余枚举: severity (info/warn/critical)、cooldown_seconds ≥ 0、active_time_start/end 成对、bypass_quiet_period bool、webhook_channels ∈ {feishu, telegram}。
- `normalize(rule)` (`:203-241`) 补默认: enabled/asset_type/scope/symbols/position_ids/sector/strategy_id/direction/conditions/logic/cooldown_seconds=3600/severity=info/message/webhook_channels (webhook_enabled 旧字段兼容, wecom 定向剥离)。
- 持久化: `user_data/monitor_rules/{rule_id}.json` (`:48-55`); operational repo 另有 `monitor_rules` 表镜像 (`repository.py:329-344`)。

### 1.2 引擎 (`backend/app/strategy/monitor.py`)

- `class MonitorRuleEngine` (`:329`), 构造参数 `alert_handler`/`clock`; 主程序装配 `MonitorRuleEngine()` **不传 handler** (`main.py:627`) → 事件由调用方 (quote_service) 收集后统一持久化/广播。
- 状态: `_rules` / `_last_fire: dict[(rule_id, symbol), float]` (cooldown, `:352`) / `_name_map` / `_strategy_pools: dict[(sid, asset_type), set[symbol]]` (盘中池 diff 基线, `:360`) / `_latest_strategy_results` / `_building_strategy_results` / `_board_loader` / `_history_loader*`。
- `evaluate(df, asset_type="stock", reset_strategy_results=True)` (`:497-560`): 遍历规则 → 跳过 `type=="position"` 或 asset_type 不匹配 → `_evaluate_rule(df, rule, now)`。**关键: 当前对 `type=preopen` 无跳过逻辑 → 会落入 `_evaluate_rule` 的 else 分支 (通用条件匹配) 在盘中求值 — 必须在 evaluate 入口显式跳过 preopen (见 §4)。**
- `_evaluate_rule(df, rule, now)` (`:617-700`): ① `_apply_scope` 过滤; ② 按 type 分派 (`strategy`→`_match_strategy`, `ladder`→`_evaluate_ladder`, 其余→`_match_conditions`); ③ cooldown 去重 (key=`(rule_id, symbol)`, 批量事件 key=`(rule_id, _<ev_type>_batch)`); ④ 事件构建: `id/ts/occurred_at/rule_id/rule_name/source(=rtype)/type(=ev_type)/symbol/name/message/price/change_pct/signals/severity/conditions/logic`; ⑤ `self._alert_handler(ev)` (本例为空)。
- `_apply_scope` (`:704-739`): `all` 原样; `symbols` 按 `pl.col("symbol").is_in(syms)` 精确匹配 (符号带交易所后缀格式, 与盘中规则一致); `sector` 经 `_board_loader` join, 未注入/未匹配 → `df.head(0)` fail-closed; 未知 scope 原样返回 (validate 已挡)。
- `_match_strategy` (`:736-900`): 跑策略选股 (`self._strategy_engine.run(sid, precomputed=df)`) → 写 `_building_strategy_results` → 池 diff (`_strategy_pools`) → `new_entry`/`dropped` 事件 (单只或 >5 只批量)。**这是池基线污染点 (选项 B 否决原因); preopen 评估绝不触碰。**
- `_match_conditions(df, rule)` (`:903-930`): `_build_condition_mask(df, conditions, logic)` → 命中行 `(symbol, name, price=row.get("close"), pct=row.get("change_pct"), hit_sigs)`。
- `_build_condition_mask` (模块级, `:281-303`): **字段不在 df.columns → `df.head(0)` fail-closed** (诚实缺列); `truth` → `fill_null(False)`; 数值比较经 `_OP_BUILDERS` (`custom_signals.py:58-63`)。
- `_default_message` (`:1005-1078`): strategy/ladder 专属文案; signal/price/market → `_format_conditions_text` 条件摘要 + 现价/涨跌幅 (price/pct None 时省略)。
- `set_rules/add_rule/remove_rule/clear`、`has_rule_type(rtype)` (`:481-491`, preopen 无需改动即可复用)、`has_asset_rules`、`latest_strategy_results()`/`consume_strategy_result_updates()`。

### 1.3 盘中评估触发 (`backend/app/services/quote_service.py`)

- `_is_continuous_trading()` (`:1146-1160`): 严格 9:30-11:30 / 13:00-15:00 工作日。`_evaluate_monitors` 首段 gate (`:1173-1176`): 非 `PHASE1_FIXTURE_MODE` 且非连续竞价 → 直接 return; 另有 `enriched_date == cn_today()` 新鲜度判据 (`:1182-1185`)。**09:26 不在连续竞价窗口 → 盘中监控天然不评估; preopen 评估与盘中互不干扰。**
- `_evaluate_monitors(daily_df, quote_extra)` (`:1169-1353`): enriched → name_map 预构建 (`:1193-1213`) → ladder 封单注入 (`_inject_sealed_vol`) → `engine.evaluate(eval_df, asset_type="stock")` → ETF 轮 (`reset_strategy_results=False`) → position 轮 (`evaluate_positions`) → **持久化优先**: `operational.record_alert_event` 逐个落 `alert_events` (`:1266-1278`, 失败跳过广播/投递) → SSE dict 组装 (`:1282-1305`) → `_broadcast_alerts(all_alerts)` (`:405-407`, 逐订阅者 `push_alerts`) → `_maybe_send_system_notifications` → `_maybe_send_webhook(rule_events, engine)` (`:1356+`, 按 rule.webhook_channels 经 `notifications/delivery.py` DeliveryConfig 入队, fixture_mode 短路)。
- `_market_phase` (`:1109-1111`): 9:15-9:30 → `"preopen"`; `_should_poll_for_phase` 含 preopen → **盘前轮询会 flush live enriched** (`_flush_live_enriched`, `:1459+`; 调用点 `:892-893`, `:1003`) → 09:26 预览 job 消费的就是这份内存帧。
- `trigger_phase1_fixture_monitor` (`:635-640`): fixture-mode 测试 seam (`_evaluate_monitors(pl.DataFrame(), None)`) — preopen 测试可仿此直接调新入口, 无需时间 gate。
- `app.state.quote_service = qs` (`main.py:429-430`) — daily_pipeline 可经 `app_state.quote_service` 触达广播/投递方法。

### 1.4 盘前预览 (v2.1, PM-01)

- Job: `daily_pipeline.py` `_PREMARKET_JOB_ID = "premarket_pool_preview"`, `_PREMARKET_HOUR, _PREMARKET_MINUTE = 9, 26` (`:966-970`); `scheduler.add_job(lambda: _run_tracked(_premarket_pool_preview, "premarket_pool_preview"), CronTrigger(mon-fri, 09:26, Asia/Shanghai), id=..., misfire_grace_time=1800)` (`:1145-1153`); `_run_tracked` 单飞 (`:723-758`, job_store + 重任务执行槽)。
- `_premarket_pool_preview(on_progress)` (`:1017-1061`): app_state/repo/svc → `today = cn_today()` → `premarket_pool.build_premarket_preview(repo, engine, as_of=today)` → `if payload.get("available"): persist_premarket_snapshot(data_dir, str(today), payload)` → return `{as_of, strategies, degraded}`。**绝不写 strategy_cache / screener_results (PM-01 铁律)。尾段接线点 = persist 之后、`emit("done")` 之前。**
- Payload 构造 (`services/premarket_pool.py:30-100` `build_premarket_preview`): `svc.run_all_with_hits(as_of, engine)` (`screener.py:723-812`, 输出 `{sid: {total, as_of, rows}}`, rows 每行附 `hit_factors` 经 `strategy/factor_hits.py`) + `resolve_auction_probe()` 判定 → `{as_of, available, window:"pre_open", computed_at, provisional:True, degraded:(verdict.status != "available"), probe:verdict, strategy_version, results}`; 空 results → `{as_of, available:False, degraded:True, window:"pre_open", probe, results:{}}` 诚实空态。
- Payload 行字段 (经 `_project_hub` 消费面确认, `pool_hub.py:222-248`): `symbol` (带交易所后缀, 如 `"000001.SZ"`)、`code`、`name`、`open_gap`、`change_pct`、`hit_factors` + 竞价列 `auction_volume/auction_amount/auction_volume_ratio/auction_unmatched_amount` (**仅 probe available 且 `kline_auction/date={T}` 有行时存在**, 注入见 `services/auction_columns.py:90-151` 双闸门)。`change_pct` 恒在 (enriched 列)。
- 存储 (`services/premarket_snapshot.py`): `persist_premarket_snapshot` (`:48-82`, 原子写 + `_DATE_RE` fullmatch 防路径穿越) / `load_premarket_snapshot` (`:83-99`) / `list_premarket_dates` (`:101-113`)。
- 只读 API (`api/pool.py:118-176` `GET /api/pool/premarket`): 固定今日; 快照缺失/非 available → 200 `{available:false, degraded:true}`; 有 → `_project_hub` 投影 + `window/provisional/degraded/probe` 透传 + `mask_guest_hub`。

### 1.5 告警持久化 / 读取 / 投递

- `operational/repository.py record_alert_event` (`:345-391`): `INSERT INTO alert_events (id, rule_id, source, type, symbol, name, price, change_pct, severity, conditions_json, account_id, position_id, valuation_source, valuation_as_of, occurred_at, created_at, event_json)` — **`event_json` 存全量事件 dict** → `get_alert_event` (`:393-403`) 返回全量字段 → preopen 专属字段 (`window/provisional/degraded/probe/strategy_ids/preopen_metrics`) 天然 round-trip, 无需改表。
- `list_alert_events` (`:408-445`): days/limit/source/type/severity/delivery_status 过滤。
- `api/alerts.py list_alerts` (`:18-46`): 优先 operational (SQLite), 未初始化回退 `alert_store.list_recent` (`services/alert_store.py:68+`, jsonl); `append_many` (`:52-66`) 为降级写路径。
- SSE: `_broadcast_alerts` (`quote_service.py:405-407`) → 订阅者 `push_alerts`; `api/alerts.py:144-164` 演示数据也走 `quote_service` SSE (仅 Dev 页)。

### 1.6 规则 API / 前端

- `api/monitor_rules.py`: `RuleModel` (`:59`); `GET /options` (`:82-143`) 返回 `threshold_fields` (ALLOWED_FIELDS + `ENRICHED_COLUMNS` 中文标签, `indicators/pipeline.py:90-161`)、`builtin_signals` (signal_*)、`custom_signals` (csg_*)、`operators` (6 个数值比较)、`types` (signal/price/market/strategy/position — **无 ladder**, 走专属 UI)、`scopes` (symbols/all/positions — **sector 不下发**)、`logics/severities/directions`。`save_rule` (`:139-153`) normalize+validate; ladder 有 Pro+ 能力闸门 (preopen 无需能力闸门)。
- 前端: `pages/Monitor.tsx` (告警列表 + 规则列表; `TYPE_LABEL` (`:25-29`) 需加 `preopen` 条目; `SOURCE_BADGE_STYLE` 可加 preopen 样式; AlertsList 渲染 `source`/`message`/`severity`, 加 provisional 徽标), `components/monitor/RuleEditor.tsx` (类型切换 + 条件编辑; `thresholdFields = options.data?.threshold_fields`, `operators` 下拉, truth 信号点选), `lib/api.ts` (`MonitorRule`/`MonitorCondition`/`AlertEvent`/`MonitorRuleOptions` 类型, `:939-1004`)。**`frontend/src/pages/Watchlist.tsx` OFF-LIMITS 铁律保持。**

### 1.7 关键错位确认 (研究文档 §3 结论复核)

| 维度 | 监控引擎 | 盘前预览 | 复核结论 |
|---|---|---|---|
| 输入 | 实时 enriched DataFrame | JSON payload `{sid: {total, as_of, rows}}` | 需输入适配 (§5) |
| 时间窗口 | 仅连续竞价 | 09:26 单次 job | 无重叠 (09:26 ∉ 连续竞价; 与 15:30 EOD 相距 ~6h) |
| 字段 | `ALLOWED_FIELDS` (EOD 列含 `change_pct`/`close`/`vol_ratio_5d`) | pre_open 白名单 (禁 EOD 列) | **`ALLOWED_FIELDS` 不含 `open_gap`/`auction_*`** → preopen 需独立白名单常量 (§3) |
| 语义 | 盘中价格/信号 | provisional | 事件携带 provisional 标注 |

---

## 2. 实现方案 (选项 A — 统一引擎 `preopen` 规则类型)

沿用 MONITOR-PREOPEN.md 推荐: **新增 `preopen` 类型 + `MonitorRuleEngine.evaluate_premarket(payload)` + `_premarket_pool_preview` 尾段接线**。选项 B (复用 type=strategy) 因 `_strategy_pools` 池基线污染 09:30 盘中首轮 diff 已否决; 选项 C (独立硬编码 hook) 因绕开统一规则 schema/UI 已否决 — 均不复活。

设计决策 (本次核实后收敛):

| # | 决策点 | 结论 | 依据 |
|---|--------|------|------|
| D1 | 白名单常量 | **新增 `PREOPEN_ALLOWED_FIELDS = frozenset({"open_gap", "auction_volume", "auction_amount", "auction_volume_ratio", "auction_unmatched_amount"})`** (放 `monitor_rules.py`, 与 `ALLOWED_FIELDS` 并列) | `ALLOWED_FIELDS` (`custom_signals.py:34-56`) 物理不含 `open_gap`/`auction_*` — 独立常量避免污染盘中字段语义; 中文标签复用 `ENRICHED_COLUMNS` (`pipeline.py:95,157-161`) |
| D2 | op 支持 | **仅数值比较 `OPS` (`> >= < <= == !=`); `op=truth` 显式拒绝** | 引擎 `truth` 语义 = 布尔信号列 (`_is_signal_field` 校验 `signal_`/`csg_` 前缀, `monitor_rules.py:96-99`), pre_open 帧无布尔信号列 (白名单全数值) → truth 规则必然 fail-closed; 配置期拒绝优于评估期静默 (MONITOR-PREOPEN MON-01 原文一致) |
| D3 | scope | **仅 `symbols`/`all`**; `sector`/`positions` validate 拒绝 | 09:26 板块 loader 可用但属可后补 (OQ-2); `positions` 语义与盘前无关; 与 /options scopes 下发一致 |
| D4 | 评估帧构建 | payload rows 抽 `symbol` 去重; 只保留存在列 + `symbol/name/change_pct(None)/hit_factors/source_strategies`; **不伪造白名单列** | 缺列 → `_build_condition_mask` `field not in cols → df.head(0)` fail-closed (镜像 attach_auction_columns 诚实缺列, 绝不 0 填) |
| D5 | cooldown 复用 | 复用 `_last_fire` key=`(rule_id, symbol)`; preopen rule_id 与盘中规则天然隔离 | 现有实现; remove_rule 清理同 rule_id; GIL 原子 dict 写 (与盘中轮询线程并发安全) |
| D6 | 事件字段 | `source="preopen"`、`type="preopen"`、`window="pre_open"`、`provisional=True`、`degraded`/`probe` 透传、`strategy_ids`、`preopen_metrics` (命中行白名单数值)、`change_pct=None`、`price=None` | `record_alert_event` event_json 全量 round-trip (§1.5), 不改表; SSE dict 组装处追加透传键 (§5.3) |
| D7 | 调度 | 尾段接线 (persist 后同单飞内); 失败非致命 | 免二次读盘、免新 job 竞态; 预览失败已落盘的场景由 job result 摘要覆盖 (不做独立 09:27 job, 保持 v2.2 范围最小) |
| D8 | 降级独立 job | **不做** (尾段方案优先); `load_premarket_snapshot` 兜底路径留作注释性说明 | MONITOR-PREOPEN 调度设计二选一, 推荐尾段 |

---

## 3. 规则 schema (MON-01)

### 3.1 新增常量 (`backend/app/strategy/monitor_rules.py`)

```python
RULE_TYPES = {"strategy", "signal", "price", "market", "ladder", "position", "preopen"}  # :29 扩展

# 盘前监控字段白名单 — 09:26 帧仅集合竞价可确认的数值列 (禁 EOD 列)。
# 与 builtin pre_open 策略 (auction_*/t1_flash) 禁 EOD 列语义一致。
PREOPEN_ALLOWED_FIELDS: frozenset[str] = frozenset({
    "open_gap", "auction_volume", "auction_amount",
    "auction_volume_ratio", "auction_unmatched_amount",
})
```

### 3.2 `validate()` 新增分支 (插在 ladder 分支后, else 之前)

```python
elif rule.get("type") == "preopen":
    if rule.get("scope", "symbols") not in {"symbols", "all"}:
        raise ValueError("preopen 规则 scope 仅支持 symbols/all")
    # conditions 走通用校验 (1-8 条、logic), 但字段/op 用 preopen 专属约束:
    for i, c in enumerate(conds := rule.get("conditions", [])):
        if c.get("op") == "truth":
            raise ValueError(f"第 {i+1} 个条件: preopen 规则不支持 op=truth (无布尔信号列)")
        if c.get("op") not in OPS:
            raise ValueError(f"第 {i+1} 个条件: op {c.get('op')!r} 非法 (preopen 仅 {OPS})")
        if c.get("field") not in PREOPEN_ALLOWED_FIELDS:
            raise ValueError(f"第 {i+1} 个条件: preopen 阈值字段 {c.get('field')!r} 不在盘前白名单 "
                             f"{PREOPEN_ALLOWED_FIELDS} (EOD 列如 change_pct/close/vol_ratio_5d 禁用)")
        if not isinstance(c.get("value"), (int, float)):
            raise ValueError(f"第 {i+1} 个条件: value 必须是数字")
```

要点:
- **`change_pct`/`close`/`vol_ratio_5d`/`amount` 等 EOD 列显式拒绝** (白名单外抛 ValueError, 镜像 MONITOR-PREOPEN MON-01 + builtin pre_open 策略禁 EOD 列)。
- `op=truth` 显式拒绝 (D2)。conditions 非空/≤8、logic、severity/cooldown/active_time/webhook_channels 走既有通用校验 (落在 `else` 之后的公共段, 零重复)。
- 通用 `conditions` 校验循环会先跑 (当前实现把 conditions 校验放在 `else` 分支) — **实现注意**: 现有代码把 conditions 校验放在 `else` (signal/price/market) 分支内, preopen 分支需自行复制 conditions 形状/数量校验或重构该段为公共 helper; 推荐把「conditions 形状 + logic + 数量」抽成 `_validate_conditions_shape(rule)`, 三个类型共用, 字段/op 约束按类型分派 (`_validate_condition_field`), 避免三份重复。

### 3.3 `normalize()` 

preopen 落入既有默认值路径 (enabled/asset_type=stock/scope=symbols/conditions/logic=and/cooldown_seconds=3600/severity=info/webhook_channels 均已在 `:203-241` setdefault) — **零改动**。`direction` 默认 "entry" (preopen 不用, 无碍)。

### 3.4 规则示例

```json
{
  "id": "mr_preopen_gap5",
  "name": "盘前高开预警",
  "type": "preopen",
  "enabled": true,
  "asset_type": "stock",
  "scope": "all",
  "logic": "and",
  "conditions": [
    {"field": "open_gap", "op": ">=", "value": 0.05},
    {"field": "auction_volume_ratio", "op": ">=", "value": 3.0}
  ],
  "cooldown_seconds": 600,
  "severity": "warn",
  "webhook_channels": ["feishu"]
}
```

---

## 4. 引擎改动 (`backend/app/strategy/monitor.py`)

### 4.1 `evaluate()` 入口跳过 preopen (正确性必需, 新发现)

当前 `evaluate` 循环 (`:540-548`) 仅跳过 `type=="position"` 或 asset_type 不匹配; `type=preopen` 会落入 `_evaluate_rule` else 分支在**盘中连续竞价**求值 — 因盘中帧含 `open_gap` (enriched 恒在), `open_gap` 规则会盘中重复触发 (噪音), 且 `change_pct` 为盘中值 (误导)。改动:

```python
if (rule.get("type") in {"position", "preopen"}
        or rule.get("asset_type", "stock") != asset_type):
    continue
```

### 4.2 `evaluate_premarket(payload) -> list[dict]` 入口

```python
def evaluate_premarket(self, payload: dict) -> list[dict]:
    """盘前评估: 消费 v2.1 预览 payload (JSON), 产出 preopen 告警事件。

    - 只评估 enabled 且 type=preopen 的规则 (与盘中 evaluate 互斥);
    - 从 payload["results"] 全部策略 rows 抽 symbol 去重建 Polars DataFrame,
      change_pct 一律置 None (诚实缺列, R1);
    - 复用 _apply_scope / _build_condition_mask / _match_conditions /
      _last_fire cooldown / _default_message (事件构建);
    - 绝不触碰 _strategy_pools / _latest_strategy_results / _building_strategy_results。
    """
```

流程:

1. **前置**: `if not self._rules: return []`; `payload` 无 `results` 或 `payload.get("available") is False` → `return []` (诚实空态, 调用方也不该进)。
2. **规则集**: `rules = [r for r in self._rules.values() if r.get("enabled") is not False and r.get("type") == "preopen"]`; 空 → `[]`。
3. **构建评估帧** (纯内存, 只读 payload):
   ```python
   rows: list[dict] = []
   source_map: dict[str, set[str]] = {}
   for sid, result in (payload.get("results") or {}).items():
       for row in result.get("rows", []):
           if not isinstance(row, dict) or not row.get("symbol"):
               continue
           rows.append(row)
           source_map.setdefault(str(row["symbol"]), set()).add(sid)
   if not rows:
       return []
   # 列 = 行键并集 (仅存在列); 保证 symbol/name 恒在; change_pct 全 None 显式声明
   cols = sorted({k for r in rows for k in r.keys()})
   frame = pl.DataFrame(rows).select([c for c in cols if c in frame_ok])  # 见下
   ```
   规范化: 保留 `symbol/name/open_gap/auction_volume/auction_amount/auction_volume_ratio/auction_unmatched_amount/hit_factors` (白名单列 + 展示列); **追加** `change_pct = None` 列 (显式「此处无意义」标记, 兼防 `_match_conditions` 读到行内残留 change_pct); **追加** `source_strategies` (排序后 list)。`frame = frame.unique(subset=["symbol"], keep="first")` (symbol 级去重, 镜像 `auction_columns.py:146`; 多策略命中取首个行, `hit_factors` 本身已是跨策略聚合)。
4. **逐规则评估** (复用 `_evaluate_rule`):
   ```python
   now = time.time()
   events: list[dict] = []
   for rule in rules:
       try:
           events.extend(self._evaluate_rule(frame, rule, now))
       except Exception as e:
           logger.warning("盘前规则评估失败 %s: %s", rule.get("id"), e)
   ```
   `_evaluate_rule` 内 `_apply_scope` (scope=symbols/all)、`_match_conditions`、cooldown、事件构建全部复用 — **single event-building path, 零分叉**。
5. **事件标注** (对每个事件):
   ```python
   ev["source"] = "preopen"
   ev["type"] = "preopen"
   ev["window"] = "pre_open"
   ev["provisional"] = True
   ev["degraded"] = bool(payload.get("degraded"))
   ev["probe"] = payload.get("probe")
   ev["strategy_ids"] = sorted(source_map.get(ev.get("symbol"), []))
   ev["change_pct"] = None          # R1 诚实缺列 (兜底)
   ev["price"] = None
   # preopen_metrics: 命中行白名单数值 (结构化给 UI/飞书模板用)
   ```
6. **隔离保证**: 本方法全程不读写 `_strategy_pools` / `_latest_strategy_results` / `_building_strategy_results`; 不调 `_match_strategy`; 不 import 执行族 / strategy_cache (MON-05)。

### 4.3 message (推荐小改 `_default_message`)

`_default_message` 加 preopen 分支 (镜像 strategy/ladder 分支风格):

```python
if rtype == "preopen":
    cond_text = self._format_conditions_text(rule, conditions)
    return f"盘前 {cond_text}" if cond_text else "盘前监控触发"
```

(price/pct 恒 None, 不加尾缀。) `preopen_metrics` 供前端/飞书渲染具体数值 (open_gap 格式化为 %, auction_volume_ratio 保留 2 位), 不塞进 message 字符串 (保持 message 稳定可断言)。

---

## 5. 调度接线 (MON-03)

### 5.1 尾段钩子 (`backend/app/jobs/daily_pipeline.py` `_premarket_pool_preview`)

persist 之后、`emit("done")` 之前插入 (与 persist 同一 `_run_tracked` 单飞内):

```python
if payload.get("available"):
    premarket_snapshot.persist_premarket_snapshot(data_dir, str(today), payload)
    # MON-03: 盘前告警评估尾段 — 内存直取 payload, 免二次读盘; 失败不阻断预览本身。
    try:
        qs = getattr(app_state, "quote_service", None)
        if qs is not None and callable(getattr(qs, "evaluate_premarket_alerts", None)):
            eval_summary = qs.evaluate_premarket_alerts(payload)
            result_extra = eval_summary or {}
        else:
            logger.info("盘前告警评估跳过: quote_service 未装配")
    except Exception as e:  # noqa: BLE001
        logger.warning("盘前告警评估失败 (不阻断预览持久化): %s", e)
```

- `payload.available == False` → 不评估不告警 (诚实空态, 与预览 skip 语义一致)。
- 失败非致命: 预览 persist 已完成, job 正常 succeed; 异常记 warning (镜像 `_pool_eod_persist` 的 concept_history 捕获风格 `:1011-1015`)。
- job result 追加 `preopen_eval: {rules, events, degraded, probe_status}` 摘要 (JobStore 历史可见, 供「为什么没告警」排查, 配合 MON-04)。

### 5.2 `QuoteService.evaluate_premarket_alerts(payload) -> dict` (`quote_service.py`, 与 `_evaluate_monitors` 并列)

镜像 `_evaluate_monitors` 的持久化/广播/投递序列, 但**不 gate 时间** (仅由 09:26 job 触发):

```python
def evaluate_premarket_alerts(self, payload: dict) -> dict:
    """盘前告警评估 + 持久化 + SSE + 飞书 (MON-03)。零盘中耦合。"""
    engine = getattr(self._app_state, "monitor_engine", None)
    if engine is None:
        return {"skipped": "no monitor engine"}
    if not payload or not payload.get("available"):
        return {"skipped": "preview unavailable", "degraded": True}
    events = engine.evaluate_premarket(payload)
    # 持久化优先 (镜像 _evaluate_monitors:1266-1278): 落库成功才广播/投递
    operational = getattr(self._app_state, "operational", None)
    persisted: list[dict] = []
    if operational is not None:
        for ev in events:
            try:
                p = operational.record_alert_event(ev)
                ev["id"] = p["id"]; ev["occurred_at"] = p["occurred_at"]
                persisted.append(ev)
            except Exception as e:  # noqa: BLE001
                logger.warning("盘前告警持久化失败,跳过广播和投递: %s", e)
    else:
        # 降级: alert_store.jsonl (镜像旧路径); 跳过投递
        from app.services import alert_store
        alert_store.append_many(self._app_state.repo.store.data_dir, events)
        persisted = events
    if persisted:
        self._broadcast_alerts([self._preopen_sse_shape(ev) for ev in persisted])
        self._maybe_send_webhook(persisted, engine)
    return {
        "rules": engine.rule_count,
        "events": len(persisted),
        "degraded": bool(payload.get("degraded")),
        "probe_status": (payload.get("probe") or {}).get("status"),
    }
```

`_preopen_sse_shape(ev)`: 在 `_evaluate_monitors` 的 SSE dict 键集 (`:1282-1305`) 基础上**追加** `window/provisional/degraded/probe/strategy_ids/preopen_metrics` (纯增量键, 旧客户端忽略未知键, 兼容)。`_broadcast_alerts` (`:405-407`) 与 `_maybe_send_webhook` (`:1356+`, 按 `engine.rules[rule_id].webhook_channels` 入队) 原样复用 — preopen 规则已 `set_rules` 装载, 渠道/severity 生效。

### 5.3 时间碰撞复核 (本次确认)

- 09:26 ∈ 盘前轮询窗口 (`_should_poll_for_phase("preopen")` True), ∉ 连续竞价 (09:30 起) → 与盘中 `_evaluate_monitors` 零重叠; 09:30 首轮盘中评估在 09:26 之后, 不受 preopen 影响 (且 preopen 规则已被 `evaluate` 跳过, §4.1)。
- 与 15:30 EOD 管道 / 15:35 股池持久化相距 ~6h, 无碰撞; `_run_tracked` 单飞保证同 job 不并发。
- 共享资源 (operational.db / SSE 队列 / delivery 队列) 均为线程安全追加 (既有事实, 与盘中并发共存), preopen 评估线程 (调度器线程) 与行情轮询线程共享 `_last_fire` — dict 原子写 + 异 rule_id, 无冲突。

---

## 6. 诚实语义 (MON-04)

| 场景 | 行为 | 表达 |
|------|------|------|
| 预览 `available:false` (空帧/无 live 缓存) | 不评估、0 告警 | job result `preopen_eval.skipped="preview unavailable"`; 前端盘前页已有诚实空态 (PM-01) |
| 预览 `degraded:true` (probe 非 available) | 竞价列缺席 → 依赖 `auction_*` 的规则 `_build_condition_mask` `field not in cols → df.head(0)` **fail-closed 0 命中**; `open_gap` 规则仍可命中 (open_gap 恒在 enriched) | 命中事件携带 `degraded:true` + `probe` (冻结快照); job result 透传 degraded; 前端盘前页/告警页可展示「盘前数据降级」提示 |
| 单 symbol 缺竞价值 (分区有行但该股缺席) | 列存在但该行 null → `null >= x` 不成立 → 不命中 (诚实按标的缺席, 非整日 null-as-present) | 无事件; `preopen_metrics` 缺失键 |
| EOD 列 (change_pct/close/vol_ratio_5d/amount) | validate 白名单拒绝 + 评估帧 `change_pct` 全 None 双保险 | 配置期 ValueError; 事件 `change_pct:null` |
| provisional | 所有 preopen 事件 `provisional:true` + `window:"pre_open"` | 前端「盘前·非最终」徽标; 飞书消息前缀「盘前」 |
| 降级时「为什么不报」 (R3) | 不静默: job result 摘要 + 事件 degraded 标志 + 盘前页既有 degraded 态 | 开放问题 OQ-3: 是否落「未触发日志」表 (v2.2 建议不做, 保持零新 schema) |

**绝不**: 0 填缺失竞价列、派生兜底 (e.g. 用 change_pct 冒充 open_gap)、把预览帧写 strategy_cache/screener_results、让 preopen 规则在盘中求值。

---

## 7. 零执行 / 存储隔离 (MON-05)

- **只读边界**: `evaluate_premarket` 只读内存 payload (job 尾段) 或 `load_premarket_snapshot` (未来手动补跑); 绝不调 `strategy_cache.write_cache` / `pool_snapshot.persist_point_snapshot` / 写 `screener_results` / `run_all_with_hits` (预览 payload 已由 job 上游构造)。
- **import 白名单**: `monitor.py`/`quote_service.py`/`daily_pipeline.py` 的 preopen 路径不 import 执行族 (broker/order/trade/execution/portfolio/position/account/transaction) 与 `strategy_cache` — 镜像 `premarket_pool.py` 模块 docstring 铁律。
- **AST 守卫**: 镜像 `tests/test_pool_hub.py:854-963` 形 (`_EXECUTION_TOKEN` regex + `_imported_module_names` ast 解析 + `_WRITE_PATTERNS`), 新增对 preopen 评估路径的守卫测试 (见 §11 T7)。
- **既有守卫不冲突**: `test_pool_hub.py` 守卫只扫 `pool_hub.py/pool.py/pool_snapshot.py` — 引擎/行情/调度模块不在扫描面; 新增守卫独立按模块拆分 (与 SUMMARY「POOL-03 AST 守卫词汇扩展须按模块拆分」一致)。

---

## 8. 游客脱敏 (MON-06)

- 现状: `mask_guest_hub` (`services/guest_masking.py:20-55`) 是游客可见 DTO 的唯一脱敏点 — 身份 `******` + 白名单 `{change_pct, concept_board, hit_factors, cross_resonance}` 外全剥离 (open_gap/auction_* 天然不带出), 顶层 `auction_columns` pop。
- preopen 告警落库字段含 `symbol/name/open_gap/auction_*` (event_json + 列) — **任何游客可见表面渲染告警记录时须脱敏**:
  - 新增 `mask_guest_alert(event: dict) -> dict` (放 `guest_masking.py`, 纯拷贝): `symbol/name/code → MASKED_IDENTITY`; 剥离 `open_gap/auction_*`/`preopen_metrics`/`probe`; 保留 `message`(含盘前文案, 不含 PII)/`severity`/`window/provisional/degraded`/`rule_name`/`conditions`。
  - 当前 `/api/alerts` 为登录面 (无 guest 路径), SSE 告警推送面向登录订阅者 — 守卫语义为**防御性**: 未来任何 guest 可见 alerts 表面必须经 `mask_guest_alert` (镜像 GUEST-01/02 DTO 边界原则)。
- 飞书/Telegram 为所有者通道, 不受 guest 掩码约束 (MONITOR-PREOPEN 诚实边界原文)。

---

## 9. 规则 API / 前端 (MON-07, P2)

### 9.1 后端 `/api/monitor-rules/options` (`api/monitor_rules.py:82-143`)

- `types` 追加 `{"key": "preopen", "label": "盘前异动"}` (signal/price/market/strategy/position 之后)。
- 追加 `preopen_threshold_fields`: 5 个白名单字段 + 中文标签, 复用 `ENRICHED_COLUMNS` (`pipeline.py:95` open_gap 开盘涨幅, `:157-161` auction_volume 竞价量 / auction_amount 竞价金额 / auction_volume_ratio 竞价量比 / auction_unmatched_amount 派生未匹配金额) — **零新标签表**。
- `operators` 沿用 (6 个数值比较); `scopes` 不变 (symbols/all 由 preopen validate 约束)。

### 9.2 前端 (不触碰 `Watchlist.tsx`)

- `lib/api.ts`: `MonitorRuleOptions` 加 `preopen_threshold_fields?: {key,label}[]`; `MonitorRule.type` 联合类型加 `'preopen'`; `AlertEvent` 加可选 `window/provisional/degraded/strategy_ids/preopen_metrics`。
- `components/monitor/RuleEditor.tsx`:
  - `TYPE_DEFAULT_NAME` 加 `preopen: '盘前异动'`; 类型下拉 (options.types 驱动) 自动出现 preopen。
  - 条件字段下拉: `type === 'preopen'` 时用 `options.preopen_threshold_fields ?? []` (而非 `threshold_fields`)。
  - `type === 'preopen'` 时隐藏 truth 信号点选 (addCond 只允许 threshold; SignalPicker 区隐藏)。
  - 保存校验沿用 (conditions 非空 + 数值 value)。
- `pages/Monitor.tsx`:
  - `TYPE_LABEL` 加 `preopen: '盘前'` (`:25-29`)。
  - `SOURCE_BADGE_STYLE` 加 `preopen` 条目 (可选配色)。
  - AlertsList: 对 `ev.source === 'preopen'` 渲染「盘前·非最终」徽标 (provisional 徽标) + degraded 时灰标「数据降级」(取 `ev.degraded`)。
- 规则编辑器 preopen 保存无需能力闸门 (ladder 的 Pro+ DEPTH5_BATCH 闸门不适用)。

---

## 10. 风险 (R1 已核实, 其余复核)

| # | 风险 | 级别 | 结论/缓解 |
|---|------|------|-----------|
| R1 | **change_pct 口径** | 高 | **已核实**: `compute_enriched_today` (`indicators/pipeline.py:1312-1314`) 对 `change_pct` 无列时按 `close/prev_close − 1` 计算; 09:26 帧 `close` = 集合竞价撮合/指示价 (09:25 定盘, `_market_phase` preopen 轮询 flush, `quote_service.py:1109-1111,1459+`) → **`change_pct ≈ open/prev_close − 1 = open_gap`, 语义 = 竞价价较昨收的变动, 绝非 EOD 日涨跌幅** [INFERENCE: live API 在 09:26 的 `close` 精确字段来源未在代码内逐字节验证, 但竞价定盘语义 + `open_gap` 单一实现 (`:1328-1334` 与 change_pct 同分母) 强支持此结论]。缓解: 白名单禁 EOD 列 (MON-01) + 评估帧 `change_pct` 置 None (MON-02) — 双保险已锁死误用路径 |
| R2 | 盘前命中 + 开盘后重复 | 中 | preopen 独立 rule_id → cooldown 域隔离; `evaluate()` 跳过 preopen (§4.1) 防盘中重复; 默认 severity=info + 前端「盘前」徽标区分 |
| R3 | degraded 时「静默不报」 | 中 | job result 摘要 + 事件 degraded 标志 + 盘前页既有 degraded 态; OQ-3 未触发日志表 (v2.2 不做) |
| R4 | 选项 B 池基线污染被误采 | 高 | 本方案明确否决 B; roadmap 已锁 (SUMMARY 范围裁决); 引擎注释 `_match_strategy` 处加「preopen 不得走此路径」警示注释 |
| R5 | probe 状态 09:26 后变化 | 低 | 事件携带冻结 `payload.probe` 快照; 预览语义即「当时快照」, 不回溯 |
| R6 | `evaluate()` 未跳过 preopen → 盘中误触发 | 中 | §4.1 显式跳过 + 回归测试 (T6) |
| R7 | 并发: 调度线程 `evaluate_premarket` 与行情轮询 `evaluate` 共享 `_last_fire` | 低 | 异 rule_id + GIL 原子 dict 写; 与既有 `remove_rule` list 快照模式同级 |
| R8 | 事件 `event_json` 体积 (preopen_metrics + probe dict) | 低 | SQLite 存 JSON 文本, 单事件 <10KB, 可忽略; 不做裁剪 |

---

## 11. 新增测试清单 (验收口径 MON-01..07 映射)

| # | 测试文件 | 测试 | MON |
|---|---------|------|-----|
| T1 | `tests/test_preopen_monitor_rules.py` (新) | `validate` 合法 preopen 规则 (5 白名单字段 × OPS) 保存成功 | MON-01 |
| T2 | 同上 | `field=change_pct` / `close` / `vol_ratio_5d` / `amount` → ValueError (禁 EOD 列); `op=truth` → ValueError; 缺 conditions → ValueError; `scope=sector/positions` → ValueError | MON-01 |
| T3 | 同上 | `normalize` preopen 默认: severity=info, cooldown=3600, logic=and, asset_type=stock | MON-01 |
| T4 | 同上 | `evaluate_premarket(payload)` 帧构建: 多策略 rows 按 symbol 去重、`change_pct` 列全 None、`source_strategies`/`hit_factors` 正确、行内残留 `close` 不进入事件 | MON-02 |
| T5 | 同上 | 命中事件字段: `source="preopen"`/`type="preopen"`/`window="pre_open"`/`provisional=True`/`degraded`/`probe` 透传/`strategy_ids`/`preopen_metrics`/`change_pct=None`/`price=None` | MON-02/04 |
| T6 | 同上 | `evaluate()` (盘中) 跳过 preopen 规则 → 0 事件 (回归: open_gap 规则不得盘中触发) | MON-02 (隔离) |
| T7 | 同上 | `_strategy_pools`/`latest_strategy_results()` 在 `evaluate_premarket` 前后不变 (隔离断言) | MON-02 |
| T8 | 同上 | cooldown: 同 (rule_id, symbol) 冷却期内二次调用不重复触发; 不同 rule_id 互不影响 | MON-02 |
| T9 | 同上 | `degraded=true` payload + `auction_*` 规则 → 0 事件 (fail-closed); 同 payload `open_gap` 规则仍命中且事件 `degraded=True` | MON-04 |
| T10 | 同上 | 缺竞价列 payload (degraded) + 混合规则: 缺列规则 0 命中; 某 symbol 无 auction 值 → 该 symbol 不命中 (按标的缺席) | MON-04 |
| T11 | `tests/test_preopen_scheduling.py` (新) | 注册形 grep (镜像 `test_premarket_pool.py::test_premarket_job_registered_in_scheduler`): `_PREMARKET_JOB_ID`/09:26/`_run_tracked`/mon-fri 常量存在 | MON-03 |
| T12 | 同上 | 尾段接线: monkeypatch `app_state.quote_service.evaluate_premarket_alerts` → `_premarket_pool_preview` persist 后调用, 传内存 payload (非二次读盘) | MON-03 |
| T13 | 同上 | `payload.available:false` → 不调 evaluate_premarket_alerts | MON-03 |
| T14 | 同上 | 评估异常 → 预览 persist 仍成功、job 返回成功 + warning (失败非致命) | MON-03 |
| T15 | 同上 | 时间无重叠: 断言 `(9,26)` ∉ 连续竞价窗口 `[9:30,11:30]∪[13:00,15:00]`; `_PREMARKET_HOUR/_MINUTE` ≠ EOD 默认 `(15,30)` 偏移域 | MON-03 |
| T16 | 同上 (或并入) | fixture 集成: 注入内存 payload → `operational.record_alert_event` 落库 → SSE 队列入队 → 投递入队 (镜像 `_evaluate_monitors` 断言风格); `operational=None` → 降级 `alert_store.append_many` | MON-03 |
| T17 | `tests/test_preopen_honesty.py` (新) | 事件 round-trip: `record_alert_event` → `get_alert_event` → `window/provisional/degraded/probe/strategy_ids/preopen_metrics` 全保留 (event_json 全量) | MON-04 |
| T18 | 同上 | `mask_guest_alert` 快照: 身份 `******`、无 `open_gap`/`auction_*`/`preopen_metrics`/`probe`、保留 message/severity/window/provisional/degraded | MON-06 |
| T19 | `tests/test_preopen_ast_guard.py` (新, 镜像 `test_pool_hub.py` E-guard) | preopen 评估路径 (monitor.py preopen 段 / quote_service.evaluate_premarket_alerts / daily_pipeline 尾段) 无执行族 import、无 `strategy_cache`/`write_cache`/`run_all`/`persist_point_snapshot` 写触发、无写路径 | MON-05 |
| T20 | `tests/test_preopen_api_options.py` (新) | `GET /api/monitor-rules/options`: `types` 含 preopen; `preopen_threshold_fields` = 5 键 (open_gap/auction_volume/auction_amount/auction_volume_ratio/auction_unmatched_amount) | MON-07 |
| T21 | 前端 (若纳入) | RuleEditor preopen 类型: 字段下拉显示 5 白名单字段、无 truth 点选; Monitor.tsx 渲染 preopen 告警「盘前·非最终」徽标 | MON-07 |

---

## 12. 现有测试保持绿色 (回归锁定)

| 文件 | 关注点 | 为何不受影响 |
|------|--------|-------------|
| `tests/test_pool_hub.py` | E1-E6 守卫 (`_EXECUTION_TOKEN`/`_imported_module_names`/`_WRITE_PATTERNS`/GET-only/无 run_all 触发) | 只扫 `pool_hub.py`/`pool.py`/`pool_snapshot.py`; preopen 改动在 monitor/quote/daily_pipeline, 不在扫描面; 守卫词汇扩展按新模块拆分 (T19) |
| `tests/test_premarket_pool.py` | PM-01 job 注册/存储隔离/诚实 skip/probe 三态/API 透传/guest 掩码/POOL-03 AST | 尾段接线仅新增 `quote_service` 调用, 测试的 `_FakeRepo`/`SimpleNamespace` app_state 无 `quote_service` 属性 → getattr 默认 None → skip (设计保证) |
| `tests/test_pipeline_and_monitor_fixes.py` | job 单飞/重任务槽/scope validate/`_apply_scope` sector | preopen 是新增分支, 不动现有分支 |
| `tests/test_monitor_etf.py` | asset_type 过滤/evaluate 行为 | §4.1 只加 `"preopen"` 到跳过集合, 不影响 etf 规则 |
| `tests/test_position_monitor.py` | position 规则契约 | preopen 与 position 互斥 (validate scope 拒绝) |
| `tests/test_guest_masking.py` | GUEST-01/02 | `mask_guest_hub` 不改; `mask_guest_alert` 纯新增 |
| `tests/test_monitor_etf.py`/`test_position_monitor.py` 之外的规则保存链 | `/api/monitor-rules` save/list | normalize/validate 增量分支, 既有类型行为不变; /options 无测试断言 types 精确列表 (已 grep 确认) |

---

## 13. 关键锚点 (exact files/symbols/lines, 本次全部实读)

| 目标 | 文件 | 符号 / 行 |
|---|---|---|
| 规则类型集合 | `backend/app/strategy/monitor_rules.py` | `RULE_TYPES` `:29`; `validate` `:101-201`; `normalize` `:203-241`; `_is_signal_field` `:96-99` |
| 字段白名单 (对照) | `backend/app/strategy/custom_signals.py` | `ALLOWED_FIELDS` `:34-56` (无 open_gap/auction_*); `OPS` `:32`; `_OP_BUILDERS` `:58-63` |
| 引擎 | `backend/app/strategy/monitor.py` | `MonitorRuleEngine` `:329`; `evaluate` `:497-560` (preopen 跳过点 `:540-548`); `_evaluate_rule` `:617-700`; `_apply_scope` `:704-739`; `_match_strategy` `:736-900` (池基线污染点); `_match_conditions` `:903-930`; `_build_condition_mask` `:281-303` (模块级, 缺列 fail-closed); `_default_message` `:1005-1078`; `has_rule_type` `:481-491` |
| 盘中评估触发 | `backend/app/services/quote_service.py` | `_is_continuous_trading` `:1146-1160`; `_market_phase` preopen `:1109-1111`; `_evaluate_monitors` `:1169-1353` (persist-first `:1266-1278`, SSE dict `:1282-1305`); `_broadcast_alerts` `:405-407`; `_maybe_send_webhook` `:1356+`; `_flush_live_enriched` `:1459+`; `trigger_phase1_fixture_monitor` `:635-640` |
| 盘前 job | `backend/app/jobs/daily_pipeline.py` | `_PREMARKET_JOB_ID/_HOUR/_MINUTE` `:966-970`; `_premarket_pool_preview` `:1017-1061` (尾段 = persist 后/`emit done` 前); `scheduler.add_job` `:1145-1153`; `_run_tracked` `:723-758` |
| 盘前 payload | `backend/app/services/premarket_pool.py` | `build_premarket_preview` `:30-100` (window/provisional/degraded/probe/results) |
| 盘前存储 | `backend/app/services/premarket_snapshot.py` | `persist_premarket_snapshot` `:48-82`; `load_premarket_snapshot` `:83-99`; `_DATE_RE` `:31` |
| 竞价列注入 | `backend/app/services/auction_columns.py` | `attach_auction_columns` `:90-151` (probe×分区双闸门, 缺列诚实) |
| 告警持久化 | `backend/app/operational/repository.py` | `record_alert_event` `:345-391` (event_json 全量); `get_alert_event` `:393-403`; `list_alert_events` `:408-445` |
| 告警 API | `backend/app/api/alerts.py` | `list_alerts` `:18-46` |
| 规则 API | `backend/app/api/monitor_rules.py` | `RuleModel` `:59`; `/options` `:82-143`; `save_rule` `:139-153` |
| 游客脱敏 | `backend/app/services/guest_masking.py` | `mask_guest_hub` `:20-55`; `_GUEST_VISIBLE` `:18`; `MASKED_IDENTITY` `:14` |
| 盘前 API | `backend/app/api/pool.py` | `GET /premarket` `:118-176` (投影/透传/掩码) |
| 引擎装配 | `backend/app/main.py` | monitor_engine `:625-703` (无 handler); `app.state.quote_service` `:429-430` |
| change_pct 口径 | `backend/app/indicators/pipeline.py` | `compute_enriched_today` `:1250+`; `change_pct` `:1312-1314`; `open_gap` `:1328-1334`; `ENRICHED_COLUMNS` labels `:95,157-161` |
| 行 shape / hit_factors | `backend/app/services/screener.py` / `strategy/factor_hits.py` | `run_all_with_hits` `:723-812`; `build_factor_hits`/`attach_factor_hits` (`factor_hits.py:19,46`); `_project_hub` 行键 `pool_hub.py:222-248` |
| AST 守卫范本 | `backend/tests/test_pool_hub.py` | E1-E6 `:854-963`; `_imported_module_names` `:884-892` |
| PM-01 守卫范本 | `backend/tests/test_premarket_pool.py` | job 注册/存储隔离/诚实 skip/POOL-03 AST 守卫 |

---

## 14. 开放问题 (v2.2 范围外 / 需 roadmap 决策)

1. **OQ-1 (R1 残余)**: live API 在 09:26 帧 `close` 的精确取值 (撮合价 vs 指示价 vs 昨收) — 代码内不可验证, 需首个真实交易日对 `premarket_results/date=T/part.json` 实测确认; 未确认前白名单禁 EOD 列 + `change_pct=None` 双保险已覆盖产品风险。
2. **OQ-2**: preopen 是否支持 `scope=sector` (板块 loader 已可用, `_apply_scope` sector 分支现成; 需同步 /options scopes 下发 + validate 放宽 + 测试) — 建议 v2.2 后补。
3. **OQ-3**: degraded 时是否落「未触发日志」表 (R3 产品化) — 建议 v2.2 不做 (job result + 事件标志 + 盘前页 degraded 态已覆盖「为什么不报」), 若产品要求再评估零新 schema 的日志方案。
4. **OQ-4**: 与 Phase 31 复盘衔接 — 盘前异动告警是否直喂竞价复盘 (决策闭环跨领域, 属 v2.3) — 与 ResearcherRecap 结论对齐后由 roadmap 定。
5. **OQ-5**: `evaluate_premarket` 落 `monitor.py` (引擎) 后, AST 守卫 (T19) 需按「模块内新增函数段」而非整文件白名单实现 (monitor.py 本身含策略执行路径 `_match_strategy`) — 守卫测试应对 preopen 函数体做 ast 子集解析, 或把 `evaluate_premarket` 放入独立小模块 (如 `strategy/preopen_eval.py`, 只读 payload) — **推荐独立小模块**, 守卫更简单且与选项 A「输入适配」定位一致; 若独立模块, `evaluate_premarket` 从 `MonitorRuleEngine` 调出 (引擎持有实例方法做薄封装, cooldown/_match_conditions 复用经 self 传入)。

---

*Research complete: 2026-08-06*
*Ready for planning: yes (MON-01..07 验收口径 + 测试清单齐备; R1 已核实并双保险锁死)*
