# FA-05 — BJ 板块覆盖上限诚实立场 (BJ 恒空 333 / 94.0% 天花板 / 源受阻区分)

**Status**: 永久立场文档 (operator-facing) — 36-03 将要点折入 `docs/features.md`
**Date**: 2026-08-07
**Source**: `.planning/research/v2.4-full-universe/AUCTION-FULL-BACKFILL.md` §3.2 (同日 live 实测) + 本波次运行观测
**Anchored test**: `tests/test_auction_backfill_honesty.py:262-278` (`test_auction_backfill_bj_stock_empty_response_recorded`)

## 1. 实测上游缺口 (2026-08-07 live, 28 次请求直连 xyz MCP)

- 湖内 BJ universe = **333 symbols, 全为 920xxx 新号段** (92 前缀; `kline_daily` 湖 DISTINCT,
  与 32-02 逐字一致: SZ 2894 / SH 2310 / BJ 333, 总计 5537)。
- 6 只 920xxx live 探针 (920016 / 920029 / 920033 / 920047 / 920066 / 920089) → **全部 0 行** (0.38-1.78s)。
- 裸码 `920016` → 0 行 (非报错)。
- **5 种替代格式全部 `请求参数错误`**:
  - `BJ920016`
  - `920016.BJ`
  - `bj920016`
  - `"bj 920016"`
  - `"BJ 920016"`
- **结论**: 上游无 BJ 集合竞价数据, 且**非代码格式问题** —— 「改号段/换格式即可」假设被 5 格式反证排除。

## 2. 台账行为 (诚实记录, 绝不伪造)

- 全部 333 BJ 在终态 `failed_symbols` 记 `{symbol, reason: "empty_response"}`, symbol ∈ `92xxxxx.BJ`。
- **绝不预填/0 填** (湖中无 BJ 行)、绝不重试到永远、绝不把「未覆盖」包装成「已覆盖」。
- 锚定: `test_auction_backfill_bj_stock_empty_response_recorded`
  (`tests/test_auction_backfill_honesty.py:262-278`, 湖内无 BJ 行断言在内)。

## 3. 覆盖口径 (≤94.0%, 永不 100%)

- 覆盖 = `auction_symbol_count / 5537` = 5204/5537 = **0.940**; 框架永远是 `已回填/5537`。
- 任何报告 (SUMMARY / features.md / recap) **不得打印 100%**, 不得插值, 不得声称全市场覆盖。
- `rows_present < expected` 时保持 honest-partial 框架: verify 脚本 fail-closed (exit 1),
  明示「回填进行中/中断/上游源受阻, 不得视为完成」。
- 湖外推导的 verify 脚本 `[6] coverage` 同一口径 (打印小数如 `0.940` / `0.007`, 永不 "100%")。

## 4. 恢复路径 (上游补 BJ 后自动接上, 零代码改动)

- 若上游日后提供 BJ 竞价数据: `--all --only-missing` 顶补的覆盖预扫描 (FA-02) 自动抓取并写湖。
- **顶补稳定性门 (W-1 修正)**: BJ 333 永远「待回填」→ 顶补 `requested=333` 是**预期**, 不是失败;
  以 **`backfilled_symbols == 0 && rows == 0`** 为稳定判据 (连续两次),
  `failed == 333` 全 BJ `empty_response` 为预期噪声 (幂等重请求 ~6 分钟, 无新增行)。

## 5. 源受阻与 BJ 缺口的区分 (诚实缺口, 2026-08-07 运行事件后新增)

- **事件**: 全量运行 ~32 标的成功后, 上游 xyz MCP 开始持续 403 Forbidden (10+ 分钟,
  单请求复测仍 403), 由 operator 停止 (36-02-SUMMARY.md 事故记录)。
- **机制**: `xyz_provider.get_auction` 把 403 异常吞成空帧 (`xyz_provider.py:192-196`) →
  服务层空响应分支记 `empty_response` —— 与 BJ 永久缺口 **同标签**。
- **`reason` 字段无法区分「上游无数据」(BJ 永久) 与「上游受阻」(403/配额)** —— 都是 `empty_response`。
- **区分手段: 按 symbol 集合判断** — BJ 号段 `empty_response` = 已知永久缺口;
  非 BJ (SZ/SH) 标的 `empty_response` = **疑似源受阻**, 需重试/顶补, 不得当作永久缺口归档。
- verify 脚本 `--ledger` 归类: 台账含非 BJ `empty_response` → `suspected source-block: YES`;
  全为 .BJ → `NO`; 无台账 → `UNKNOWN` (明示缺口, 不猜)。
- **运营含义**: 单会话全量 FA-04 验收被源配额阻塞时, 走**分块突发策略** (小批量 symbol 批次 +
  冷却 + `--only-missing` 续跑) — 验收判据只看湖终态 (verify 脚本 PASS), **不要求单会话完成**。

## 6. 本波次运行台账证据 (终态数字待顶补完成后回填)

- 首次全量运行 (2026-08-07 08:27-08:37): 32 成功 → ~200 失败 (403 派生 `empty_response`) →
  operator 停止; 湖终: 37 symbols / 8,951 rows / 248 分区 / 交叉 mismatch 0 / 无 `.tmp`。
  无终态台账 (进程未到完成点 — CLI 仅在完成时写 `--out`)。
- 预期终态 (RESEARCH §3.4 验收口径): `requested=5537, backfilled_symbols≈5204, rows≈1,290,592,
  dates=248, failed=333` 全为 `{symbol, reason:"empty_response"}` 且 symbol ∈ BJ 920 号段。
- 顶补稳定后把实际终态 dict 事实贴入本段 (供 36-03 SUMMARY 消费)。
