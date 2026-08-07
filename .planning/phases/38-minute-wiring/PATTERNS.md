# Phase 38 模式映射 (Patterns)

**Mapped:** 2026-08-07 (orchestrator, from R3 doc + repo reads)

| # | 需求对象 | 现有模式 (file:line) | 复用方式 |
|---|---|---|---|
| 1 | factory (MN-01) | `CANONICAL_MINUTE_COLS` (kline_sync.py:535-537); 湖读 `pl.read_parquet(data_dir / "kline_minute" / f"date={as_of}" / "part.parquet")` | `make_minute_loader(data_dir)`: 缺目录/文件 → 空帧 (pl.DataFrame(columns=canonical)); 过滤 candidates; sort |
| 2 | 接线 (MN-02) | engine.py:154/163 (minute_loader param); 分支 :373-392 (None → required 空/optional 跳过; 非空 → `dt.time() <= evaluation_time` 截断); 双构造点 main.py:562-565 + advanced/governed_runner.py:63-66 | 传 `minute_loader=make_minute_loader(repo.store.data_dir)`; 零行为改动 |
| 3 | hermetic 测试 (MN-03) | test_auction_strategy_family.py:31-39/59-62/146-162/199-225 (空 loader 行为); test_auction_strategy_family_p2.py:222-273; test_minute_sync_verify.py; module-object monkeypatch; tmp_path fixture | 新测试文件嵌 token (minute_loader/empty/truncate); 空湖行为-保持 + 分区在场点亮 + 截断 + 只读 |
| 4 | 报告不变 (MN-03) | research/validation `minute_confirm='not_applied'` (Phase 34); _MINUTE_NOTE (auction_backtest.py:66-71) | 断言报告键不变; 不接线 research runner 语义 (governed_runner 接线仅引擎路径?) — 按 plan 裁决, 缺省: 两端都接, 报告语义不动 |
| 5 | 文档 (MN-04) | docs/features.md 分钟节 (Phase 32 AQ-06 defer); docs/deploy-verification.md (D 清单) | 一行状态更新 (接线落地/点亮 gate); 无 `## ` header 漂移 |
| 6 | 测试惯例 | `cd backend && .venv/bin/python -m pytest`; token 名; 零新依赖 | 照此 |

## 契约

- `make_minute_loader(data_dir: Path) -> Callable[[list[str], date], pl.DataFrame]` — 签名与 engine 期望一致 (candidates: list[str], as_of: date)。
- 空帧列 = canonical 列集 (不 dtypes 强制 — 生产 fixture 为准)。
- 截断语义: `truncated = frame.filter(pl.col("datetime").dt.time() <= evaluation_time)`; 空截断 → required 空池/optional 跳过 (与空帧一致)。
- 双构造点接线后, 空湖路径行为与未接线时字节一致 (测试断言)。
- 零新 import 冲突 (engine 已 import 所需)。
