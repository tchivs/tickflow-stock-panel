# 43-02-SUMMARY.md — SDC-02 T-day 累积 + canonical 转化 (Wave 2)

**Phase:** 43-tday-auction-sidecar · **Wave:** 02 (SDC-02: T-day 逐日累积 + canonical 转化) · **Date:** 2026-08-07
**Executor:** ExecP4302 · **Status:** DONE — 4 commits (T1 RED → T1 GREEN → T2 → T3), 43-02 电池 14 passed / 0 failed, 诚实回归族 (sync/columns/probe) 46 passed, 43-01 capture 面 12 passed

## 交付物

| Artifact | Path | 说明 |
|---|---|---|
| 提审驱动 | `backend/app/services/auction_promote.py` | `promote_to_canonical(stage_dir, repo, trade_date, tol=1e-6)` — gate (manifest completeness.ok ∧ reconciliation.closed, **绝不用** `resolve_auction_probe` — Pitfall 6) → 撮合行过滤 (time∈09:25:00..09:25:59 ∧ num_trades>0 → sort("time") → `unique(subset=["symbol"], keep="first")` 单 symbol 单日单行) → 单位映射 (auction_volume=vol_hand×100 股 / auction_amount=price×vol_hand×100 元 / auction_virtual_price=price; num_trades 只进返回/manifest 元数据) → `write_auction_partitions` 直调 (555..565 谓词 + 存在性 crop + merge-upsert 幂等 + 原子写) |
| 逐日累积 | `backend/app/services/auction_promote.py` | `promote_trading_day(repo, data_dir, trade_dates)` — 自 T-day 起每交易日一分区逐日提审, 聚合 `{"promoted_dates", "skipped": [{date, reason}], "total_written"}`; 无 staging → skipped (staging_missing); gate 拒绝 → skipped (reason 透传) — 全链路诚实可观测; 幂等天然 (merge-upsert + written=新增键计数) |
| manifest promoted 块 | `backend/app/services/auction_promote.py` | `_update_manifest_promoted` — 读旧 manifest → 增 `{promoted: true, promoted_at, written, num_trades_by_symbol}` → temp+os.replace 原子写 (镜像 premarket_snapshot); 旧键保留; 旧 manifest 缺失 (gate 已拒) 不写 — 绝不伪造提审状态 |
| DATA-06 交叉验证 | `backend/app/services/auction_promote.py` | `cross_validate_virtual_price(repo, trade_date, symbols=None, tol=1e-6)` — kline_auction.auction_virtual_price vs kline_daily.open 独立第二来源互证 (镜像 verify_auction_backfill [4]); 逐 symbol `{symbol, virtual_price, kline_open, diff, ok}`; 无 kline_daily 当日分区 → `{"skipped": [...], "reason": "no_kline_daily"}` 诚实标注 |
| 契约测试 | `backend/tests/test_auction_promote.py` | 14 用例 (12 plan + 2 防御: manifest_missing 独立 / no_match_rows): 撮合行端到端 / 虚拟行+回显行+重复行排除 / gate 三拒 / 多日累积 / 幂等重跑 / skipped / manifest 块 / 交叉验证三态 / unmatched 永不产出 |

## Commit 链 (RED → GREEN 可回溯)

| Commit | Sha | 内容 |
|---|---|---|
| T1 (RED) | `022d376` | 提审契约测试 ×14 — 收集期红: `ModuleNotFoundError: No module named 'app.services.auction_promote'` |
| T1 (GREEN) | `0809609` | promote_to_canonical — 仅撮合行升湖 + 单位映射 + staging gate (6 契约测试绿) |
| T2 | `c98bfbb` | T-day 逐日累积 — promote_trading_day + 幂等重跑 (written=新增键) + manifest promoted 块 (4 契约测试绿) |
| T3 | `e95497e` | DATA-06 映射 + 交叉验证 (virtual_price==kline_daily.open 1e-6; unmatched 诚实缺列) (4 契约测试绿) |

## Verify 命令输出摘录

**T1 (RED, 验收第一步行):**
```
tests/test_auction_promote.py::test_promote_single_symbol_writes_canonical - ModuleNotFoundError: No module named 'app.services.auction_promote'
1 failed in 0.27s
```

**T1 (GREEN):**
```
tests/test_auction_promote.py -k "single_symbol or excludes_virtual or gate or no_match"
6 passed, 8 deselected in 0.31s
```

**T2 (GREEN):**
```
tests/test_auction_promote.py -k "trading_day or rerun or skipped or manifest"
5 passed, 8 deselected in 0.41s
```

**T3 (GREEN):**
```
tests/test_auction_promote.py tests/test_auction_columns.py
28 passed in 1.06s
```

**43-02 电池 (最终, 零网络):**
```
tests/test_auction_promote.py
14 passed in 0.52s
```

**诚实回归族 (canonical 写面/缺列语义/probe 枚举零回归):**
```
tests/test_auction_promote.py tests/test_auction_columns.py tests/test_auction_sync.py tests/test_auction_probe.py
60 passed, 1 skipped in 2.84s
```

**43-01 capture 面兼容 (peer 已提交部分):**
```
tests/test_auction_capture.py
12 passed in 0.16s
```

## 契约锁死点 (可执行规范)

- **仅撮合行升湖 (T-43-02-01):** staging 过滤 `time∈09:25:00..09:25:59 ∧ num_trades>0` → sort("time") → `unique(subset=["symbol"], keep="first")` → 单 symbol 单日单行 (09:25:00 撮合行; 同值 09:25:04 dedupe); 虚拟快照行 (num_trades=0) 与 09:25:01 回显行永不入 canonical (555..565 谓词 + 提审过滤双保险)。测试断言: 6 行窗口 (3 虚拟 + 撮合 + 回显 + 重复) → canonical 恰 1 行 09:25:00。
- **单位映射锁死 (T-43-02-03):** auction_volume = 173×100 = 17300 股 (手→股 ×100) / auction_amount = 173×100×1308.66 = 22,639,818 元 (pytest.approx) / auction_virtual_price = 1308.66; datetime = 09:25:00 naive 北京墙钟; num_trades (120) 只进返回/manifest — canonical 无此列。
- **提审闸门 fail-closed (T-43-02-05 / T-43-02-02):** manifest 缺失 → `manifest_missing`; completeness.ok != True → `capture_incomplete`; reconciliation.status != "closed" (mismatch/pending/缺块) → `reconciliation_not_closed` — 三拒 0 写带 reason 绝不静默; 闸门为当日 staging 判定, **无任何** `resolve_auction_probe` 调用面。
- **逐日累积幂等:** 多日期驱动逐日分区; 重跑同参 → written==0 (全部已覆盖, written=新增键计数, merge-upsert keep=last) + 分区行数不变; manifest promoted==true 幂等更新。
- **诚实 skipped:** 无 staging 分区 → `{"date", "reason": "staging_missing"}` 不写湖不报错; 全虚拟窗口 → `no_match_rows` 0 写。
- **DATA-06 诚实 (T-43-02-04):** `auction_unmatched_volume` 分区列集断言 == {symbol, datetime, auction_volume, auction_amount, auction_virtual_price} — tick 源无未匹配量字段, 存在性 crop 天然缺列绝不 0 填; virtual_price vs kline_daily.open 1e-6 交叉验证三态 (闭合 all_ok / 漂移 0.34 诚实报告 all_ok False / 缺 daily → skipped+reason) 镜像 verify [4] 语义。
- **原子性:** manifest promoted 块 temp+os.replace; canonical 走 `_atomic_write_parquet` (无 .tmp 残留断言); 旧 manifest 键 (completeness/reconciliation) 保留。

## 约束复核

- **零新增依赖:** 4 commits 不触碰 `backend/pyproject.toml` / `backend/uv.lock`。
- **Watchlist 零触碰:** commits 不触及 `frontend/src/pages/Watchlist.tsx` (保持唯一 unstaged, 非本 executor 所为; 针对性 `git add` 隔离)。
- **零新机制:** 全部镜像既有模式 — canonical 写面直调 `write_auction_partitions` (20-01 单一写路径), 原子写 (premarket_snapshot), 交叉验证 (verify_auction_backfill [4] 1e-6), 种子形态 (test_verify_auction_backfill `_seed_daily` / test_auction_sync repo_env)。
- **本 plan 不承诺真实源覆盖:** 全部验收种子 staging/kline_daily 分区零网络; 43-03 调度面接 `promote_trading_day` 返回键集。

## 协作注记

- 与 ExecP4301 (43-01) 通过 hub 锁定 manifest 契约: `{"completeness": {"ok": bool, "by_symbol": ...}, "reconciliation": {"status": "closed"|"mismatch"|"pending"|"staging_missing", ...}}` — 与 43-02 gate 读取键逐字一致, 集成无漂移。
- 与 ExecP4303 (43-03) 通过 hub 锁定 `promote_trading_day(repo, data_dir, trade_dates) -> {"promoted_dates", "skipped": [{date, reason}], "total_written"}` 签名/返回键; 无文件重叠 (43-03 归 daily_pipeline.py / auction_sidecar_ledger.py)。
- ExecP4301 的 `backend/tests/fixtures/ticks/` + `test_auction_capture.py` 未触碰 (针对性 `git add` 隔离)。

## Next Phase Readiness

- 43-03 (诚实门 + 调度): `promote_trading_day` 即 EOD 15:40 promote job 的调用面; `skipped` 键集供台账/告警判定 (gate 拒绝日可告警可观测)。
