# 43-03-SUMMARY.md — SDC-03 诚实门 + sidecar 调度 (Wave 3)

**Phase:** 43-tday-auction-sidecar · **Wave:** 03 (SDC-03: 诚实门 + 调度) · **Date:** 2026-08-07
**Executor:** ExecP4303 · **Status:** DONE — 2 commits, 43-03 电池 19 passed / 0 failed (ledger 10 + pipeline 9), 43-01..03 全链路 46 passed, 诚实回归族 (sync/columns/probe/minute_sync_verify) 50 passed / 1 skipped

## 交付物

| Artifact | Path | 说明 |
|---|---|---|
| sidecar 台账 | `backend/app/services/auction_sidecar_ledger.py` | `append_ledger` (JSONL 追加 + threading.Lock + 滚动清理 MAX_DAYS=7/MAX_RECORDS=5000/PRUNE_EVERY=20, 镜像 alert_store.py:1-41; 原子写 temp+os.replace) / `list_ledger` (job 过滤 + 时间倒序 + 限量, 持锁读) / `read_sidecar_capture_state` (staging manifest → capture 终态推导, 供 09:40 告警判定) — W-5 终态键集: 成功 7 键 `{job, trade_date, requested, ok, failed_symbols, started_at, finished_at}`; fail-closed 追加 `reason` (8 键, ok==0 自动补 `"fail_closed"` 键形不变量, 显式 reason 优先); 非交易日行 `skipped:"no_data"` 与 reason 互斥 |
| 交易日判定 | `backend/app/services/auction_sidecar_ledger.py` | `confirm_trading_day(provider, trade_date, probe_symbol="SH600519", retry_sleep=300.0)` — **数据在场判定** (09:30 bar 存在 ⇒ 交易日; AQ 无日历服务 Q6/A5); 缺失 → sleep 重试 1 次 → 仍无 → False; 与 43-01 reconcile `trading_day_confirmed` 同源同判定点; 请求窗口端日语义 (start=T 00:00 / end=T+1 00:00) |
| 诚实门告警 | `backend/app/services/auction_sidecar_ledger.py` | `evaluate_sidecar_alerts(data_dir, trade_date, capture, reconcile, trading_day)` 纯判定函数 (镜像 30-03 evaluate_premarket 形态) — 交易日 ∧ ok<requested → `auction_sidecar_capture_missing`; 交易日 ∧ status=="mismatch" → `auction_sidecar_reconcile_fail` (含 checks); 非交易日 → 零告警; 事件经 `alert_store.append` 落 `data/user_data/alerts.jsonl` (/api/alerts 查询面既有); 返回事件列表供台账透传 |
| 调度注册 | `backend/app/jobs/daily_pipeline.py` | 三 job 常量 + `_sidecar_capture`/`_sidecar_reconcile`/`_sidecar_promote` (形态镜像 `_premarket_pool_preview`: `fn(on_progress=None) -> dict` + `_get_app_state()` → repo → 终态 dict; 无 app state → 诚实 skip) + `_get_sidecar_provider()` 懒构造 StockDBProvider 单例; 注册: capture 09:26 (与 premarket 同槽位不同 id) / reconcile 09:40 / promote 15:40, 全 CronTrigger mon-fri Asia/Shanghai + `lambda: _run_tracked(fn, job_id)` 单飞 + `replace_existing=True`, capture/reconcile `misfire_grace_time=1800` (盘前窗口窄) / promote 3600 (EOD 后宽窗口) |
| 告警接线 | `backend/app/jobs/daily_pipeline.py` | `_sidecar_reconcile`: reconcile → `trading_day_confirmed` 透传 → 非交易日台账 `skipped_no_data` 零告警; 交易日 → `read_sidecar_capture_state` (无 manifest → 池解析给 requested 提示, ok=0 → capture_missing 可告) → `evaluate_sidecar_alerts` → `events` 透传台账行 (SDC-03「09:26 后缺失可告」) |
| 契约测试 | `backend/tests/test_auction_sidecar_ledger.py` | 10 用例 (4 台账 + 5 告警/交易日 + 1 manifest 推导): W-5 键集逐键 / fail-closed reason 互斥 / 滚动清理不膨胀 / job 过滤倒序 / 09:30 bar 判定三态 + 重试语义 / capture_missing / reconcile_fail / 非交易日零告警 + skipped / 正常日零噪声 / manifest → capture 终态 |
| 调度测试 | `backend/tests/test_daily_pipeline_refresh.py` (扩展) | 6 新用例: 三 job 注册形锁死 (id/时点/replace_existing/misfire_grace_time/09:26 同槽位不同 id/既有 job 零回归/grep 单飞门禁) + 5 接线用例 (采集台账 / mismatch 告警链 / 无 manifest capture_missing / 非交易日静默 / promote 台账) — wave-1/2 边界 sys.modules stub seam, hermetic 零网络 |
| 文档同步 | `docs/features.md` / `docs/deploy-verification.md` | features.md 新增「📡 T-day 竞价采集 sidecar」节 (三 job / staging / 三重对账 / canonical 映射 / 诚实门); deploy-verification.md 观测窗口表 2 行 + D8 节 (sidecar 点亮门 + 诚实空态) |

## Commit 链

| Commit | Sha | 内容 |
|---|---|---|
| T1+T2 | `ff53c68` | sidecar 台账 + 交易日判定 + 告警接线 — JSONL 追加/滚动清理/W-5 键集 + capture_missing/reconcile_fail, 非交易日静默 (10 ledger 契约测试绿) |
| T3 | `90b41b9` | sidecar 三 job 调度注册 + 诚实门接线 + 文档同步 — 09:26/09:40/15:40 CronTrigger mon-fri Asia/Shanghai + _run_tracked 单飞 + 台账/告警链 (6 新用例 + docs) |

## Verify 命令输出摘录

**43-03 电池 (最终, 零网络):**
```
tests/test_auction_sidecar_ledger.py
10 passed in 0.15s

tests/test_daily_pipeline_refresh.py
9 passed in 0.44s
```

**43-01..03 全链路 (wave 合并级 gate):**
```
tests/test_auction_capture.py tests/test_auction_reconcile.py tests/test_auction_promote.py tests/test_auction_sidecar_ledger.py
46 passed in 0.71s
```

**诚实回归族 (canonical 排除/缺列/probe/分钟族零回归):**
```
tests/test_auction_sync.py tests/test_auction_columns.py tests/test_auction_probe.py tests/test_minute_sync_verify.py
50 passed, 1 skipped in 1.88s
```

**Watchlist 守卫:**
```
git diff --stat frontend/src/pages/Watchlist.tsx  — 本 executor 零改动 (133 行 diff 为会话开始前已存在的用户工作, 针对性 git add 隔离, 未入任何 commit)
```

## 契约锁死点 (可执行规范)

- **W-5 终态键集 (T-43-03-03):** 成功态 7 键逐字断言 `{job, trade_date, requested, ok, failed_symbols, started_at, finished_at}`; ok==0 → 自动补 `reason` (fail-closed 8 键, 失败态绝不无因; 显式 reason 不覆盖); `skipped:"no_data"` 与 reason 互斥 — 测试逐键断言锁死。
- **滚动清理 (镜像 alert_store):** MAX_DAYS=7 ∧ MAX_RECORDS=5000 取交集; 测试 monkeypatch MAX_RECORDS=5/PRUNE_EVERY=1 → 写 8 清 3 不膨胀; 原子写 temp+os.replace (T-43-03-03)。
- **交易日判定 = 数据在场 (T-43-03-01):** 09:30 bar 存在 ⇒ 交易日 (AQ 无日历服务, Q6/A5); 缺失 → 重试 1 次 → 仍无 → False; 非交易日 (mon-fri 假日) 自然无分区无告警 — 假日不告警风暴。
- **告警链 (T-43-03-02):** 交易日 ∧ 采集缺失/不完整 (ok<requested) → `auction_sidecar_capture_missing` {ts, rule_id, source, trade_date, requested, ok, failed_symbols}; 对账 mismatch → `auction_sidecar_reconcile_fail` {ts, rule_id, source, trade_date, checks}; 正常日零噪声 (ok==requested ∧ closed → 零事件零文件写入断言); 非交易日零告警 — alerts.jsonl 落盘断言 + /api/alerts 查询面既有。
- **fail-closed 保持 (T-43-03-02):** 采集失败 → 无当日分区 (43-01 机制) + 台账 reason + 09:40 告警; 对账失败 → 不升 canonical (43-02 gate) + reconcile_mismatch 告警; job 异常由 `_run_tracked` 标记 failed (台账由 job 前段尽量记 reason, 不吞)。
- **调度注册形 (T-43-03-05):** 三 job id/时点/时区/misfire_grace_time/replace_existing 捕获断言锁死; 09:26 与 `premarket_pool_preview` 同槽位不同 id 显式断言; 既有 job (instruments/pipeline/pool_eod/premarket/depth) 零回归断言; grep 门禁 `_run_tracked(_sidecar_*, _SIDECAR_*_JOB_ID)`。
- **接线 seam:** job 函数懒 import wave-1/2 模块; 测试经 `sys.modules` + 父包属性双 patch stub (真实模块已 import 时 `from pkg import mod` 取包属性绕过 sys.modules — 属性 patch 保证 stub 生效), 模块级行为由 43-01/02 各自测试覆盖。

## 约束复核

- **零新增依赖:** 2 commits 不触碰 `backend/pyproject.toml` / `backend/uv.lock`。
- **Watchlist 零触碰:** commits 不触及 `frontend/src/pages/Watchlist.tsx` (唯一 unstaged, 会话开始前已存在, 非本 executor 所为; 针对性 `git add` 隔离)。
- **canonical 湖只收 09:25 撮合行:** 本 plan 无 canonical 写面 — promote job 直调 43-02 `promote_trading_day` (gate/过滤/映射全在 43-02 交付物内), 快照行绝不入 canonical 的谓词双保险由 43-02 测试锁死, 43-03 只做接线 + 可观测。
- **零新机制:** 全部镜像既有模式 — JSONL+滚动清理+锁 (alert_store), W-5 键集 (36/41 台账), 告警纯判定函数 (30-03 evaluate_premarket), 调度注册 (daily_pipeline :1140-1174 + _PREMARKET 09:26 同槽位先例), 数据在场判定 (A5)。

## 协作注记

- 与 ExecP4301 (43-01) hub 锁定 manifest 契约: `pool_size` / `symbols_ok` (list[str]) / `symbols_failed` (list[{symbol, reason}]) / `completeness.ok` + `reconcile_window` 返回 `trading_day_confirmed` — `read_sidecar_capture_state` 读取键逐字一致。
- 与 ExecP4302 (43-02) hub 锁定 `promote_trading_day(repo, data_dir, trade_dates) -> {"promoted_dates", "skipped": [{date, reason}], "total_written"}` — `_sidecar_promote` 消费键集一致; 无文件重叠。
- 43-01/02 提交于 43-03 开发中途落盘 — 接线测试用 stub seam 保持 hermetic, 不依赖落盘时序; 落盘后全链路 gate (46 passed) 复核真实模块兼容。

## Next Phase Readiness

- Phase 43 三 wave 全绿: 采集 (SDC-01) → canonical 转化 (SDC-02) → 诚实门+调度 (SDC-03) 闭环; sidecar 自 T-day 起逐日累积, FA-04/RC-02 真列路径解锁 (P2 验证后升级常驻通道)。
- 全量回归由 orchestrator 统一 (本 phase 跳过); deploy D8 点亮门为部署面首验项 (交易日 09:26 起)。
