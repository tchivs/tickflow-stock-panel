# 42-02-SUMMARY.md — MIN-02 统计口径双报告 (Wave 2)

**Phase:** 42-minute-lake-expansion · **Wave:** 02 (MIN-02) · **Date:** 2026-08-07
**Executor:** ExecP4202 · **Status:** DONE — 4 commits (T1 RED→GREEN, T2 feat, T3 feat), test_auction_validation_report.py 27/27 + test_verify_auction_backfill.py 13/13 全绿, wave 合并 57 passed (含 test_auction_sync.py canonical 排除回归 test_0930_excluded)

## 交付物

| Artifact | Path | 说明 |
|---|---|---|
| `_minute_stats_coverage` digest | `backend/app/services/auction_validation.py` | 统计口径覆盖 digest (caliber=statistical_minute_0930): symbol 覆盖 / 解锁门 (0.94) / dates_covered / universe_size / 量额字段 — 镜像 `_coverage_symbols` 骨架 (glob date=* + `_dir_date` 窗口过滤 + fail-closed skip T-29-01-05) |
| coverage.minute_stats 接线 | `backend/app/services/auction_validation.py` | build_report coverage 块新增 `minute_stats` 键, 与 canonical `symbols` 键并列, 绝不相加; universe = verification_panel symbol unique (与 canonical 同宇宙可比) |
| amount 诚实派生 | `backend/app/services/auction_validation.py` | 09:30 bar 量恒等手求和; OHLC 全等 → `volume×close×100` 派生 (契约 521×1328.36×100≈69,207,556 闭合); 非全等 → `amount_unknown_count`, 绝不猜 |
| `_empty_report` minute_stats 块 | `backend/app/services/auction_validation.py` | 空态与实态同键形状 (D-02): 全 0 + unlock_met False + dates_covered [] |
| verify [6] 并列行 | `backend/scripts/verify_auction_backfill.py` | `_minute_stats` helper (镜像 `_lake`) + 并列打印 `minute_stats: {m}/{uni} = {r:.3f} (dates={d}, caliber=statistical_minute_0930)`; 分母 = 运行期 universe (A4 动态, 不硬编码) |
| 契约测试 ×10 | `backend/tests/test_auction_validation_report.py` (7) + `backend/tests/test_verify_auction_backfill.py` (3) | 双口径并列 / 09:30-only / 空态 / 解锁门 / amount 三契约 / verify 三守卫 |

## Commit 链 (RED → GREEN 可回溯)

| Commit | Sha | 内容 |
|---|---|---|
| T1 (RED) | `16f50a4` | test(42-02): 统计口径 digest 契约 — 4 用例红 (`KeyError: 'minute_stats'`) |
| T1 (GREEN) | `7dc5b82` | feat(42-02): `_minute_stats_coverage` + coverage.minute_stats 接线 — 4/4 绿 (量额占位 0) |
| T2 (feat) | `f8c7325` | feat(42-02): 统计口径 amount 派生 (OHLC 全等闭合 / 非全等 UNKNOWN) + 3 契约测试 — 27/27 绿 |
| T3 (feat) | `9d59cb7` | feat(42-02): verify [6] 并列统计口径覆盖行 + 双口径守卫测试 — 13/13 绿 |

## Verify 命令输出摘录

**T1 (RED):**
```
tests/test_auction_validation_report.py::test_minute_stats_block_dual_caliber_parallel - AssertionError: ... 'minute_stats' in {...}
tests/test_auction_validation_report.py::test_minute_stats_only_0930_rows - KeyError: 'minute_stats'
... 4 failed, 20 deselected
```

**T2 (RED, 占位 0 实锤):**
```
test_minute_stats_amount_mixed_symbols - assert 0.0 == 69207556.0 ± 1
3 failed, 24 deselected
```

**Wave 合并 (最终):**
```
tests/test_auction_validation_report.py tests/test_verify_auction_backfill.py tests/test_auction_sync.py
57 passed in 5.86s
```

**Live 冒烟 (真实湖, 读侧只读):**
```
[6] coverage:      auction_symbol_count/5538 = 0.008 — PARTIAL
minute_stats: 0/5538 = 0.000 (dates=0, caliber=statistical_minute_0930) — PARTIAL
verdict: PARTIAL — ... (exit 1)
```
统计口径诚实空态 (kline_minute 湖尚无分区), 双口径并列打印, "100%" 绝不出现。

## 契约锁死点 (MIN-02)

- **双口径并列**: `coverage.symbols` (canonical) 与 `coverage.minute_stats` (统计) 两独立键并存, 各按自身口径 (测试断言 2 ≠ 3 且互不相加); `minute_stats["caliber"] == "statistical_minute_0930"` 逐字标注。
- **09:30-only**: `datetime.dt.time() == time(9, 30)` 过滤; 09:31/14:59 行绝不进统计口径 (symbol 覆盖 + dates_covered 均排除; 无 09:30 行的分区不入 dates)。
- **amount 诚实派生**: OHLC 全等 (open==high==low==close) → `auction_amount_yuan += volume×close×100` — 契约测试断言 `pytest.approx(69_207_556.0, abs=1.0)` (521×1328.36×100 精确闭合, RESEARCH live 实测); 非全等 → `amount_unknown_count`, 绝不猜。
- **解锁门可观测**: `unlock_threshold == 0.94` (FA-04/RC-02) + `unlock_met` bool; 3/3 → True, 1/3 → False (诚实 partial, 不假解锁)。
- **verify [6] 并列行**: canonical 行与 `minute_stats: {m}/{uni} = {r:.3f} (dates={d}, caliber=statistical_minute_0930)` 独立打印; 分母 = 运行期 `uni["total"]` (动态, 不硬编码 5537/5538); "100%" 字符串守卫对双口径同时生效 (满覆盖打印 1.000)。
- **canonical 湖排除保持**: 统计口径零写 kline_auction (只读 glob); `test_0930_excluded` 绿 (wave 合并 57 passed 内含); 退出码语义不因统计空态改变 (PARTIAL 判定只看 canonical)。

## 计划偏差

1. **量额字段未按计划分两次提交**: PLAN Task 1 注「量/额字段 Task 2 填充, 本任务先置 0 占位」— 已忠实执行: `7dc5b82` 返回 0 占位 (T2 RED 测试即以此实锤占位), `f8c7325` 替换为真实派生。提交边界与计划一致 (4 commits)。
2. **verify 打印格式微调对齐 PLAN 字面**: 首次实现带 `rows=` 字段 + 缩进对齐, 与 PLAN 指定格式 `minute_stats: {m}/{uni} = {r:.3f} (dates={d}, caliber=...)` 不一致 → 测试红 → 按 PLAN 字面修正 (rows 仍由 `_minute_stats` helper 计算, 供未来使用, 不打印)。行为测试按 PLAN 格式断言。
3. **column guard 扩面**: 计划只要求 datetime/symbol 列检查; 实现额外要求 volume/open/high/low/close (派生所需列), 缺列分区 fail-closed skip — T-29-01-05 纪律延伸, 防派生中途异常冒泡 500。

## 约束复核

- **零新增依赖**: 无 pyproject/uv.lock 改动; polars/time 均为既有面。
- **Watchlist 零触碰**: `frontend/src/pages/Watchlist.tsx` 保持唯一 unstaged 改动, 未被我修改。
- **既有契约零破坏**: canonical coverage 块零改动; `_empty_report` 只加键; 端点 (research_auction.py:67) 零改动, digest 自动透传 (读代码核实); 退出码语义不变。

## 协作注记

- 与 ExecP4203 (42-03, wave 3) 经 IRC 锁定 digest 键集契约: 其 `minute_source` kwarg → `minute_stats["source"]` + `_empty_report` 的 `"source": "unknown"` 键加在本次提交之上, 无键冲突; 其 Task 2 在 42-02 提交后落位。
- 全量回归 `pytest tests/` 由 orchestrator 统一收口 (本 wave 只跑 42-02 相关文件 + canonical 回归族)。
