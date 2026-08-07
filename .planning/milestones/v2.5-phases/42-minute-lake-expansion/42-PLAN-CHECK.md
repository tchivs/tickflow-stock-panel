# Phase 42 Plan Check — 分钟湖扩湖 (Minute Lake Expansion)

**Checked:** 2026-08-07 · **Plans:** 42-01 / 42-02 / 42-03 · **Method:** goal-backward (gsd-plan-checker 惯例), 只读评审, 零代码修改
**参照物:** REQUIREMENTS.md MIN-01..03 · ROADMAP Phase 42 (3 success criteria) · 42-RESEARCH.md (492 行全读) · PATTERNS.md · 既有源码/测试逐条核实 (kline_sync / stockdb_provider / auction_validation / verify_auction_backfill / auction_backtest / test_minute_sync_verify / test_auction_backtest / test_auction_validation_report / test_verify_auction_backfill / repository)

---

## Verdict: **EXECUTABLE**

0 blockers · 6 warnings · 3 info。零源依赖机制全部可测; 源覆盖诚实 gate 化 (checkpoint:human-verify); 计划未触碰 `frontend/src/pages/Watchlist.tsx`; 46min 未进入任何验收 (RESEARCH CRITICAL 遵守)。

## D1 — Goal-backward: 每 success criterion → 可观测验收 (反向无孤儿)

| ROADMAP Success Criterion | 覆盖 Plan/Task | 可观测验收 | 状态 |
|---|---|---|---|
| SC1: backfill-minute 落 kline_minute 分区; 增量续跑幂等 (源覆盖 source-gated) | 42-01 T1/T2/T3 | 驱动 canned 端到端落盘 + 重跑 skipped + upsert 行数不变; per-symbol [latest+1day, end] 增量; universe 动态; CLI exit 0/2; 覆盖声明交 42-03 门 | ✅ |
| SC2: 09:30 bar 集合竞价统计进覆盖报告 (独立统计口径, 绝不算逐笔) | 42-02 T1/T2 + 42-03 T1 | coverage.minute_stats 键 (caliber=statistical_minute_0930) 与 canonical symbols 键并列; 09:30-only 过滤; amount 派生闭合 69,207,556; _MINUTE_NOTE 标注非逐笔 | ✅ |
| SC3: FA-04/RC-02 统计口径解锁门 ≥0.94 或诚实 partial | 42-02 T1/T3 + 42-03 T3 | digest unlock_threshold=0.94 + unlock_met; 未达 → 诚实 partial 双口径并列; verify [6] 统计行独立打印; checkpoint 门防冒充解锁 | ✅ |

**反向孤儿检查:** 全部 9 任务可回溯到 MIN-01..03 与 SC1..3, 无孤儿任务; 需求覆盖 MIN-01✅ MIN-02✅ MIN-03✅ (MIN-01 机制 = 42-01, 源 seam/门 = 42-03 T2/T3; MIN-02 = 42-02; MIN-03 = 42-03 T1)。42-02 与 42-01 零文件重叠 → wave 1 并行 (机制双轨: 驱动与报告 digest 各自独立可测)。

## D2 — 依赖/顺序

- **wave 1** = 42-01 (`depends_on: []`) + 42-02 (`depends_on: []`): 零 `files_modified` 重叠 (42-01: kline_sync/CLI/幂等测试; 42-02: auction_validation/verify/报告测试) → 并行合法。digest 测试直接种子 `kline_minute` 分区, 不依赖驱动存在; 驱动测试注入 canned fetch, 不依赖 digest — 真并行。
- **wave 2** = 42-03 (`depends_on: [42-01, 42-02]`): 共享 `kline_sync.py` (source_label, 42-01 交付物) + `auction_validation.py` (digest source, 42-02 交付物) → 隐式依赖强制顺序, 无环, 无前向引用。
- 42-03 任务顺序: T1 (标注文本) → T2 (seam) → T3 (checkpoint 门) — T2 的 digest source 注入点在 42-02 交付的 minute_stats 块上, 正确; T3 门住真实源执行, 门后才有真实覆盖动作。
- 42-03 `autonomous: false` (T3 blocking checkpoint) — 正确。

## D3 — 风险覆盖 (RESEARCH 遗留逐项)

| RESEARCH 遗留 | PLAN 处理 | 状态 |
|---|---|---|
| [CRITICAL] Pitfall 1: Tushare 40203 频限被当真空吞错 | 42-01 T2 fetch 异常上抛 fail-closed (绝不伪空/伪 skip) + CLI exit 2 (T-42-01-01) + 42-03 T3 门 | ✅ |
| [CRITICAL] Pitfall 2: TDX/腾讯深度与 09:30 语义错配 | 42-03 T2 MINUTE_SOURCE_PROFILES (tdx has_0930_bar=False 锁死) + digest dates_covered/source 显式暴露深度 (腾讯 3 日假象) | ✅ |
| [HIGH] Pitfall 3: 端日语义再踩 (end 不含当日) | 42-01 驱动 fetch 缺省 = stockdb_provider.get_minute (end+1day 内置), 驱动不得手拼 URL — PATTERNS/42-01 T1 action 显式禁止 | ✅ |
| [HIGH] Pitfall 4: 幂等跳过误伤 (全局 last_dt vs per-symbol) | 42-01 T2 `_latest_minute_dates` per-symbol GROUP BY (镜像 :735 查询面); 全局 `_latest_minute_datetime` 不用于驱动 | ✅ |
| [MEDIUM] Pitfall 5: 09:30 amount 语义混淆 | 42-02 T2 OHLC 全等 → vol×close×100 (契约 69,207,556); 非全等 → UNKNOWN 计数 | ✅ |
| [MEDIUM] Pitfall 6: 既有诚实回归被扩湖误伤 | 42-03 T1 诚实回归族保持绿清单 (test_0930_excluded / probe 窗口 / 截断族); minute_note 断言随新文本更新 (两处同步) | ✅ |
| Open Q1: Tushare token 档位升级 | 42-03 T3 checkpoint option-a (凭证侧动作 + 升级后跑全量; 46min 仅读侧) | ✅ |
| Open Q2: 部署机 3018 源深度重探 | 42-03 T3 option-b + DEP-01/44 前置 runbook 登记 (T-42-03-04) | ✅ |
| A4: 5537 vs 5538 分母漂移 | 42-01 T2 `_resolve_minute_universe` + 42-02 T3 运行期 `uni["total"]` — 不硬编码 | ✅ |
| RESEARCH 骨架 `self._date_range` | 不存在 — 42-02 T1 改为 `_coverage_symbols` 同款 glob+`_dir_date` 模式 (W1) | ✅ |
| 46min 当端到端验收 (CRITICAL 反模式) | 42-01 objective/success_criteria 显式排除; CLI docstring 诚实声明指引 | ✅ |

## D4 — 可执行性 (行号核对证据表)

| 计划引用 | 源码实测 | 判定 |
|---|---|---|
| kline_sync.py :892-912 分区写循环 (写面抽取源) | sync_and_persist_minute partition_by("_trade_date") → concat existing → unique(subset=["symbol","datetime"], keep="last") → sort → _atomic_write_parquet, :885 `if df.is_empty(): return 0` | ✅ 一致 |
| kline_sync.py :735 `_latest_minute_datetime` (per-symbol 变体镜像) | `repo.execute_one("SELECT max(datetime) FROM kline_minute")`; repository.py :337 `execute_all(sql)` 存在 (GROUP BY 可用) | ✅ 一致 |
| stockdb_provider.py get_minute 端日语义 | :199-204 `end_param = (end_time + timedelta(days=1))...` — end+1day 内置; 签名 (symbols, start_time, end_time, freq) 与驱动 fetch 契约对齐 | ✅ 一致 |
| auction_validation.py :221-233 coverage 装配点 | coverage dict {auction_enabled_dates, ..., symbols: self._coverage_symbols(...)} — minute_stats 并列键插入点明确 | ✅ 一致 |
| auction_validation.py :260-309 `_coverage_symbols` (digest 骨架镜像) | glob("date=*/part.parquet") + `_dir_date` (:287) + fail-closed skip + 诚实空态 — 镜像成立; `_date_range` 不存在 (修正) | ✅ 一致 |
| auction_validation.py :40 import 行 | `from datetime import date, datetime, timedelta, timezone` — 无 `time`, 42-02 T1 需补 | ✅ 一致 |
| verify_auction_backfill.py :76-86 `_lake` / :281-283 [6] 行 | 分区 glob + DuckDB 视图计数; [6] 行 `coverage = lake["symbols"] / uni["total"]` — 并列行插入点明确; `uni` 在 main 内可用 | ✅ 一致 |
| auction_backtest.py :66-70 `_MINUTE_NOTE` / :760 manifest 写入 | 硬编码旧文案 (含过期「历史 CLOSED / 不随湖覆盖增长」语义) — MIN-03 更新点确认; manifest["minute_note"]= _MINUTE_NOTE | ✅ 一致 |
| test_auction_backtest.py :488-489 minute_note 断言 | `"kline_minute" in minute_note` + 旧锚点片段断言 — 随新文本同步替换 | ✅ 一致 |
| test_minute_sync_verify.py :130-147 09:30 anchor | `df["datetime"].min() == datetime(2026, 8, 4, 9, 30)` — 夹具每日期首根 09:30 约定一致 | ✅ 一致 |
| test_auction_validation_report.py :64-70 `_write_auction_partition` + :87-101 repo_env | 分区种子 + 隔离 data_dir fixture — 42-02 测试复用成立 | ✅ 一致 |
| test_verify_auction_backfill.py :21-53 _seed_daily/_seed_auction + :58-66 _run | DATA_DIR env 驱动 main — 42-02 T3 测试复用成立 | ✅ 一致 |
| repository.py :337 execute_all / :342 execute_one | 查询面存在 — `_latest_minute_dates` / `_resolve_minute_universe` 可用 | ✅ 一致 |

## D5 — 决策覆盖 (CONTEXT.md D-NN 引用门)

| 需求 | 决策/约束 | 计划落地 | 状态 |
|---|---|---|---|
| MIN-01 | 源覆盖 source-gated: 机制零源依赖交付; 覆盖 = 源插件深度; 升级 token/重探 = checkpoint:human-verify (绝不虚报) | 42-01 (机制) + 42-03 T2 (seam) + T3 (checkpoint 门) | ✅ |
| MIN-02 | 双口径并列报告 (统计口径绝不算逐笔); FA-04/RC-02 ≥0.94 或诚实 partial | 42-02 T1 (digest 并列) + T2 (amount 派生) + T3 (verify [6]) | ✅ |
| MIN-03 | 09:30 标「集合竞价统计」非逐笔; canonical 只收 09:25 撮合行; T-21-01 截断不回归 | 42-03 T1 (标注 + 回归) + T2 (seam) + 42-02 (caliber) | ✅ |
| 42-RESEARCH | 源选择显式决策 (升级 token / 部署机重探 / seam 三档) | 42-03 T3 option-a/b/c | ✅ |
| 42-RESEARCH | 09:30 双源证实 + amount 派生公式 | 42-02 T2 契约测试 521×1328.36×100≈69,207,556 | ✅ |

## D6 — B/W 清单

### Blockers (0)
无。

### Warnings (6)

- **W1 (42-02 T1)**: RESEARCH §Code Examples 的 digest 骨架引用 `self._date_range(start, end)` — 该方法在 `auction_validation.py` **不存在**。计划已修正为 `_coverage_symbols` 同款 `glob("date=*/part.parquet")` + `_dir_date` 过滤 (D4 已核)。执行时不得按 RESEARCH 骨架逐字抄。
- **W2 (42-02 T1)**: `from datetime import time` 需补 import (现 :40 无 `time`) — 若遗漏, `datetime.time()` 引用会误用 datetime 类方法。已在 action 显式列明。
- **W3 (42-03 T3)**: checkpoint 为 blocking gate → 42-03 `autonomous: false`; 若用户选 option-c (保持机制态), MIN-01 覆盖不达 — 但需求文本已 source-gated (机制交付即满足), 计划已显式声明「覆盖 = 源插件深度」, 不构成需求缩水。
- **W4 (42-01 T3 CLI)**: 未覆盖 symbol 的 CLI 执行面会走默认 fetch (真实 stockdb) — 测试以「跳过优先 + --limit 约束」保证零网络; 若测试环境无 stockdb 容器, 涉及真实 fetch 的用例须以 canned 注入钩子替代 (action 已注明; 容器 :8000 本环境实测可达, 风险低)。
- **W5 (42-02 T3 verify)**: `_minute_stats` 扫全湖 (verify 脚本无窗口参数) — 与 digest 的窗口语义不同 (digest 按 build_report 窗口)。已用 dates 计数显式暴露范围, 不构成口径冲突 (verify = 全湖现状, digest = 报告窗口)。
- **W6 (42-03 T2)**: digest `source` 字段在 42-02 T1 已锁定的 dict 形状上**追加** (42-02 测试不断言 source 键存在/不存在 → 无破坏); 但 42-03 需在 42-02 合并后执行 (wave 2), 执行时若 42-02 有未预期改动需先核对。

### Info (3)

- **I1**: 46min 是 AQ 读侧节奏 (5537×1 GET @120/min), 非端到端时长 — 全程未写入任何验收/done; CLI docstring 含诚实声明指引。
- **I2**: build_report 被 `app/api/research_auction.py:67` 消费 — minute_stats digest 自动透传 API 响应, 端点零改动 (42-02 验证可选 curl 抽查)。
- **I3**: 诚实回归保持绿清单已在 42-03 T1 显式列出 (test_0930_excluded / probe 窗口 09:15-09:25 / test_minute_timestamp_convention / engine 截断族 :371-392) — 扩湖 PR 不得触碰 auction_sync.py / auction_probe.py 写路径。

## D7 — 执行顺序建议

```
Wave 1 (并行): 42-01 (驱动+幂等+CLI)  ‖  42-02 (双口径 digest + verify [6])
Wave 2:       42-03 (标注 + seam + checkpoint 门)
门后 (wave 2 内): 按 T3 决策执行真实源动作 (升级 token / 重探 / 保持) → 覆盖声明按实
```

**Phase gate:** wave 2 合并后全 suite 绿 (含诚实回归族) → `/gsd-verify-work` (42-03 T3 门通过后)。
