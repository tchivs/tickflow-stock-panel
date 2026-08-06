# Phase 30: 盘前监控告警 (MON-01..07) — Pattern Map

**Mapped:** 2026-08-06
**Files analyzed:** 15 (9 modified, 6 new)
**Analogs found:** 12 / 15 (3 partial — no exact analog, see "No Exact Analog" section)

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|---|---|---|---|---|
| `backend/app/strategy/monitor_rules.py` (mod) | config/validation | CRUD | self (`validate` :101-201, `normalize` :203-241) + `strategy/builtin/auction_allround.py` pre_open 白名单语义 | exact |
| `backend/app/strategy/monitor.py` (mod) | engine | event-driven | self: `evaluate` :497-560, `_evaluate_rule` :617-700, `evaluate_positions` :562-616, `_default_message` :1005-1078 | exact |
| `backend/app/strategy/preopen_eval.py` (new, OQ-5) | utility (纯只读评估适配) | transform | `services/premarket_pool.py` 铁律 docstring :1-18 + `services/pool_hub.py` (纯投影模块) | role-match |
| `backend/app/services/quote_service.py` (mod) | service (编排) | event-driven | self `_evaluate_monitors` :1169-1353 (persist-first :1266-1278, SSE dict :1282-1305, webhook :1356+) | exact |
| `backend/app/jobs/daily_pipeline.py` (mod) | job (调度) | batch | self `_premarket_pool_preview` :1017-1061 (尾段) + `_pool_eod_persist` :975-1015 (非致命 try/except :1008-1015) | exact |
| `backend/app/services/guest_masking.py` (mod) | utility (脱敏) | transform | self `mask_guest_hub` :20-55 (`MASKED_IDENTITY` :14, `_GUEST_VISIBLE` :18) | exact |
| `backend/app/api/monitor_rules.py` (mod) | controller | request-response | self `get_options` :82-143 (`threshold_fields` 构建 :88-93, `types` 列表 :106-112) | exact |
| `tests/test_preopen_monitor_rules.py` (new) | test | — | `tests/test_monitor_etf.py` (引擎单测: `MonitorRuleEngine()` 直构 + `_signal_rule`/`_etf_df` helper) + `tests/test_premarket_pool.py` (`_FakeRepo`/`_make_app_state`) | role-match |
| `tests/test_preopen_scheduling.py` (new) | test | — | `tests/test_premarket_pool.py` job 注册形 grep 测试 + monkeypatch/`SimpleNamespace` 桩 | role-match |
| `tests/test_preopen_honesty.py` (new) | test | — | `tests/test_guest_masking.py` (`_make_guest_client` 结构) + `operational/repository.py` record→get round-trip | role-match |
| `tests/test_preopen_ast_guard.py` (new) | test | — | `tests/test_pool_hub.py` E-guard :854-963 (`_EXECUTION_TOKEN`/`_imported_module_names`/`_WRITE_PATTERNS`) | exact |
| `tests/test_preopen_api_options.py` (new) | test | — | `tests/test_premarket_pool.py` `_make_premarket_client` (FastAPI TestClient + stub 会话) + `tests/test_monitor_etf.py` `RuleModel` 默认值测试 | role-match |
| `frontend/src/lib/api.ts` (mod) | types | — | self MonitorRule/MonitorRuleOptions/AlertEvent 接口 :938-1011 | exact |
| `frontend/src/components/monitor/RuleEditor.tsx` (mod) | component | request-response | self: `TYPE_DEFAULT_NAME` :26-28, `thresholdFields` :191, `addCond` :150-156, truth 点选 `selectedSignals/thresholdConds` :193-194 | exact |
| `frontend/src/pages/Monitor.tsx` (mod) | component | event-driven (SSE) | self: `TYPE_LABEL` :25-29, `SOURCE_BADGE_STYLE` :30-36, AlertsList 渲染 :275-443 (徽标 :392-399) | exact |

## Pattern Assignments

### `backend/app/strategy/monitor_rules.py` (config/validation, CRUD) — MON-01

**Analog:** self + `strategy/builtin/auction_allround.py`

**类型常量扩展** — `RULE_TYPES` (line 29):
```python
RULE_TYPES = {"strategy", "signal", "price", "market", "ladder", "position"}  # → 追加 "preopen"
```
新常量 `PREOPEN_ALLOWED_FIELDS` 与 `ALLOWED_FIELDS` 并列声明 (ALLOWED_FIELDS 来自 `custom_signals.py:34-56`, 本模块已 import)。**镜像 builtin 策略的 pre_open 白名单语义** (`auction_allround.py:35-38`): 禁 EOD 列 (change_pct/close/vol_ratio_5d/amount), 缺列 fail-closed — 这是「禁 EOD 列」的平台既有惯例。

**validate() 新分支** — 插在 `elif rule.get("type") == "ladder":` 分支 (:111-119) 之后、`else:` (:120-140) 之前。复制 else 分支的 conditions 形状/数量校验 (非空、≤8、dict、logic ∈ LOGICS), 但字段/op 用 preopen 专属约束 (RESEARCH §3.2 现成代码):
```python
elif rule.get("type") == "preopen":
    if rule.get("scope", "symbols") not in {"symbols", "all"}:
        raise ValueError("preopen 规则 scope 仅支持 symbols/all")
    for i, c in enumerate(conds := rule.get("conditions", [])):
        if c.get("op") == "truth":
            raise ValueError(f"第 {i+1} 个条件: preopen 规则不支持 op=truth (无布尔信号列)")
        if c.get("op") not in OPS:
            raise ValueError(f"第 {i+1} 个条件: op {c.get('op')!r} 非法 (preopen 仅 {OPS})")
        if c.get("field") not in PREOPEN_ALLOWED_FIELDS:
            raise ValueError(f"第 {i+1} 个条件: preopen 阈值字段 {c.get('field')!r} 不在盘前白名单")
        if not isinstance(c.get("value"), (int, float)):
            raise ValueError(f"第 {i+1} 个条件: value 必须是数字")
```
错误消息格式: 全部中文 ValueError + 精确字段名, 镜像现有 :132-139 的 `f"第 {i+1} 个条件: …"` 风格。scope/severity/cooldown/active_time/webhook_channels 走既有公共段 (:144-200) 零重复。

**normalize()** (:203-241): preopen 零改动 — 既有 setdefault 已覆盖全部默认 (RESEARCH §3.3)。

### `backend/app/strategy/monitor.py` (engine, event-driven) — MON-02

**Analog:** self `evaluate` / `_evaluate_rule` / `evaluate_positions` / `_default_message`

**1) evaluate() 入口跳过 preopen** — `evaluate` :497-560 的规则循环 (:540-548):
```python
for rule_id, rule in list(self._rules.items()):
    if rule.get("type") == "position" or rule.get("asset_type", "stock") != asset_type:
        continue
```
→ 改为 `if rule.get("type") in {"position", "preopen"} or ...`。**list() 快照 + 每规则 try/except + logger.warning("规则评估失败 %s: %s", rule_id, e) (:550-552) 全部保留。**

**2) `evaluate_premarket(payload)` 入口** — 结构复制 `evaluate` (:497-560) + `evaluate_positions` (:562-616, 同类「按 type 过滤规则 → 独立事件构建」入口先例):
- 前置空态: `if not self._rules: return []` + `payload.get("available") is False → []` (镜像 evaluate :519 `if not self._rules or df.is_empty(): return []`)。
- payload rows → Polars DataFrame: 这是**新增适配层**, 无现成引擎内先例; 列规范化镜像 `_inject_sealed_vol` (quote_service.py:1355+, 评估前把列注入 df 副本) 的「构建评估帧」思路 + `auction_columns.py:146` `unique(subset=["symbol"], keep="first")` 去重。**change_pct 全 None 显式声明** (诚实缺列, R1 双保险)。
- 逐规则复用 `_evaluate_rule(frame, rule, now)` (:617-700) — 内部 `_apply_scope` (:704-739, scope=symbols/all 分支现成)、`_match_conditions` (:903-930)、cooldown (:660-685)、事件 dict (:675-697) 全复用, single event-building path。
- 每规则 try/except 复制 evaluate :550-552 的 warning 风格。
- 事件标注 (RESEARCH §4.2 step 5): `ev["source"]="preopen"` / `ev["type"]="preopen"` / `ev["window"]="pre_open"` / `ev["provisional"]=True` / `degraded` / `probe` / `strategy_ids` / `preopen_metrics` — 纯增量键, 与 `record_alert_event` event_json 全量 round-trip 兼容 (repository.py:345-391)。
- 隔离: 不读写 `_strategy_pools`/`_latest_strategy_results`/`_building_strategy_results`; 不调 `_match_strategy` (:736-900, 池基线污染点, **严禁**)。

**3) `_default_message` preopen 分支** (:1005-1078) — 插在 strategy 分支 (:1010-1035) 之后、signal/price/market 段 (:1037+) 之前:
```python
if rtype == "preopen":
    cond_text = self._format_conditions_text(rule, conditions)  # :1058-1078
    return f"盘前 {cond_text}" if cond_text else "盘前监控触发"
```
price/pct 恒 None 不加尾缀 (price_text/pct_text 逻辑 :1039-1046 不适用)。

### `backend/app/strategy/preopen_eval.py` (new, utility/transform) — MON-05/OQ-5

**Analog (role-match):** `services/premarket_pool.py` + `services/pool_hub.py`

新独立小模块 (OQ-5 推荐, 让 AST 守卫按整文件白名单实现, 避开 monitor.py 内 `_match_strategy` 的执行路径):

**模块 docstring 铁律块** — 复制 `premarket_pool.py:1-18` 的结构:
```python
"""盘前规则评估适配 (MON-02/05) — 只读内存 payload, 零执行。

铁律 (镜像 premarket_pool.py:1-11):
- 绝不 import 执行族模块 (broker/order/trade/execution/portfolio/position/account/
  transaction) 与 ``strategy_cache``。
- 绝不调 strategy_cache.write_cache / pool_snapshot.persist_point_snapshot / 写 screener_results。
- 绝不写任何文件; 不触碰 _strategy_pools / _latest_strategy_results。
"""
```

**纯函数结构** — 复制 `pool_hub.py` 的纯只读投影风格 (build/transform, 无副作用, AST 守卫扫面): 引擎持有薄封装方法 (cooldown 与 `_match_conditions` 经 self 传入, 镜像 `set_strategy_engine`/`set_board_loader` 的「引擎注入外部机制」模式 :385-408)。

### `backend/app/services/quote_service.py` (service, event-driven) — MON-03

**Analog:** self `_evaluate_monitors` :1169-1353

`evaluate_premarket_alerts(payload) -> dict` 与 `_evaluate_monitors` 并列定义。复制三段 (RESEARCH §5.2 现成代码):
- **持久化优先** (:1266-1278): `operational.record_alert_event(ev)` → `event["id"]=persisted["id"]`/`event["occurred_at"]=...` → 失败 `logger.warning("告警持久化失败,跳过广播和投递: %s", e)`; `operational is None` → 降级 `alert_store.append_many` + 跳过投递 (镜像 :1266-1271)。
- **SSE dict 组装** (:1282-1305 键集基础上追加 window/provisional/degraded/probe/strategy_ids/preopen_metrics — 纯增量键, 旧客户端忽略未知键): `_preopen_sse_shape(ev)` 辅助函数。
- **广播 + 投递**: `self._broadcast_alerts(all_alerts)` (:405-407) + `self._maybe_send_webhook(persisted, engine)` (:1356+) 原样复用。
- 与 `_evaluate_monitors` 的差异: **无时间 gate** (`_is_continuous_trading` :1146-1160 不调用), 仅由 09:26 job 触发; engine 经 `getattr(self._app_state, "monitor_engine", None)` 取 (main.py:625-703 装配, 无 handler)。
- 测试 seam 先例: `trigger_phase1_fixture_monitor` (:635-640) fixture-mode 直调入口, 新方法天然可直调无需时间 gate。

### `backend/app/jobs/daily_pipeline.py` (job, batch) — MON-03

**Analog:** self `_premarket_pool_preview` :1017-1061 + `_pool_eod_persist` :975-1015

尾段钩子 — persist (:1053-1054) 之后、`emit("done")` (:1055) 之前插入 (RESEARCH §5.1 现成代码):
```python
if payload.get("available"):
    premarket_snapshot.persist_premarket_snapshot(data_dir, str(today), payload)
    # MON-03: 盘前告警评估尾段 — 内存直取 payload, 免二次读盘; 失败不阻断预览本身。
    try:
        qs = getattr(app_state, "quote_service", None)
        if qs is not None and callable(getattr(qs, "evaluate_premarket_alerts", None)):
            result_extra = qs.evaluate_premarket_alerts(payload) or {}
        else:
            logger.info("盘前告警评估跳过: quote_service 未装配")
    except Exception as e:  # noqa: BLE001
        logger.warning("盘前告警评估失败 (不阻断预览持久化): %s", e)
```
- **失败非致命 try/except + warning** — 复制 `_pool_eod_persist` 的 concept_history 捕获风格 (:1008-1015, `logger.warning("概念历史归档失败（不阻断股池持久化）: %s", e)`)。
- **诚实 skip 语义** — 复制本函数既有 :1045-1047 (`if payload.get("available"):` 守卫) 与 :1027-1030 (无 app state → `{"as_of": None, "skipped": "no app state"}`)。
- **getattr 默认 None → skip** — 设计保证 `test_premarket_pool.py` 的 `_FakeRepo`/`SimpleNamespace` app_state (无 quote_service 属性) 不破坏 (RESEARCH §12)。
- job result 追加 `preopen_eval` 摘要 (JobStore 经 `_run_tracked` :723-758 持久化 result dict)。
- 调度注册 (mon-fri 09:26 常量) 不动, 若需新 job 复制 :1145-1153 add_job 块 (本方案为尾段, 不新增)。

### `backend/app/services/guest_masking.py` (utility, transform) — MON-06

**Analog:** self `mask_guest_hub` :20-55

新增 `mask_guest_alert(event: dict) -> dict` (纯拷贝, 不修改入参 — 复制 mask_guest_hub :26 注释语义):
```python
def mask_guest_alert(event: dict) -> dict:
    """返回脱敏后的告警事件副本 (GUEST-02 语义, 防御性)。

    symbol/name/code → MASKED_IDENTITY; 剥离 open_gap/auction_* / preopen_metrics / probe;
    保留 message/severity/window/provisional/degraded/rule_name/conditions。
    """
```
- 复用 `MASKED_IDENTITY = "******"` (:14)。
- 白名单重建风格复制 mask_guest_hub 的 masked_row 重建 (:33-45): 显式键重建 + `_GUEST_VISIBLE` 白名单 update; preopen 告警需新白名单 `{message, severity, window, provisional, degraded, rule_name, conditions, occurred_at, rule_id, source, type}`。
- 调用点: `api/pool.py` guest 路径先例 (`:173-174 if not is_vip: hub = mask_guest_hub(hub)`) — 未来 guest 可见 alerts 表面必须经 mask_guest_alert; 当前 `/api/alerts` (api/alerts.py:18-46) 为登录面无 guest 路径, 守卫语义为防御性。

### `backend/app/api/monitor_rules.py` (controller, request-response) — MON-07

**Analog:** self `get_options` :82-143

- `types` 列表 (:106-112) 追加 `{"key": "preopen", "label": "盘前异动"}`。
- 追加 `preopen_threshold_fields` — 复制 `threshold_fields` 构建 (:88-93) 模式, 但源为 `PREOPEN_ALLOWED_FIELDS`:
```python
preopen_threshold_fields = [
    {"key": f, "label": ENRICHED_COLUMNS.get(f, f)}
    for f in sorted(PREOPEN_ALLOWED_FIELDS)
]
```
中文标签零新表: `ENRICHED_COLUMNS` (pipeline.py:95 open_gap, :157-161 auction_volume/auction_amount/auction_unmatched_amount/auction_volume_ratio) 现成。
- `operators`/`scopes` 沿用; preopen 无需 ladder 的 Pro+ 能力闸门 (:145-151 不适用)。

### Tests (5 new files)

#### `tests/test_preopen_monitor_rules.py` (T1-T10, MON-01/02/04)
**Analog:** `tests/test_monitor_etf.py` + `tests/test_premarket_pool.py`
- 引擎直构 `eng = MonitorRuleEngine()` (test_monitor_etf.py:1-4 惯例)。
- 规则构造 helper 复制 `_signal_rule` 风格 (test_monitor_etf.py:33-42), 改为 `_preopen_rule(rid, field, op, value, scope)`。
- 评估帧构造: `pl.DataFrame({...})` 直构 (test_monitor_etf.py `_etf_df` :48-55); preopen 帧用 payload rows 构造。
- 隔离断言 (T7): `eng._strategy_pools` 前后相等 + `eng.latest_strategy_results()` 不变 — 直接属性断言 (test_monitor_etf.py 直探 `_history_loader_for` 先例 :6-8)。
- validate 负例: `pytest.raises(ValueError)` + 中文消息断言 (monitor_rules.py validate 抛错风格)。

#### `tests/test_preopen_scheduling.py` (T11-T16, MON-03)
**Analog:** `tests/test_premarket_pool.py`
- 注册形 grep 测试复制 `test_premarket_job_registered_in_scheduler` (:96-105 段, `assert "id=_PREMARKET_JOB_ID" in text` 形)。
- 尾段接线测试: `_FakeRepo` + `SimpleNamespace(repo=repo, strategy_engine=engine, quote_service=stub)` (复制 `_make_app_state` :57-90) + `monkeypatch.setattr` 断言 persist 后调 `evaluate_premarket_alerts(payload)` 且传内存 payload。
- fixture 集成: 复制 `_evaluate_monitors` 断言风格 — stub `operational.record_alert_event` 落库、SSE 队列、投递队列。
- 时间无重叠 (T15): 直接断言 `(9,26)` 与连续竞价窗口。

#### `tests/test_preopen_honesty.py` (T17-T18, MON-04/06)
**Analog:** `tests/test_guest_masking.py` + `operational/repository.py` round-trip
- round-trip: `record_alert_event` → `get_alert_event` (repository.py:345-403) 断言 window/provisional/degraded/probe/strategy_ids/preopen_metrics 全保留 (event_json 全量)。
- `mask_guest_alert` 快照断言: 复制 test_guest_masking.py 的字段集合断言风格 (断言 guest 可见字段集合不含 open_gap/auction_*/身份)。

#### `tests/test_preopen_ast_guard.py` (T19, MON-05)
**Analog:** `tests/test_pool_hub.py` E-guard :854-963 — **逐行复制**:
- `_EXECUTION_TOKEN` regex (:857-861) + `_imported_module_names` ast 解析 (:879-885) + `_WRITE_PATTERNS` (:863-868)。
- 扫描面按模块拆分 (RESEARCH §7): 仅扫 `strategy/preopen_eval.py` (整文件) + monitor.py 的 preopen 函数段 (ast 子集解析) + `quote_service.evaluate_premarket_alerts` 段 + `_premarket_pool_preview` 段 — 因 monitor.py 本身含执行路径 `_match_strategy`, 不能整文件扫 (OQ-5 正是为此推荐独立模块)。

#### `tests/test_preopen_api_options.py` (T20, MON-07)
**Analog:** `tests/test_premarket_pool.py` `_make_premarket_client` (FastAPI TestClient + stub 会话中间件, 结构镜像 test_guest_masking._make_guest_client)
- `GET /api/monitor-rules/options` → `types` 含 `{"key": "preopen"}`; `preopen_threshold_fields` 键集 = 5 白名单字段 (open_gap/auction_volume/auction_amount/auction_volume_ratio/auction_unmatched_amount)。

### Frontend (MON-07, P2) — `Watchlist.tsx` OFF-LIMITS

#### `frontend/src/lib/api.ts` (types)
**Analog:** self :938-1011
- `MonitorRule.type` 联合类型 (:949) 加 `'preopen'`。
- `MonitorRuleOptions` (:975-986) 加 `preopen_threshold_fields?: { key: string; label: string }[]`。
- `AlertEvent` (:1000-1011) 加可选 `window?/provisional?: boolean/degraded?: boolean/strategy_ids?: string[]/preopen_metrics?: Record<string, number|null>`。

#### `frontend/src/components/monitor/RuleEditor.tsx` (component)
**Analog:** self
- `TYPE_DEFAULT_NAME` (:26-28) 加 `preopen: '盘前异动'` (类型下拉由 options.types 驱动自动出现)。
- 字段下拉源切换 (:191 `const thresholdFields = options.data?.threshold_fields ?? []` → `type === 'preopen' ? options.data?.preopen_threshold_fields ?? [] : thresholdFields`)。
- truth 点选隐藏: `addCond('truth')` (:150-156) 与 `SignalPicker` 区 (:221-226 `selectedSignals/thresholdConds` :193-194) 对 preopen 禁用。
- 保存校验 (:115-129) 沿用 (conditions 非空 + 数值 value)。

#### `frontend/src/pages/Monitor.tsx` (component)
**Analog:** self
- `TYPE_LABEL` (:25-29) 加 `preopen: '盘前'`。
- `SOURCE_BADGE_STYLE` (:30-36) 加 `preopen` 条目 (可选配色)。
- AlertsList 渲染 (:275-443): 对 `ev.source === 'preopen'` 渲染「盘前·非最终」provisional 徽标 + `ev.degraded` 时灰标「数据降级」— 新 UI 元素, 最近似先例是投递状态 chip (`DELIVERY_LABEL` :38-44 + :392-399 badge 渲染点)。

## Shared Patterns

### 1. 持久化优先 (persist-first) — MON-03
**Source:** `quote_service.py:1266-1278` (`_evaluate_monitors`)
**Apply to:** `evaluate_premarket_alerts`
```python
operational = getattr(self._app_state, "operational", None)
persisted: list[dict] = []
if operational is None:
    logger.error("告警未持久化: operational repository 未初始化")
else:
    for event in events:
        try:
            persisted_ev = operational.record_alert_event(event)   # repository.py:345-391
            event["id"] = persisted_ev["id"]; event["occurred_at"] = persisted_ev["occurred_at"]
            persisted.append(event)
        except Exception as e:  # noqa: BLE001
            logger.warning("告警持久化失败,跳过广播和投递: %s", e)
```
落库成功才广播/投递; 失败跳过广播 (event_json 全量 round-trip 无需改表)。

### 2. cooldown 去重 — MON-02
**Source:** `monitor.py:660-685` (`_evaluate_rule`) — key=`(rule_id, symbol)`, `self._last_fire` dict, `remove_rule` 清理 :425-430 (list 快照防并发迭代)。
**Apply to:** `evaluate_premarket` (经 `_evaluate_rule` 复用, preopen rule_id 与盘中规则天然隔离)。

### 3. 诚实缺列 fail-closed — MON-01/02/04
**Source:** `monitor.py:281-303` `_build_condition_mask` (`field not in cols → df.head(0)`); `auction_columns.py:90-151` 双闸门缺列诚实; `auction_allround.py:35-38` 白名单缺列空池。
**Apply to:** 白名单校验 (validate), 评估帧构建 (`change_pct=None` 显式声明, 绝不 0 填/派生兜底), degraded payload → auction_* 规则 0 命中。

### 4. 失败非致命 (job 尾段) — MON-03
**Source:** `daily_pipeline.py:1008-1015` (`_pool_eod_persist` concept_history try/except)
**Apply to:** `_premarket_pool_preview` 尾段钩子 — warning + 不阻断 persist/`emit("done")`。

### 5. AST 守卫 (零执行隔离) — MON-05
**Source:** `tests/test_pool_hub.py:854-963` (`_EXECUTION_TOKEN`/`_imported_module_names`/`_WRITE_PATTERNS`/E1-E6)
**Apply to:** `tests/test_preopen_ast_guard.py` — 按模块/函数段拆分扫描面; `strategy/preopen_eval.py` 整文件白名单最简。

### 6. 模块 docstring 铁律 — MON-05
**Source:** `premarket_pool.py:1-18` (绝不 import 执行族 + 绝不写 strategy_cache/screener_results)
**Apply to:** `strategy/preopen_eval.py` docstring (复制铁律块)。

### 7. 诚实 skip (无状态早退) — MON-03
**Source:** `daily_pipeline.py:1027-1030` + `premarket_pool.py:74-78` (`available:false` 空态)
**Apply to:** `evaluate_premarket`/`evaluate_premarket_alerts`/尾段钩子 — 无 rules/无 results/非 available → 静默返回, 不写不告警。

### 8. 逐规则隔离评估 — MON-02
**Source:** `monitor.py:545-552` (`evaluate` 循环) — list() 快照 + 每规则 try/except + `logger.warning("规则评估失败 %s: %s", rule_id, e)`
**Apply to:** `evaluate_premarket` 逐规则循环 (单条规则异常不丢弃整轮)。

## No Exact Analog

| File / Step | Role | Data Flow | Reason / Fallback |
|---|---|---|---|
| `strategy/preopen_eval.py` 的「payload → DataFrame 输入适配」步骤 | utility | transform | 引擎至今只吃实时 enriched DataFrame (monitor.py `evaluate(df)`); JSON payload 重建帧是全新适配。最接近: `_inject_sealed_vol` (quote_service.py:1355+) 的列注入 + `auction_columns.py:146` `unique(subset=["symbol"], keep="first")`。Planner 用 RESEARCH §4.2 step 3 现成伪代码。 |
| `monitor.py` 内「独立评估入口调用独立模块」的组合 | engine | event-driven | 无先例。最近似: `set_strategy_engine`/`set_board_loader` 注入 (:385-408) + `evaluate_positions` 独立入口 (:562-616)。 |
| 前端 provisional/degraded 徽标 (Monitor.tsx) | component | event-driven | 新 UI 元素; 最近似: `DELIVERY_LABEL` 状态 chip (:38-44) + 徽标渲染点 :392-399。 |
| `mask_guest_alert` 的调用点 | utility | transform | `/api/alerts` (alerts.py:18-46) 为登录面无 guest 路径 — 调用点目前不存在, 守卫为防御性 (RESEARCH §8)。 |

## Pattern Gaps (planning notes)

1. **`evaluate_premarket` 输入适配无引擎先例** — payload rows 列并集 + 白名单保留 + `change_pct=None` + `source_strategies` 追加 + `unique(keep="first")` 的组合在代码库无直接模板; RESEARCH §4.2 step 3 提供了完整伪代码, planner 直接引用。
2. **conditions 校验重复** — RESEARCH §3.2 指出现有 validate 把 conditions 形状校验放在 else 分支内, preopen 分支需自行复制或抽 `_validate_conditions_shape` 公共 helper (三类型共用) + `_validate_condition_field` 按类型分派。这是唯一涉及「重构既有代码」的点 (其余均为纯增量)。
3. **OQ-5 决策影响守卫测试形态** — 若选独立 `strategy/preopen_eval.py`, T19 整文件白名单; 若放 monitor.py 内, T19 需 ast 子集解析 (扫描函数段)。PATTERNS.md 按独立模块推荐 (与 RESEARCH 一致)。
4. **前端 AlertEvent 字段** — `window/provisional/degraded/strategy_ids/preopen_metrics` 为纯增量可选字段, 与后端 SSE dict 追加键 (quote_service.py:1282-1305) 对齐; 旧客户端忽略未知键兼容。

## Metadata

**Analog search scope:** `backend/app/strategy/`, `backend/app/services/`, `backend/app/api/`, `backend/app/jobs/`, `backend/app/operational/`, `backend/tests/`, `frontend/src/lib/`, `frontend/src/pages/`, `frontend/src/components/monitor/`
**Files scanned:** ~15 primary + targeted greps (preopen 全局引用确认无既有实现; `Watchlist.tsx` 未触碰)
**Pattern extraction date:** 2026-08-06
**Anchors:** RESEARCH.md §13 关键锚点表 (全部经本次直读复核: monitor_rules.py validate :101-201 / monitor.py evaluate :497-560, _evaluate_rule :617-700, _match_conditions :903-930, _default_message :1005-1078 / quote_service.py _evaluate_monitors :1169-1353 / daily_pipeline.py _premarket_pool_preview :1017-1061 / guest_masking.py mask_guest_hub :20-55 / api/monitor_rules.py get_options :82-143 / test_pool_hub.py E-guard :854-963 / test_premarket_pool.py fixtures / test_monitor_etf.py engine 单测 / frontend RuleEditor.tsx + Monitor.tsx + lib/api.ts)
