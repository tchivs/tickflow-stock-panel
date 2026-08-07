# 38-SUMMARY — 分钟确认接线 BT-10 (Phase 38, MN-01..04) 阶段总结

**Phase**: 38 分钟确认接线 BT-10 (Minute Confirm Wiring)
**Executed**: 2026-08-07 (ExecutorP3801 wave-1 + ExecutorP3802 wave-2 + ExecutorP3803 wave-3)
**Commits**: `4380545` (38-01, MN-01+MN-03: 工厂 + hermetic 测试 + 锚点基线) · `2f8629e` (38-02, MN-02: 双接线 + 字节保持证明) · `38-03` (MN-04: 文档同步, 本文档)

## 1. Goal

接线 BT-10 分钟确认层: 把 `kline_minute` 湖只读加载封装为 `make_minute_loader(data_dir)` 工厂, 接入两个生产构造点 (app 引擎 main.py + research runner governed_runner.py), 以 hermetic 测试证明空湖行为逐字节保持 (fail-closed), 并以文档同步交付诚实点亮语义 (live 日湖写, post-sync, 非盘中)。需求 MN-01 (工厂) / MN-02 (双接线) / MN-03 (hermetic 测试) / MN-04 (P2 文档同步) 全部交付。

## 2. 验收映射

| Req | 交付物 | 验证命令 | 结果 |
|---|---|---|---|
| MN-01 工厂 | `backend/app/services/minute_loader.py` (50 行, 只读: canonical 列分区读 + `is_in` 候选过滤 + `sort(["symbol","datetime"])`; 缺分区/损坏分区 → canonical 列集空帧 fail-closed, 损坏附 `logger.warning` 不静默; 零写面) | 38-01 T2: `cd backend && .venv/bin/python -m pytest tests/test_minute_loader_wiring.py -q` | 8 用例全绿 (7 计划 + W6 损坏分区 fail-closed 附加) |
| MN-02 双接线 | `backend/app/main.py:551/567` `minute_loader=make_minute_loader(store.data_dir)` (本地 import 与 ScreenerService 同类形); `backend/app/advanced/governed_runner.py:55/72` `minute_loader=make_minute_loader(data_dir)` (import 严格留在 `_service()` 内, 模块顶层零新增 import) | 38-02 T3 结构门 (`test_main_wired_minute_loader` / `test_governed_runner_wired_minute_loader`) + T4 `test_wired_empty_lake_byte_identical_to_unwired` | 全绿 — 接线后空湖 required/optional 与 `minute_loader=None` 基线逐字段一致 (`strategy_id`/`total`/`rows`/`scores`, `elapsed_ms` 除外), 含缺分区态 |
| MN-03 hermetic 测试 | `backend/tests/test_minute_loader_wiring.py` (11 用例, tokens: `minute_loader`/`empty`/`truncate`/`readonly`) | 38-01 T2 + 38-02 T3/T4: `cd backend && .venv/bin/python -m pytest tests/test_minute_loader_wiring.py -q` | 11 全绿 — 空湖 required→空 StrategyResult / optional→跳过确认保留日线核心池; 分区在场点亮真实 `auction_intraday_confirm` + 单点截断 `datetime.time() <= 09:45` (T-21-01, W2 monkeypatch 先于引擎构造); 只读 sha256+mtime 树快照逐字节一致 + 空湖态不创建目录; 模块零写面结构门 |
| MN-04 (P2) 文档同步 | `docs/features.md` BT-10 bullet 行内追加一句 + `docs/deploy-verification.md` D8 追加一条观察 bullet + 本文档 | 38-03 T4: `git diff --stat docs/` + header 漂移 grep | 见 §3/§4 — diff 仅两文件 (features.md +1 / deploy-verification.md +1), `^[+-]## ` header 漂移 = 0 (W1 修正命令) |

**行为保持证明 (38-02 T5, 接线后复跑 38-01-BASELINE.md 同五条命令)**: cmd1=4/12, cmd2=3/8, cmd3=4, cmd4=1/8, cmd5=4/16 → 与接线前基线逐字节一致 (**16 passed**); not_applied 报告语义锚点 (`test_full_backtest_minute_annotation_and_manifest` backtest:455 + validation_report:159/564/794/1054) 复跑不变。**全量回归 (T6)**: 1797 passed, 4 skipped — engine/backtest/validation/report 零改动, 仅引擎构造参数。

## 3. 证据清单

**新文件**:
- `backend/app/services/minute_loader.py` — MN-01 工厂 (commit `4380545`)
- `backend/tests/test_minute_loader_wiring.py` — 11 hermetic 用例 (38-01 8 用例 + 38-02 3 用例, commits `4380545`+`2f8629e`)
- `.planning/phases/38-minute-wiring/38-01-BASELINE.md` — 接线前 5 anchor 命令通过数耐久基线 (16 passed)
- `.planning/phases/38-minute-wiring/38-03-SUMMARY.md` — 本文档

**改动文件**:
- `backend/app/main.py` (+2: 本地 import + 构造参数, commit `2f8629e`)
- `backend/app/advanced/governed_runner.py` (+2: 同上, commit `2f8629e`)
- `docs/features.md` (+1: BT-10 bullet 行内追加, 本 wave)
- `docs/deploy-verification.md` (+1: D8 bullet 追加, 本 wave)

**运行命令与结果** (全部实测):
- 38-01: `cd backend && .venv/bin/python -m pytest tests/test_minute_loader_wiring.py -q` → 8 passed; 5 anchor 命令 → 16 passed (存档 38-01-BASELINE.md)
- 38-02: 接线后 5 anchor 命令复跑 → 同通过数 16; `tests/test_minute_loader_wiring.py` → 11 passed; 全量 `pytest -q` → 1797 passed, 4 skipped
- 38-03: `git diff --stat docs/` → 仅 features.md + deploy-verification.md; `git diff docs/features.md docs/deploy-verification.md | grep -c '^[+-]## '` → 0

## 4. 诚实边界

- **点亮未验证 (deploy-gated)**: `kline_minute` 湖当前 **0 分区** → 接线后的运行时行为 = 空湖 fail-closed (required → 空池 / optional → 跳过确认), 字节保持证明覆盖此态; 真点亮 (分区在场 + `auction_intraday_confirm` 非空) 只在 live 日湖写后发生, 沙箱不可验证。
- **确认 = 同步后 (post-sync) 语义, 绝非盘中**: 湖只读加载器 = 确认只在同步后点亮 (15:30 EOD 管道或手动同步), 与「确认时刻之后无输入」T-21-01 语义一致; 两处文档均明示「非盘中 09:45」。
- **报告语义冻结**: 回测/验证报告 `minute_confirm='not_applied'` 保持 (auction_backtest.py:66 `_MINUTE_CONFIRM` / auction_validation.py:434 硬编码, 本 phase 零改动, not_applied 锚点复跑证明)。
- **零新增运行时依赖**: 工厂仅 stdlib (logging/datetime/pathlib) + 既有 polars/kline_sync 常量; 不触碰 strategy_cache/screener_results (E3)。
- **W4 — probe_phase13 第三构造点未接线 (by design)**: `backend/scripts/probe_phase13.py:59-62` 存在第三个 `StrategyEngine` 构造点, 保持 `minute_loader=None` — 与 MN-02 命名范围 (main.py + governed_runner.py) 一致; None → 与接线前相同的 fail-closed 路径, 行为正确。38-02 结构门只锁定两个命名站点, 不覆盖该 probe (未来「接线所有站点」重构需另加门)。

## 5. 遗留

- **点亮验证待 live 日**: 真实点亮观察项已写入 deploy-verification.md D8 (post-sync 分区存在 + `auction_intraday_confirm` 非空), 属部署侧观察, 非沙箱可测。
- **BT-10 P2 验收口径不变**: 注解诚实 (非实现分钟) — 分钟 248 日回填保持 CLOSED; features.md BT-10 bullet 已同步接线现状, 措辞维持「接线落地 / 点亮前置 = live 日湖写」二分。
- **全量验证收尾**: 38-02 T6 全量 (1797 passed, 4 skipped) 已由 wave-2 执行; orchestrator 可按需复跑确认。
