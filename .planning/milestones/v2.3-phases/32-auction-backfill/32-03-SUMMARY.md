# 32-03 SUMMARY — AQ-04 诚实守卫 + 交叉校验 + 文档 (Phase 32 Wave 2)

**Executor:** ExecutorP3203 · **Date:** 2026-08-06 · **Plan:** `.planning/phases/32-auction-backfill/32-03-PLAN.md`
**Parallel:** 32-02 (ExecutorP3202) — zero file overlap; coordination via hub (pacing of test runs; 32-02 landed mid-run, precondition gates respected).

## Delivered

| Artifact | Content | Commit |
|---|---|---|
| `backend/tests/test_auction_backfill_honesty.py` (new, 11 tests) | AQ-04 诚实套件: 失败台账终态形状 / 部分失败如实 / origin-rpm 契约 / BJ 空响应诚实记录 / 空响应类别互斥 / fail-closed 9 键 0 写; 成功准则 4 罐装交叉校验 (恒 on) + 网络门变体; POOL-03 AST 守卫 (新 POST 路由 E1/E3 + auction_history GET-only 复验 + strategy_cache 负向) | `a1a7cf5` |
| `docs/features.md` | 竞价历史回填小节 (端点/诚实闸门/origin 契约/缺列/操作指引 + curl 示例) + AQ-06 分钟回填 CLOSED 注记 + R3 probe 缓存注记 | `8aefc65` (section), `2906dc7` (curl runbook) |

## Verification results

| Gate | Command | Result |
|---|---|---|
| Task 1 (台账/BJ/empty) | `pytest tests/test_auction_backfill_honesty.py -k "ledger or origin or bj or empty" -x -q` | **6 passed** |
| Task 2 (交叉校验+守卫) | `pytest tests/test_auction_backfill_honesty.py -k "cross_check or ast_guard or get_only or strategy_cache" -x -q` | **4 passed** |
| 全量诚实套件 | `pytest tests/test_auction_backfill_honesty.py -x -q` | **10 passed, 1 skipped** (网络门默认 skip) |
| 既有守卫不破 | `pytest tests/test_auction_history.py tests/test_pool_hub.py -x -q` | **54 passed** (零改动) |
| 网络门交叉校验 (沙箱, 一次) | `RUN_NETWORK_TESTS=1 pytest tests/test_auction_backfill_honesty.py -k virtual_price -x -q` | **1 passed** (真实 kline_daily 只读 3 日 + mock 上游确定性; 真实 MCP 附加段因沙箱探测非 available 诚实跳过 — 确定性 mock 段为承重断言) |
| 全量回归 (32-01/02/03) | `pytest tests/test_auction_backfill_honesty.py tests/test_auction_backfill.py tests/test_auction_sync.py tests/test_auction_history.py tests/test_auction_probe.py tests/test_xyz_provider.py tests/test_pool_backfill.py -x -q` | **96 passed, 2 skipped** (2 网络门 skip: 本套件 virtual_price + 32-02 套件网络门) |
| docs 结构门 | `grep -c 竞价历史回填 / AUCTION-BACKFILL.md / 正式关闭 / curl -X POST` | 1 / 1 / 1 / 2 (均 ≥1) |

## W-4 / W-5 application evidence

- **W-4 (token-embedded names)**: Task 1 六个测试名全部内嵌 `-k` token —— `test_auction_backfill_failed_ledger_terminal_shape`, `test_auction_backfill_partial_failure_ledger_records_others_continue`, `test_auction_backfill_origin_backfill_only_in_terminal_dict`, `test_auction_backfill_bj_stock_empty_response_recorded`, `test_auction_backfill_empty_response_reason_category_distinct`, `test_auction_backfill_fail_closed_ledger_shape_and_zero_writes`; `-k "ledger or origin or bj or empty"` 全命中 6 例。Task 2 四例命中 `-k "cross_check or ast_guard or get_only or strategy_cache"`,网络门命中 `-k virtual_price`。
- **W-5 (8-key vs 9-key contract)**: 成功路径 set 相等限定在 `test_auction_backfill_failed_ledger_terminal_shape` — `set(term) == {requested, backfilled_symbols, rows, dates, failed, failed_symbols, origin, rpm}` (恰 8 键, 无缺键无多键); fail-closed 9 键 (8 成功键 + `reason`) 在 `test_auction_backfill_fail_closed_ledger_shape_and_zero_writes` 单独断言 (`set(term) == _SUCCESS_KEYS | {"reason"}`, `reason=="source_unavailable"`, 0 写)。与 32-02 落地实现逐字核对一致 (服务 `_fail_closed` 返回 9 键, 终态 dict 8 键)。
- 附加: `_patch_probe`/`_patch_provider` 双面 patch (源模块 + 消费模块), 覆盖 32-02 函数级 import 形态; `_patch_pacing` 钉 `rate_limits._reserve_slot` → 0 避免真实 sleep (W-3 精神); `_FakeRepo` 支持 `repo.db.execute(...).fetchall()/fetchone()` (W-1: 无 repo.query, 与 32-02 `_lake_distinct_symbols`/`_has_daily_rows` 兼容)。

## Deviations

1. **monkeypatch string-target quirk**: `monkeypatch.setattr(module_name_str, attr, ...)` 在本 pytest 版本抛 `AttributeError` (字符串目标不解析属性) — 改为模块对象目标 (`monkeypatch.setattr(auction_sync, "_first_auction_provider", ...)`), 与仓库既有测试 (test_auction_sync.py) 形态一致。无行为影响。
2. **网络门真实 MCP 附加段**: 沙箱 `resolve_auction_probe()` 返回非 available → 附加实时取数段诚实跳过 (try/except 包裹, 记录 `real_checked=False`); 承重断言仍是确定性 mock 段 (真实 kline_daily 只读 open 值 == 写后 virtual price, 3 日逐值相等)。与计划「真实 MCP 可达时附加」语义一致。
3. **Task 3 curl 示例**: 计划小节未列 curl 文本, 但任务描述「operator runbook (POST curl, …)」要求 —— 补 2 个 curl 示例 (全量 + 子集日期范围 + 取消注释), 零改动既有小节文案。
4. 测试文件首次运行踩到 32-02 半落地状态 (`_first_auction_provider` 位置随 32-02 重构移动) — 等待 32-02 `61e3b07` 合入后重跑全绿; 未修改 32-02 任何文件。

## Honesty invariants locked (AQ-04)

- 失败台账每条恰两键 `{symbol, reason}`; reason 截断 ≤200 (300 字异常 → 恰 200); `empty_response` 与 `str(e)[:200]` 两类互斥。
- 终态如实反映部分失败: 3 symbols 中 1 个失败 → `failed==1`, `backfilled_symbols==2`, `rows==2` (A+C 实际行数, 绝不 3 倍伪造); 湖中无失败 symbol 行。
- `origin=="backfill"` 只在终态 dict; 湖分区列读回无 `origin`/`source` provenance 列。
- BJ (`920146.BJ`) 有 kline_daily 覆盖但上游空 → `failed_symbols` 记 `{"symbol":"920146.BJ","reason":"empty_response"}`, 湖中零 BJ 行 (绝不预填/0 填)。
- fail-closed (probe 非 available) → 0 写 + `reason:"source_unavailable"`。
- 成功准则 4: 罐装 (恒 on) + 网络门 (RUN_NETWORK_TESTS=1) 双变体证明 `auction_virtual_price == kline_daily.open` (≥3 日期逐值, `pytest.approx`)。
- POOL-03: `api/auction_backfill.py` import 面无执行族 token / 无 strategy_cache / 无文件写 pattern; `api/auction_history.py` 仍 GET-only (复验); 既有守卫测试零改动。

## Watchlist proof

`git status --short` 末尾确认: `frontend/src/pages/Watchlist.tsx` 仍是**唯一** unstaged 变更 (M, 用户待办), 本计划全程未读/未触碰该文件。最终提交后 `git status --short` 见下节。

## Final state

```
M frontend/src/pages/Watchlist.tsx        ← 用户所有物, 本计划未读未触碰 (唯一由我留下的 unstaged)
M backend/tests/test_auction_backfill.py  ← 32-02 兄弟执行器在途修改 (其自有文件, 本计划零触碰)
```

Commits (32-03): `8aefc65` docs section · `a1a7cf5` honesty tests · `2906dc7` curl runbook · `2ae0c8d` SUMMARY
Dependencies (32-01/02): `144edc2` (32-01 docs) · `f5a6f59`/`61e3b07`/`885eb32` (32-02)
Watchlist 证明: 提交链全程 `git status --short` 中 `frontend/src/pages/Watchlist.tsx` 恒为 M 且本计划从未 add/commit 它; 兄弟执行器在途的 `test_auction_backfill.py` (轮询修复) 与我的交付物零文件重叠。
