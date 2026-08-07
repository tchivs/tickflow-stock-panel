# Phase 38 研究 — 分钟确认接线 BT-10 (Minute Confirm Wiring)

**Researched:** 2026-08-07
**Source:** `.planning/research/v2.4-full-universe/DEPLOY-MINUTE-LEGACY.md` §3.9/§5 (ResearcherV24C, confidence HIGH)
**Implementation-ready:** YES — seam 完整, 双接线点, 既有 hermetic 测试锚点

## Verdict

**SANDBOX-IMPLEMENTABLE NOW** — 纯代码增量 (factory + 双接线 + hermetic 测试), 空湖行为字节保持 (fail-closed); 实盘点亮 (live 日湖写) deploy-gated, 诚实注记。

## 关键代码事实 (R3 §3.9 核验)

- Seam: `StrategyEngine.__init__(..., minute_loader: Callable[[list[str], date], pl.DataFrame] | None = None)` (engine.py:154); `self._minute_loader = minute_loader` (:163)。
- 运行分支 engine.py:373-392: `minute_confirm_fn` + `evaluation_time` 存在 → `_minute_loader is None` → required 则空 StrategyResult (fail-closed), 可选则跳过确认保留日线核心池; loader 注入后: 空帧 → required 空池/可选跳过; 非空 → 单点截断 `datetime.time() <= evaluation_time` → `minute_confirm_fn(truncated)` → 保留确认 symbol (T-21-01「确认时刻之后无输入」硬验收)。
- **双未接线构造点**: `main.py:562-565` (app engine) + `advanced/governed_runner.py:63-66` (research runner, 回测脚本刻意未接线, 诚实 not_applied)。
- kline_minute 湖 = 0 分区 (空目录); canonical 列 `CANONICAL_MINUTE_COLS` (kline_sync.py:535-537)。
- 既有 hermetic 测试锚点: test_auction_strategy_family.py:31-39/59-62/146-162/199-225; test_auction_strategy_family_p2.py:222-273; test_minute_sync_verify.py。

## 最小增量 (MN-01..03)

1. **`make_minute_loader(data_dir)` factory**: 读 `kline_minute/date={as_of}/part.parquet` (canonical 列), 过滤候选 symbols, 排序; 缺分区 → 空帧 (fail-closed, 无异常吞没)。
2. **双接线**: main.py:562-565 + governed_runner.py:63-66 传 `minute_loader=make_minute_loader(data_dir)`; 空湖行为 = 今天 (required → 空 StrategyResult; optional → 跳过确认)。
3. **Hermetic 测试**: 生产 factory + fixture 分区: 空湖行为保持; 分区在场点亮 `auction_intraday_confirm` (单点截断 ≤evaluation_time); loader 只读 (零写 kline_minute); research/validation 报告保持 `minute_confirm='not_applied'` (不静默改语义)。
4. **(MN-04 P2) 文档同步**: features.md + deploy-verification.md 一行状态 (接线沙箱已落地, 点亮需 live 日湖写 — 15:30/manual 后, 非盘中 09:45; 诚实 fail-closed)。

## 诚实边界

- 湖只读加载器 = 确认只在同步后点亮 (post-sync), 绝不盘中即时 — 与「确认时刻之后无输入」语义一致, 无伪造。
- 回测/验证报告 `minute_confirm='not_applied'` 保持 — BT-10 注记存在 (Phase 37 已扩展 _MINUTE_NOTE)。
- 零新增运行时依赖; 不触碰 strategy_cache/screener_results (E3)。

## 风险

| 风险 | 等级 | 缓解 |
|---|---|---|
| 接线破坏空湖行为 | MEDIUM | 既有 hermetic 测试锚点全跑 + 新空湖测试 |
| fixture 与生产 partition 格式漂移 | LOW | factory 用 canonical 列常量 (kline_sync.py:535-537) |
| 盘中语义误读 | LOW | 文档明示 post-sync 语义 |
