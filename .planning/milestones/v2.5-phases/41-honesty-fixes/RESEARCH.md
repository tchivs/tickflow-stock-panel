# Phase 41: 诚实性修复 (Honesty Fixes) — 现状核实与锚点核查

**Researched:** 2026-08-07 · **Method:** 源码直读 (零网络, 行号为当前 HEAD 实测) · **Confidence:** HIGH (全部锚点逐一核实; 唯一 UNKNOWN = xyz 403 真实响应体结构)

## 现状核实 (源码直读)

### HON-01 靶点 — xyz 三态化 (403-vs-真空吞错链, PITFALLS P2)
- `backend/app/data_providers/xyz_provider.py:189-198` — `get_auction` 的 try/except (`except Exception as e` @ :194) 把所有 `_call_tool` 异常塌缩为 `pl.DataFrame()` 空帧。
- `:228-250` — `_call_tool`: HTTP 错误 (:243 `raise_for_status` / :244 `resp.json` 的 catch-all @ :245-247 → `""`); `"error" in data` (:248-250) → `""`。**403/配额窗 markers 与超时/真空完全同标签**。
- `:130-151` — `_price_frame` 调 `_call_tool` 无 try/except (daily/minute 路径; HON-01 只修竞价路径, daily/minute 契约不变, 见 PATTERNS 关键差异点)。
- 结论: 36-03 事故链成立 — 403 → `""` → 空帧 → 台账 `empty_response`, 与 BJ 永久缺口不可区分; R1 重试 (`auction_backfill.py:139-152` marker 匹配) 对 xyz 是**死代码** (xyz 从不抛异常)。

### HON-02 靶点 — fail-closed 零 emit / 取消=done/100 (PITFALLS P3)
- `backend/app/services/auction_backfill.py` 五条 fail-closed 提前返回全部**无 emit** 直接 `return _fail_closed(...)`: :200 (`source_unavailable`)、:224 (`no_scope`)、:228 (`no_provider`)、:266 (预检异常 `str(e)[:_ERROR_DETAIL_MAX]`)、:268 (`preflight_empty`) → 这就是「进度冻结」的真因 (CLI 零进度)。
- **ARCH 行号偏差核实通过**: 逐 symbol 进度 emit 已在循环内 **:308-313** (自 733b650e, git log 核实); 需求/研究引用的「283-296」已过期 — 本计划按 :308-313 为准, **不重复实现**。
- **新发现 (计划外第二个 bug)**: 取消路径 :282 `emit("done", 100, "回填被取消")` + break 之后, 循环尾 :314 `emit("done", 100, f"回填完成: …")` 仍会执行 → 取消时 `done/100` 出现**两次**, 双倍误导。HON-02 必须给 done emit 加 `cancelled` 门。
- `scripts/auction_backfill.py:139` — CLI 已接 `on_progress` 但打 **stdout** (`print(..., flush=True)`); fail-closed 运行零 emit → 用户视角零进度输出 (需求「现零进度输出」核实成立)。修 = 打 stderr。

### 消费面 (HON-01 下游)
- `auction_probe.py:161-167` — `resolve_auction_probe` `except Exception` → `status=error` + `detail=str(exc)[:_ERROR_DETAIL_MAX]`; 无 policy-block 分支。HON-01 需加 `except SourceBlockedError` → `fail_closed` + `detail="source_blocked"`。
- `verify_auction_backfill.py:187-217` — `_classify_source_block` (区分门): 非 BJ `empty_response` 一律「疑似源受阻」(:213-215, 与 BJ 永久缺口同标签的诚实缺口, FA-05-BJ-STANCE)。HON-01 后 `source_blocked` 可独立归类 → 该门必须更新, 且既有测试 `test_verify_partial_source_block_yes_non_bj_failures` 的断言随之更新 (空响应文案不再含 403 伪装含义)。
- 台账写入点: `auction_backfill.py:300-304` (异常 → `str(e)[:200]`)、:289-293 (空 + 有 kline_daily 覆盖 → `empty_response`); 两键形状 `{symbol, reason}` 核实不变。

## 与计划假设的偏差

| 假设 | 核实结果 |
|---|---|
| fail-closed 路径 :200/224/228/266/268 | ✅ 全对, 五条路径零 emit |
| 逐 symbol emit 在 :308-313 | ✅ 已存在 (733b650e), 勿重复实现 |
| test_xyz_provider.py:126-137 空帧契约 | ✅ Test 4 (空载荷/异常 → 空帧不抛), HON-01 不触碰 |
| 取消路径 | ⚠️ 额外发现二次 done/100 bug (计划含修复, 超需求但同属 P3) |
| CLI 零进度 | ✅ 已接 on_progress 但打 stdout; 修 = 改 stderr |
| xyz 403 配额窗响应体结构 | ❓ UNKNOWN (2h 窗未触发, v2.5 RESEARCH 同 flag) — 分类器双信号 (HTTP 403 + 文案 markers), 复现时回填定稿 |

## 设计决策 (计划依据)
1. `SourceBlockedError` 放 `backend/app/data_providers/base.py` (ProviderCapabilities 同契约模块, 服务面 import 零 xyz 耦合) — 镜像 `stockdb_provider.py:59-71` typed 异常纪律 (surfaced, never faked as empty)。
2. 分类器双信号: 状态码 **403** 或响应/错误文案命中 `_POLICY_BLOCK_MARKERS` → 抛 `SourceBlockedError`; 其余 4xx/5xx 与超时 → `""` (空帧契约不变)。
3. `_price_frame` (daily/minute) 捕 `SourceBlockedError` → 空帧降级保留 — HON-01 只修竞价路径标签诚实性 (scope 决策; 每日/分钟路径 403 现状即空帧, 不在本 phase 变更面)。
4. `_fetch_auction` **先捕** `SourceBlockedError` 直接重抛 — R1 重试结构性只对可重试态; 即便错误消息含 `_RATE_LIMIT_MARKERS` 重叠词 (如「带宽」) 也绝不误重试 (2h 窗 × 5537 symbols 放大即 DoS)。
5. fail-closed emit: 每条提前返回一行 `emit("auction_backfill", 0, f"fail-closed: {reason}")`; 「每 symbol 一行」由循环内 :308-313 承担 (已存在, 回归锁验证)。
