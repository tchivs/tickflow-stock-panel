# Phase 36 — 36-03 SUMMARY（EOD 回归 + features.md + FA-01..06 验收裁定）

**Wave**: 36-03 (FA-06 EOD interplay regression + docs/features.md + phase summary; parallel with 36-02, after 36-01)
**Date**: 2026-08-07
**Status**: FA-01/02/03/06 COMPLETE · FA-04 **IN-PROGRESS/BLOCKED（上游 403，运营已止损停跑，待恢复后 chunked 续跑）** · FA-05 COMPLETE（机制+测试+文档 fold；台账终证待 36-02）

## 1. Verdict

| Req | Verdict | 一句话 |
|---|---|---|
| FA-01 超时豁免 | **COMPLETE** | `create(timeout_s)` 持久化 + `reap_stale` per-job 优先 + API 传 21600；回归测试绿（详见 §3） |
| FA-02 only-missing | **COMPLETE** | 覆盖预扫描 + service 过滤 + API body 参数；测试绿（W3 形状感知 fake db 使 DuckDB 分支真实执行） |
| FA-03 运营 CLI | **COMPLETE** | 全旗标 CLI 落地并被 detached 实跑验证（它真的把 34 个新 symbol 写进了湖） |
| FA-04 全量实跑 | **IN-PROGRESS/BLOCKED** | 见 §4：上游 403 天花板在 ~36 次持续请求后触发；运营已 SIGTERM 止损；验收数字（≥5200 / ≈1,290,592 行 / 248 分区）**尚未达成**；恢复后 chunked + `--only-missing` 续跑 |
| FA-05 BJ 诚实上限 | **COMPLETE** | 诚实测试绿（`empty_response` 台账机制）+ RESEARCH 锚点（5 格式全败、94.0% 上限）+ features.md AQ-11 fold；完整 stance 文档为 36-02 并行交付 |
| FA-06 EOD 交织 | **COMPLETE** | 三层幂等 no-op crop 回归测试绿 + features.md 调度纪律注记 |

**诚实偏差声明**：FA-04 未能按原计划在本 wave 内完成 —— 不是代码缺陷（代码按设计工作：merge-upsert crop、台账、fail-closed 全部按契约运行），而是**上游源在持续请求 ~36 次后开始对一切返回 403 Forbidden**（直接单请求复测仍 403 → 源侧封锁，非瞬时抖动）。pilot（n=20 live，0×429）未触及该天花板。恢复计划由运营裁定：测恢复窗口（+10min/+30min）→ chunked 小批量 + 冷却 → `--symbols` + `--only-missing` 顶补，绝不再 3.5h 锤击。

## 2. Delivered code（本 wave 直接交付 + 36-01 落地）

- 36-01（已提交，本 wave 验证执行）：
  - `create(timeout_s=...)` 持久化 per-job 键 + `reap_stale` 循环内 `j.get("timeout_s", STALE_JOB_TIMEOUT_S)` 优先（FA-01）— commit 59dd2a6
  - `_covered_symbols` 覆盖预扫描 + `only_missing` 贯穿 service + API body 参数（FA-02）— commit e46e973
  - `backend/scripts/auction_backfill.py` 全旗标 CLI，`job_id=None` 零 job_store（FA-03）— commit 383aca8
  - 回归套件 `backend/tests/test_auction_backfill_full_universe.py`（token: timeout/reap/only_missing/cli/eod）— commit c450dd8
- 36-03（本 wave）：
  - **FA-06 回归执行**：`test_full_backfill_eod_interplay_rewrite_idempotent`（seam/service/EOD 路径三层，token `eod`）— 绿，无代码改动（测试由 36-01 定义，本 wave 执行）
  - `docs/features.md` 竞价回填节：AQ-07..12（实测规模 / 续跑 / 6h 豁免 / CLI / 94.0% 上限 / 验证）+ **调度纪律（EOD 交织）** 4 点注记
- 36-02（并行，本 wave 结束时未落盘，PENDING）：`backend/scripts/verify_auction_backfill.py`、`FA-05-BJ-STANCE.md`、RUN-LEDGER/RUN-VERIFY 证据文件

## 3. Test evidence（2026-08-07，backend/.venv 实测）

| 命令 | 结果 |
|---|---|
| `pytest tests/test_auction_backfill_full_universe.py -k "eod" -q` | **1 passed**（FA-06 三层：seam 同帧重写行数不变无 .tmp / service 二跑湖行数不变 / EOD `sync_and_persist_auction` 已覆盖 symbol 返回 >0 但湖不变 + 混合追加） |
| `pytest tests/test_auction_backfill_full_universe.py -k "timeout or reap or only_missing or bj or eod or cli" -q` | **14 passed**（36-01 batch，全 token） |
| `pytest tests/test_auction_backfill.py -q` | 23 passed |
| `pytest tests/test_auction_backfill_honesty.py -q` | 10 passed, 1 skipped（skip = RUN_NETWORK_TESTS 门控，非失败） |
| 三文件合计 | **47 passed, 1 skipped**（波末 belt-and-braces，零新增失败） |

## 4. Run evidence（FA-04，来自日志/湖/进程观测 —— 只读）

**启动**：2026-08-07 08:23 detached CLI `scripts/auction_backfill.py --all --rpm 30 --out /tmp/auction-backfill-v24.json`（pid 397197，cwd=backend）。

**成功段**：`回填 5537 个标的 × 248 日…` → 进度 `1/5537..32/5537 (成功 32, 失败 0)`；湖从 2 symbol（000001/000002，RESEARCH 基线 496 行）增至 **36 symbol × 248 分区**（34 个新 symbol 实写；分区 `date=2026-08-05/part.parquet` = 36 行 / 36 symbol，canonical 1 行/标的/日不变式保持）。分区目录 mtime 止于 08:27（最后一次成功写）。

**403 段**：自 ~symbol 33 起**每个**上游请求 `403 Forbidden`（`http://8.138.149.215:7898/mcp`；日志累计 **199 条错误行**，~2-3s/次 = rpm-30 节奏下逐 symbol 快失败）；此后零湖写入。**关键观测**：provider 把 HTTP 错误吞成空帧（`xyz_provider.py:192-196` catch-all → `pl.DataFrame()`）→ 403 封锁 symbol 被如实记为 `empty_response`，**与 BJ 真性缺口不可区分**（诚实性缺口，记为修复候选，非本 wave 范围）。另：空帧 `continue` 跳过每 symbol 进度 emit（`services/auction_backfill.py:289-296`）→ 日志进度冻结在 32/5537 而 stderr 403 行持续 —— 循环实际在推进、全部失败（可观测性缺口，W4 hub-ready 探针注记的新维度）。

**止损**：运营裁定 SIGTERM（~08:35，pid 已消失）；停后直接单请求复测仍 403 → 源侧封锁确认。台账文件 `/tmp/auction-backfill-v24.json` 仍为**启动桩**（`reason:"no_scope"`，CLI 仅在完成时写终态）→ 本次 run 记录 = 日志本身。

**36-02 证据（PENDING，非本 wave 可得）**：终态 dict（requested/backfilled/rows/dates/failed）、verify 脚本六项输出（248 分区 / 0 交叉验证失配 / 0 .tmp）、顶补稳定性（连续两次 `--only-missing` 0 新增）—— 全部待恢复续跑完成 + 36-02 落盘。

**恢复基线（RESEARCH 锚点）**：pilot mean 0.96s/req、0×429；rpm 30 全量 ≈ 3.4-3.8h（含裕量 3.5-5.5h）；目标终态 requested=5537 / backfilled≈5204（SZ/SH 全量、BJ 333 恒 empty_response）/ rows≈1,290,592 / dates=248 / 覆盖 94.0%。

## 5. Anchor corrections（36-PLAN-CHECK W5，PATTERNS.md 未修）

- PATTERNS.md row 6 「幂等 crop (auction_sync.py:137-141)」**过时**：:137-141 在 `_first_auction_provider` 内；幂等 crop = keep-columns select `auction_sync.py:82-86`，merge-upsert `:99-106`（`unique(subset=["symbol","datetime"], keep="last")`），窗口谓词 `:63-75`。
- PATTERNS.md row 7 「终态 dict (auction_backfill.py:250-258)」**过时**：8 键 dict 在 **service** 文件 `services/auction_backfill.py:253-261`（api 文件仅 125 行）。
- 36-02 T4 引 kline_daily 视图 :162-164 → 实际 `CREATE OR REPLACE VIEW kline_daily` 在 `repository.py:146-147`（kline_auction :168-170 正确）。
- PATTERNS.md 文件本身本轮未修（drift 仍在），本 SUMMARY 为纠正锚点。

## 6. Acceptance table（FA-01..06 → criterion → evidence）

| Req | Criterion（REQUIREMENTS.md） | Evidence |
|---|---|---|
| FA-01 | `create(timeout_s)` 持久化；`reap_stale` 用 `j.get("timeout_s", 600)`；API 传 21600；>600s job 不再被回收 | 代码：pipeline_jobs.py:101-119/227-255、api/auction_backfill.py:89；测试：`-k "timeout or reap"` 绿（14 批内）；commit 59dd2a6 |
| FA-02 | `only_missing=True` 预扫描（GROUP BY symbol 计数==len(aligned_dates) 跳过）；部分残差重拉；API body 接受；merge-upsert 保持 | 代码：`_covered_symbols` + run 循环；测试：`-k only_missing` 绿（含 DuckDB 分支真执行）；commit e46e973 |
| FA-03 | CLI `--symbols\|--all --start --end --rpm --only-missing`；job_id=None 零 job_store；stdout 进度；终态 dict + failed_symbols → JSON | 代码：scripts/auction_backfill.py（AST 守卫测试锁零 job_store import）；测试：`-k cli` 绿；**实跑实证**：detached 启动写入 34 symbol |
| FA-04 | detached 全量 5537×248；backfilled≥5200；rows≈1,290,592；248 分区；无 .tmp；交叉验证；顶补稳定 | **IN-PROGRESS/BLOCKED**：启动 08:23、34 symbol 实写（湖 2→36）、上游 403 封锁（199 错误行）、运营 SIGTERM 止损；验收数字未达成，恢复后 chunked+only-missing 续跑；36-02 ledger/verify 待落盘 |
| FA-05 | BJ 333 全 `empty_response` 台账；覆盖 ≤94.0% 诚实；5 格式 stance 文档 | 诚实测试绿（`-k bj`：BJ empty_response 记录）；RESEARCH §3.2（6 只 920xxx 0 行、5 格式全 `请求参数错误`）；features.md AQ-11（94.0% = 5204/5537）；FA-05-BJ-STANCE.md 待 36-02 |
| FA-06 (P2) | EOD 重写已覆盖 symbol = 幂等 no-op crop（湖行数不变）；跨进程写纪律文档化 | `test_full_backfill_eod_interplay_rewrite_idempotent`（token eod）**1 passed**（seam/service/EOD 三层）；features.md 调度纪律 4 点（EOD 窗口外 / run-slot 串行 / CLI 无槽 / 最坏 last-rename-wins 不损坏湖） |

## 7. Notes for Phase 37

1. **湖覆盖**：恢复续跑完成后 `kline_auction` 覆盖 = 5204/5537 = **0.94** → Run B 重跑 `coverage.symbols` 应翻转为 ≥0.94（RC-02 锚点）；`_compute_run_id` 湖覆盖 digest 从「恒 0.0004」变为有意义。当前湖实态 36 symbol（2+34）——94% 只在续跑完成后成立，Run B 前需先确认。
2. **403 天花板（新发现）**：持续 rpm-30 回填在 ~36 次请求后触发源侧 403（pilot n=20 未触及）。恢复策略 = chunked 小批量 + 冷却 + `--only-missing` 顶补。若再次触发，需降 rpm 或拉长冷却。
3. **诚实性缺口（修复候选）**：provider `get_auction` catch-all 吞 HTTP 错误 → 403 封锁与 BJ 真性空无法区分（都记 `empty_response`）。候选：在 provider 层区分传输/HTTP 4xx 并携带状态，或 service 层对持续全量失败加告警。非本 wave 范围。
4. **可观测性缺口（修复候选）**：空帧 `continue` 跳过每 symbol 进度 emit（services/auction_backfill.py:289-296）→ 失败段进度冻结，hub ready 探针与 stall 检测会误判。候选：emit 移到 continue 之前。W4 注记的新维度。
5. **FA-01 豁免不受影响**：CLI 路径本就不触 job_store；恢复续跑同样安全（重启中断安全是 CLI 设计属性）。
