# Phase 41: 诚实性修复 — Pattern Map

**Mapped:** 2026-08-07 · **Files:** 0 新增 / 8 修改 · **Analogs:** 全 exact (无 No-Analog; 设计差异非缺口)

## File Classification

| File | Role | Closest Analog | Match |
|---|---|---|---|
| `backend/app/data_providers/base.py` (改, +`SourceBlockedError`) | 契约 | `stockdb_provider.py:59-71` (typed 异常族: 401/429/400 surfaced, never faked as empty) + `base.py:24-48` (ProviderCapabilities 所在契约模块) | exact |
| `backend/app/data_providers/xyz_provider.py` (改) | provider | `stockdb_provider.py:59-71` (typed 错误先例) + `tickflow/policy.py:152-156` (403/权限关键词分类判据) | exact |
| `backend/app/services/auction_backfill.py` (改) | service | 自身 :52-63 `_fail_closed` / :139-152 `_fetch_auction` (R1 marker 重试) / :300-304 台账写入 / :308-313 循环 emit | exact |
| `backend/app/services/auction_probe.py` (改) | service | 自身 :29-31 错误常量纪律 (`_ERROR_DETAIL_MAX`/`FAIL_CLOSED_DETAIL`) + :161-167 error verdict | exact |
| `backend/scripts/verify_auction_backfill.py` (改) | script | 自身 :187-217 `_classify_source_block` 区分门 | exact |
| `backend/scripts/auction_backfill.py` (改) | CLI | 自身 :139 `on_progress` lambda (stdout → stderr) | exact |
| `backend/tests/{test_xyz_provider,test_auction_backfill,test_auction_backfill_honesty,test_auction_probe,test_verify_auction_backfill}.py` (改) | test | 各文件既有 helper (`_provider_with` :27-36 / `FakeAuctionProvider` :25-39 + `_patch_live` :94-101 / `_FakeAuctionProvider`+`_run_job` / `FakeAuctionProvider`+`_probe` / `_run` :29-38) | exact |

## Pattern Assignments

### xyz 三态化 (HON-01) — 镜像 stockdb typed 异常 + policy 关键词判据

- **typed 异常** (镜像 `stockdb_provider.py:59-71`): `class SourceBlockedError(Exception)` — 上游策略封锁 (HTTP 403 / 配额窗), 非瞬时、重试无意义; 消息截断 ≤200 字符 (镜像 `auction_probe.py:29` 纪律, 不泄完整 body)。
- **分类器** (镜像 `tickflow/policy.py:152-156` 关键词判据 + v2.5 RESEARCH「HTTP 403 + 文案 markers 双信号」): `_is_policy_block(status, text)` — `status == 403` 或 text 命中 `_POLICY_BLOCK_MARKERS`; 其余 4xx/5xx/超时 → `""` (空帧契约不变)。
- **传播链**: `_call_tool` 抛 `SourceBlockedError` → `get_auction` `except SourceBlockedError: raise` (绝不吞成空帧) → `_fetch_auction` `except SourceBlockedError: raise` (R1 零重试) → 预检/循环台账 reason `"source_blocked"` / probe verdict `fail_closed`+`detail="source_blocked"`。
- **反模式禁复制**: xyz 自身 :243-247/:248-250 catch-all → `""`; free_stockdb `except Exception: return []` (PITFALLS P2); 新代码严禁把 `SourceBlockedError` 归入通用 except。

### 台账第三类 reason (HON-01)

- 写入点: 循环 except 分支 (镜像 :300-304 结构) — `failed_symbols.append({"symbol": sym, "reason": "source_blocked"})`, 与 `empty_response` (:289-293) / `str(e)[:200]` 三态互斥; 预检 except → `_fail_closed(rpm, "source_blocked")`。
- 消费点: `verify_auction_backfill.py:187-217` 区分门 — `source_blocked` 非 BJ 条目 → 确定性 YES (策略封锁); `empty_response` 非 BJ 条目 → 真空缺口 (403 伪装已不存在), 文案更新 + 既有测试断言同步。

### emit 模式 (HON-02)

- 既有 emit 形状: `emit(stage, pct, msg)`; 循环内 :308-313 逐 symbol 进度 (自 733b650e, **勿重复实现**)。
- 新增 `_emit_fail_closed(emit, reason)` 模块级 helper (镜像 `_fail_closed` 命名): 五条 fail-closed 提前返回 (:200/224/228/266/268) 各补一行 `emit("auction_backfill", 0, f"fail-closed: {reason}")`。
- 取消 stage: `emit("cancelled", int(100*i/requested), ...)` (实际 pct, 绝不 `done`/100); `cancelled` 标志门住循环尾的 done emit (修二次 done/100 bug)。

### CLI (HON-02)

- 镜像 :139 既有 lambda, 仅加 `file=sys.stderr`: `on_progress=lambda stage, pct, msg, **kw: print(f"[progress] {msg}", file=sys.stderr, flush=True)` — 进度走 stderr, stdout 留给终态摘要/台账 (operator 管道语义)。

## 命名与测试惯例

- **reason 常量**: 台账 reason 用字面量 `"source_blocked"` (与 `"empty_response"`、`str(e)[:200]` 并列; 两键形状 `{symbol, reason}` 不变, 不得加第三键)。
- **probe detail 常量**: `SOURCE_BLOCKED_DETAIL = "source_blocked"` (镜像 `FAIL_CLOSED_DETAIL` :30 位置, 逐字匹配测试可断言)。
- **测试注入面**:
  - xyz 分类器级: `provider._client.post = lambda *a, **k: httpx.Response(403, request=httpx.Request("POST", url), text=...)` — 真实 `Response.raise_for_status()` 才抛 `HTTPStatusError`; 传播级复用 `_provider_with(SourceBlockedError(...))` (:27-36)。
  - backfill: `FakeAuctionProvider(exc_by_symbol={...: SourceBlockedError(...)})` (:25-39) + `_patch_live` (:94-101)。
  - probe: `FakeAuctionProvider(exc=SourceBlockedError(...))` + `_probe(...)` helper。
  - verify: `_run` helper + tmp 台账 JSON。
- **回归锁 (HON-02)**: 全空帧批量 = 预检 symbol 选**无 kline_daily 覆盖**者 (预检通过) + 其余有覆盖 → 循环逐 symbol 空帧 → 每 symbol 进度行 + `empty_response` 计数。若全部 symbol 有覆盖, 批量会整体走 `preflight_empty` 提前返回, 循环永不启动 — 回归锁必须绕过此门才能断言循环内逐 symbol 行。

## 关键差异点 (HON-01 后 vs 现状反模式)

| 维度 | HON-01/02 后 | 现状 (反模式) |
|---|---|---|
| 403/配额窗 | `SourceBlockedError` 上抛 → 台账 `source_blocked` | 塌缩 `""` → 空帧 → `empty_response` (36-03 事故) |
| 其余网络错误 | `""` → 空帧不抛 (契约不变, test :126-137 保持绿) | 同左 |
| R1 重试 | `SourceBlockedError` 先捕重抛 (零重试); marker 匹配只对可重试态 | 对 xyz 死代码 |
| 取消路径 | `cancelled`/实际 pct, 无 done | `done/100` 两次 (误导) |
| fail-closed 进度 | 五路径各一行含 reason | 零 emit (进度冻结) |
| CLI 进度 | stderr | stdout (fail-closed 零输出) |
| daily/minute 403 | `_price_frame` 捕 → 空帧降级 (scope 决策, 不变更面) | 空帧 (同左, 未修) |

## Metadata

**Scope:** `backend/app/data_providers/{base,xyz_provider}.py` · `backend/app/services/{auction_backfill,auction_probe}.py` · `backend/scripts/{auction_backfill,verify_auction_backfill}.py` · `backend/tests/{test_xyz_provider,test_auction_backfill,test_auction_backfill_honesty,test_auction_probe,test_verify_auction_backfill}.py` · **Patterns source:** RESEARCH.md (行号全部源码直读核实) · **Valid until:** 2026-09-06
