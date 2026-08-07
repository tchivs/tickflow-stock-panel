# 42-03-SUMMARY.md — MIN-03 诚实标注 + 源插件 seam + checkpoint (Wave 3)

**Phase:** 42-minute-lake-expansion · **Wave:** 03 (MIN-03) · **Date:** 2026-08-07
**Executor:** ExecP4203 · **Status:** T1/T2 DONE — 2 commits, 5 新增契约测试全绿; Task 3 checkpoint:human-verify **PRESENTED (awaiting 用户源决策)** — 机制交付证据齐备, 覆盖现状诚实核实, 三选一待决

## 交付物

| Artifact | Path | 说明 |
|---|---|---|
| `_MINUTE_NOTE` 诚实更新 | `backend/app/services/auction_backtest.py` | 移除过期「kline_minute 历史 CLOSED / 其 hits 不随湖覆盖增长 (52,591 恒定)」表述 (扩湖后不再真实, RESEARCH State of the Art Deprecated); 保留恒真语义 (minute 确认恒空 BT-10 / branch=real 仅消费 open_gap); 新增 09:30 bar = 集合竞价统计 (非逐笔) 按统计口径 (caliber=statistical_minute_0930) 进报告, 绝不算逐笔/绝不写 canonical 湖, 实际覆盖以 `coverage.minute_stats.dates_covered` 为准 (覆盖 = 源插件深度) |
| manifest 断言同步 | `backend/tests/test_auction_backtest.py` | :488-489 旧锚点「不随湖覆盖增长」移除; 新锚点「集合竞价统计」「统计口径」「dates_covered」断言 + 保留 `"kline_minute" in minute_note`; 其余断言零改动 |
| `MINUTE_SOURCE_PROFILES` 注册表 | `backend/app/services/kline_sync.py` | 4 profile (tushare-stk_mins / tencent-mkline / tdx-pytdx / canned-fixture), 字段 `{label, depth_note, has_0930_bar, amount_available}`, 值 = 42-RESEARCH Pattern 1 实测矩阵冻结; tdx-pytdx `has_0930_bar == False` 锁死 (09:31 合并根实测) |
| `source_label` 透传 | `backend/app/services/kline_sync.py` | `backfill_minute_history` kwargs 末尾新增 `source_label: str | None = None` (契约经 IRC 与 ExecP4201 锁定); 非 None → 完成时 `logger.info("minute backfill done: source=%s written=%d skipped=%d")` — 通道身份进日志/台账, 湖无 provenance 列铁律 |
| `--source-label` CLI | `backend/scripts/backfill_minute_driver.py` | argparse 新增 `--source-label` (profile 键之一) 透传驱动; 终态台账 dict 新增 `"source"` 键 (缺省 None 诚实不声明); docstring 用法/诚实声明更新 |
| digest 源身份 | `backend/app/services/auction_validation.py` | `build_report` 新增 kwarg `minute_source: str | None = None` → `_minute_stats_coverage(..., minute_source=)` → `minute_stats["source"] = minute_source or "unknown"` (诚实默认, 绝不猜源); `_empty_report` minute_stats 块同键补 `"source": "unknown"` (空态与实态同形状) |
| 契约测试 ×5 | `backend/tests/test_minute_backfill_idempotency.py` (2) + `backend/tests/test_auction_validation_report.py` (2) + `backend/tests/test_backfill_minute_driver.py` (1) | profile 注册逐字断言 (tdx 09:30✗ 锁死) / 驱动 caplog 透传 (非 None 含 label, None 不崩无日志) / digest 缺省 unknown / digest 声明 tencent-mkline / CLI 台账 source 透传 (None → null) |

## Commit 链

| Commit | Sha | 内容 |
|---|---|---|
| T1 | `48277da` | feat(42-03): `_MINUTE_NOTE` 扩湖诚实更新 + manifest 断言同步 |
| T2 | `b819e9b` | feat(42-03): 源插件 seam — profile 注册 + source_label 透传 + digest 源身份 (覆盖不虚报) |

## Verify 命令输出摘录

**T1 契约 (新锚点断言):**
```
tests/test_auction_backtest.py -k minute_annotation
1 passed, 8 deselected
```

**T1 诚实回归族 (零改动保持绿):**
```
tests/test_auction_sync.py tests/test_auction_validation_report.py -k "0930 or minute_stats" \
tests/test_auction_strategy_family.py tests/test_auction_strategy_family_p2.py
64 passed
tests/test_auction_strategy_family.py tests/test_auction_strategy_family_p2.py -k truncation   # T-21-01
2 passed
tests/test_auction_probe.py
15 passed, 1 skipped
```

**T2 seam 契约:**
```
tests/test_minute_backfill_idempotency.py tests/test_auction_validation_report.py -k "source or profile"
4 passed
tests/test_backfill_minute_driver.py
5 passed
```

**Wave 合并级 (42-01..03 verify 套件):**
```
tests/test_minute_backfill_idempotency.py tests/test_auction_validation_report.py \
tests/test_verify_auction_backfill.py tests/test_auction_backtest.py tests/test_backfill_minute_driver.py
66 passed
tests/test_auction_sync.py tests/test_auction_strategy_family.py tests/test_auction_strategy_family_p2.py tests/test_auction_probe.py
59 passed, 1 skipped
```

**Live 冒烟 (真实湖, verify [6] 双口径 — 覆盖现状核实):**
```
[6] coverage:      auction_symbol_count/5538 = 0.008 — PARTIAL
minute_stats: 0/5538 = 0.000 (dates=0, caliber=statistical_minute_0930) — PARTIAL
verdict: PARTIAL — ... (exit 1)
```
canonical 0.8% 与统计口径 0 (kline_minute 湖尚无分区) 各自如实并列, "100%" 绝不出现。

## 契约锁死点 (MIN-03)

- **诚实标注**: manifest `minute_note` 含「集合竞价统计」「统计口径」「dates_covered」新锚点 (测试断言); 旧「历史 CLOSED / 不随湖覆盖增长」表述物理消失; 恒真语义 (BT-10 minute 恒空 / branch=real 仅 open_gap) 保留。
- **诚实回归零改动保持绿**: canonical 555..565 排除 / `test_0930_excluded` / probe 窗口 09:15-09:25 / T-21-01 evaluation_time 截断族 — 统计口径只加报告面, 绝不动写湖/探针 (全部零改动, 绿)。
- **源插件 seam**: `MINUTE_SOURCE_PROFILES` 恰 4 键, 每 profile 字段集 == `{label, depth_note, has_0930_bar, amount_available}` 逐字断言; `tdx-pytdx has_0930_bar is False` 锁死 (09:31 合并根 521+644 手实测); tencent-mkline depth_note 含「≈3 交易日」且 amount_available False (无 amount 列)。
- **source_label 透传**: 非 None → 完成日志含 label + written/skipped 计数 (通道身份进日志/台账); 缺省 None 不崩且无 label 日志; CLI 台账 `source` 键缺省 null (诚实不声明)。
- **digest 源身份**: `minute_stats["source"]` 缺省 `"unknown"` (诚实默认, 湖无 provenance 列 — 报告不猜源); 声明 `minute_source="tencent-mkline"` → 如实标注; `_empty_report` 同键形状。
- **覆盖不虚报**: 腾讯 3 日深度 → dates_covered 只含实际分区 + source 标注 (RESEARCH Pitfall 2「3 日假象」被显式暴露); 覆盖声明 = 源插件深度, 绝无「机制可测冒充源覆盖达标」。

## 计划偏差

1. **T2 测试文件分布按契约落位**: PLAN 行为列表 4 用例 — profile 注册 + 驱动透传落 `test_minute_backfill_idempotency.py`, digest 缺省/声明落 `test_auction_validation_report.py`; 额外补 1 个 CLI 台账透传测试 (`test_backfill_minute_driver.py`, 镜像 42-01 CLI 测试惯例) 锁 `--source-label` → 台账 `source` 键 (null 缺省) — 超出 PLAN 最小集但属同一 seam 契约面, 零新增依赖。
2. **caplog 断言用 `"written" in caplog.text` 而非精确计数**: 日志行格式 `source=%s written=%d skipped=%d` 逐字断言 label 即可, 计数语义由驱动测试 (42-01) 已覆盖; 不重复锁格式细节。
3. **Task 3 (checkpoint) 为呈现态**: 本 executor 完成机制证据汇总 + 覆盖现状核实 + 三选项文档化 (见下); 用户决策经 orchestrator 门后, 真实源动作 (option a/b) 属门后执行面, 不在本 wave 代码内。

## checkpoint:human-verify — 源决策与覆盖声明门 (MIN-01 source-gated, 与 FA-04 同构)

**机制交付证据 (门前全部核实):**
- 42-01 verify: `test_minute_backfill_idempotency.py` 全绿 (端到端/幂等/增量/空态/异常 fail-closed/universe 动态)
- 42-02 verify: `test_auction_validation_report.py` + `test_verify_auction_backfill.py` 全绿 (双口径 digest / amount 派生 / verify [6] 并列)
- 42-03 verify: 本 wave 5 新测试 + 诚实回归族全绿 (T-21-01 截断 / canonical 排除 / probe 窗口)

**覆盖现状 (verify [6] 实测):** canonical `44/5538 = 0.008 — PARTIAL`; minute_stats `0/5538 = 0.000 (dates=0)` — kline_minute 湖无分区, 双口径如实, 无虚报。

**本环境源覆盖实测封顶 (42-RESEARCH):** Tushare stk_mins 频限 1 次/小时 (两次 40203) / 腾讯 mkline ≈3 交易日 / TDX ≈90 交易日且无 09:30 bar (09:31 合并根) / 东财不可达 — 真实源全量回填本环境不可执行, 机制零源依赖已交付 (canned 夹具全测)。

**源决策三选一 (待用户, 决定真实覆盖):**
- **option-a 升级 Tushare token 档位** (stk_mins ≥ 200/min): 凭证侧动作后服务端 CLI backfill-minute 全量填充 stockdb 湖 → AQ 驱动 5537×1 GET @120/min 读侧 ≈46min (仅读侧节奏, 非端到端承诺)
- **option-b 部署目标机 (3018) 重探源深度** (境内腾讯/东财可能更深; 复用 42-RESEARCH 探针形态, 登记 DEP-01/44 前置 runbook 项): 按实测深度填充, 覆盖 = 实测, digest dates_covered/source 如实
- **option-c 保持机制态**: 覆盖声明为 source-pending (FA-04 统计口径门不冒充解锁, 双口径并列如实), 待凭证/环境变化后经 42 源决策重开

**门后铁律 (无论选哪项):** 覆盖报告/verify [6] 均按实际分区与源身份诚实声明 (覆盖 = 源插件深度); 绝不以机制可测冒充源覆盖达标。

## 约束复核

- **零新增依赖**: 无 pyproject/uv.lock 改动; 全部既有面 (polars/logging/argparse)。
- **Watchlist 零触碰**: `frontend/src/pages/Watchlist.tsx` 保持唯一 unstaged 改动, 未被我修改。
- **既有契约零破坏**: `build_report` 新增 kwarg (向后兼容); `_minute_stats_coverage` 只加键 (42-02 契约经 IRC 锁定, 无冲突); canonical 写湖/探针/截断族零改动; 驱动签名只加 kwargs 末尾可选参数 (ExecP4201 契约确认)。

## 协作注记

- 与 ExecP4201 (42-01) 经 IRC 锁定 `backfill_minute_history` 签名 + CLI 契约: `source_label` 加 kwargs 末尾; `--source-label` 加 argparse; 其 driver 提交 `e4fc8b4` 后我落位, 无文件冲突。
- 与 ExecP4202 (42-02) 经 IRC 锁定 `_minute_stats_coverage` 键集 + `_empty_report` 形状: 我的 `source` 键加在其提交之上, 无键冲突; 其 digest 契约于 `7dc5b82`/`f8c7325` 落地。
- 全量回归 `pytest tests/` 由 orchestrator 统一收口 (本 wave 只跑 42-03 相关 + 诚实回归族)。
