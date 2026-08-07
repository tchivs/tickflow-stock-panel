# 40-03-SUMMARY — 集成 wave (LOCAL-04)

**Phase**: 40-stockdb-local-channel / wave 3 (集成)
**Executor**: ExecP4003
**Commits**:
- `c83ae2d` — test(phase-40-03): 链集成 — 链首 gap-merge (daily/minute) + 空帧回退 + 异常跳过 + 默认链首断言 + 白名单可切换 + settings builtin TestClient
- `1df4b87` — test(phase-40-03): 写路径冒烟 — append_daily 全链贯通 + 二次幂等 + 湖无 provenance 列 + 通道身份日志 (kline_sync.py 零改动)
- `75dab53` — test(phase-40-03): AST 只读守卫改形 — 执行族 import / 写模式 / 仅 GET / api_key 仅 headers 四判据 (LOCAL-01 硬验收)

依赖 wave: 40-01 (`4e16499`/`df24481`/`ff15572`/`bcba35d`, 17 tests) + 40-02 (`8655a57`/`1ee1979`/`f468c7f`, 10 tests) 均已落地后本 wave 全绿。

---

## Task 1 — 链集成测试 (gap-merge 链首 + TestClient settings 面)

文件: `backend/tests/test_provider_chain.py` (6 新增), `backend/tests/test_data_source_selection.py` (1 新增)

新增用例:
- `test_chain_local_stockdb_heads_gap_merge` — local 01-02 日 + free 02-03 日 → dates == [2024-01-02, 03, 04], 无重复 ((symbol,date) 去重 + 前序覆盖)
- `test_chain_local_stockdb_heads_minute_gap_merge` — 分钟面 (LOCAL-04 分钟 gap-merge 用例): (symbol,datetime) 去重合并, freq 夹具
- `test_chain_local_empty_falls_through` — local 空帧 → free 补全 (空帧跳过语义保持)
- `test_chain_local_exception_skips_with_warning` — local 抛 `StockDBAuthError` → free 兜底 + caplog 断言 `chain[daily]` warning 行含通道名 (通道身份进日志)
- `test_chain_builtin_heads_local_stockdb` — 默认链首断言: `get_provider_chain("daily")[0] == "local_stockdb"` 且 minute 同 (chain_for 默认)
- `test_settings_data_sources_builtin_lists_local_stockdb` — 最小 app (镜像 `_make_auction_app`) + monkeypatch `health_check`/custom 插件面 → `GET /api/settings/data-sources` 200, builtin 含 `local_stockdb` (datasets==["daily","minute"], health=="ok", base_url==settings.local_stockdb_url)
- `test_local_stockdb_swappable_via_preferences` — 白名单可切换回归锁 (静默回退陷阱) + 未知源仍安全回退

Verify: `cd backend && .venv/bin/python -m pytest tests/test_provider_chain.py tests/test_data_source_selection.py -x -q`
→ `31 passed in 1.85s`

## Task 2 — 双源守卫验证 + 写路径冒烟 (kline_sync 零改动)

文件: `backend/tests/test_local_stockdb_write_path.py` (新建, 4 用例)

配方镜像 test_daily_pipeline_refresh (tmp_path 真 repo + 零网络, 禁 background=True); fake local provider 提供 2 标的 × 2 日规范帧 (后缀形态), monkeypatch `chain._get_provider` (按 name 分派, 其余源抛 AssertionError) + `preferences.get_provider_chain` 恒 `["local_stockdb"]` → 全链 `sync_and_persist_daily_batch(symbols, repo, capset, count=2, ...)` 走既有写路径。

- `test_local_channel_writes_via_existing_append_daily` — 返回行数 == 4 == 湖 `kline_daily/date=*/*.parquet` 总行数
- `test_local_channel_write_is_idempotent` — 二次运行返回行数不变且湖行数仍 == 4 (merge-upsert `unique(subset=["symbol","date"], keep="last")` + 原子 rename 由既有机制保证, 本测试锁用户可观测结果)
- `test_lake_schema_has_no_provenance_columns` — 湖 parquet schema 列集 ⊆ {symbol,date,open,high,low,close,volume,amount,quote_ts}; 断言无 source/fetched_at/schema_version/volume_hand/ingested_at (LOCAL-04 铁律)
- `test_channel_identity_in_chain_log` — caplog 断言 `chain[daily]` 行含 `local_stockdb` 与 `added N rows`

通道日志实测摘录 (test_channel_identity_in_chain_log 运行):
```
INFO     app.data_providers.chain:chain.py:159 chain[daily]: provider local_stockdb added 4 rows
1 passed
```

Verify: `cd backend && .venv/bin/python -m pytest tests/test_local_stockdb_write_path.py -x -q` → `4 passed`; `git diff --name-only -- app/services/kline_sync.py | wc -l` → `0` (kline_sync.py 零改动铁律 ✓)

双源守卫回归 (沿用既有机制, 本任务不新建): 单源选择 = test_data_source_selection 既有 (白名单 + 可切换); run-slot 互斥 = test_auction_backfill._wait_slot_free 既有; 幂等写 = 本任务 `test_local_channel_write_is_idempotent`。Pitfall 7 记录: flush 覆写 vs merge 并发双路径共存现状 — 本通道只走 `append_daily` merge 路径, flush 语义零改动。

## Task 3 — AST 守卫改形 + 全量 hermetic 回归 + live 冒烟 runbook

文件: `backend/tests/test_stockdb_provider.py` (追加 POOL-03 模板改形, 1 用例 4 判据)

`test_stockdb_provider_is_read_only_http_client`:
- 判据 A — 无执行族 import (POOL-03 E1 `_imported_module_names` 判据, broker|order|execution|trade|portfolio|watchlist|position|account|transaction|下单|委托)
- 判据 B — 无写模式 token (`open(` 写模式 / `write_parquet` / `os.replace` / `unlink` / `mkdir`), 过滤注释+文档串后断言
- 判据 C — HTTP 动词仅 GET: `client.get(` 存在, 无 `client.post/put/delete/patch`
- 判据 D — api_key 仅 headers dict (LOCAL-01 硬验收): tokenize 级剔除注释/文档串后, 每个含 `X-API-Key` 的代码行必含 `headers`

Verify: `cd backend && .venv/bin/python -m pytest tests/test_stockdb_provider.py -x -q` → `18 passed in 0.53s` (17 契约 + 1 AST 守卫)

### 全量 hermetic 回归

`cd backend && .venv/bin/python -m pytest tests/ -x -q` → **`1836 passed, 4 skipped`** (697.07s, 零失败)

回归清单逐项:
| 命令 | 结果 |
|---|---|
| tests/test_stockdb_provider.py -x | 18 passed |
| tests/test_provider_chain.py -x | 31 passed (与 data_source_selection 合并跑) |
| tests/test_data_source_selection.py -x | 31 passed (同上) |
| tests/test_local_stockdb_write_path.py -x | 4 passed |
| tests/test_minute_timestamp_convention.py -x | 14 passed (与 ifzq/xyz 合并跑) |
| tests/test_ifzq_provider.py -x | 14 passed (同上, ×100 口径既有隐患不修) |
| tests/test_xyz_provider.py -x | 14 passed (同上, 空帧契约不触碰) |
| tests/ -x (全量) | 1836 passed, 4 skipped |
| `git diff --name-only -- app/services/kline_sync.py` | 空 (零改动门 ✓) |
| `git diff --name-only \| grep Watchlist` | 仅 pre-existing `frontend/src/pages/Watchlist.tsx` (唯一 unstaged 改动, 零触碰 ✓) |

### live 冒烟 runbook (环境门控, 实测通过)

- 前置: `curl -s 127.0.0.1:8000/health` → `404` (服务可达, 无 /health 路由; 后续 401 证明 HTTP 面活); `../stockdb/.env` 存在 (`STOCKDB_API_KEYS=testkey123`, 首 key 读取)
- 空 key 对照: 请求真实到达服务端并返回 `401 {"error":"unauthorized","detail":"invalid api key","code":401}` → 适配器正确抛 `StockDBAuthError` (typed 路径实测)
- 执行 (`LOCAL_STOCKDB_API_KEY` 注入 + `get_daily(['600519.SH'], 2026-08-05..2026-08-05)`):

```
rows: 1
[{'symbol': '600519.SH', 'date': datetime.date(2026, 8, 5), 'close': 1306.45, 'volume': 42689.0, 'amount': None}]
SMOKE-OK: 600519@2026-08-05 volume == 42689.0 (双源交叉锚点一致)
```

- **结果: 冒烟通过 (非 skip)** — 双源交叉锚点一致: live stockdb 输出 volume == 42689.0 == 湖内实测 (RESEARCH 锚点), symbol 后缀形态, date naive, amount=None 诚实透传 (腾讯日K合法缺成交额)。单请求低频 (1 请求 1 标的), 不触限频。

## Success criteria 对照

- 链集成 (gap-merge 链首 daily/minute / 空帧回退 / 异常跳过 / 默认链首 / TestClient settings 面) + 白名单可切换 — 全绿断言 ✓
- 写路径冒烟: 返回行数可观测、二次幂等、湖 schema 无 provenance 列、caplog 通道身份 — 全绿 ✓
- AST 只读守卫四判据 (执行族 import / 写模式 / 仅 client.get / api_key 仅 headers) — 全绿 ✓
- 全量 hermetic 回归绿 (1836 passed, 4 skipped); 零新增依赖 (纯测试面); Watchlist.tsx 零触碰 ✓
- LOCAL-04: daily/minute 链首 gap-merge 走既有 kline_sync 写路径 (kline_sync.py 零改动); 双源守卫沿用; 湖无 provenance 列; 通道身份进日志 ✓
- live 冒烟执行成功, 证据完整 (无 skip 场景) ✓
