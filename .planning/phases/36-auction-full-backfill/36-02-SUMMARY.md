# 36-02 SUMMARY — 全量回填运行支持 (FA-04 runbook/验证工具 + FA-05 BJ 立场)

**Plan:** `.planning/phases/36-auction-full-backfill/36-02-PLAN.md`
**Executor:** ExecutorP3602 · **Wave:** 2 (parallel with 36-03, after 36-01) · **Depends:** 36-01 (DONE, 已提交)
**Date:** 2026-08-07 · **Status:** COMPLETE (代码/文档交付齐; 运行证据因上游 403 事件部分顺延 — 见事故记录)

## Deliverables

| Artifact | Contains |
|---|---|
| `backend/scripts/verify_auction_backfill.py` | FA-04 只读验收工具: 湖六项事实 + 完整性裁决 (0=PASS/1=PARTIAL/2=FAIL) + `--ledger` 疑似源受阻归类; 零写入/零网络/零新依赖 |
| `backend/tests/test_verify_auction_backfill.py` | 9 个 hermetic 用例 (token `verify`): PASS 完整湖 / PARTIAL fail-closed / 交叉 mismatch FAIL / .tmp FAIL / 满覆盖永不 "100%" / 只读守卫 / 源受阻 YES·NO·UNKNOWN 三归类 |
| `.planning/phases/36-auction-full-backfill/FA-05-BJ-STANCE.md` | FA-05 永久立场: BJ 333 恒空 5 格式实测、empty_response 台账锚定、94.0% 口径、恢复路径、源受阻区分 (403 事件后新增) |
| `.planning/phases/36-auction-full-backfill/36-02-SUMMARY.md` | 本文件 |

## Commits (2 + 本文件)

```
41da089 feat(phase-36): FA-04 read-only verify script — lake six-facts (universe/lake/BJ-ledger/cross-check/.tmp/coverage) + completeness verdict 0=PASS·1=PARTIAL·2=FAIL + --ledger suspected source-block classification; zero writes/network/deps
0bc5dac test(phase-36): verify tool hermetic tests — PASS complete-lake / PARTIAL fail-closed / FAIL invariants (mismatch, .tmp) / never-100% framing / read-only guard / suspected source-block YES·NO·UNKNOWN (9 cases)
```

## Verification

```
cd backend && .venv/bin/python -m pytest tests/test_verify_auction_backfill.py -q
   → 9 passed

cd backend && .venv/bin/python scripts/verify_auction_backfill.py   # dry-run against frozen partial lake (post-stop)
=== verify_auction_backfill (read-only, lake-derived) ===
[1] universe:      symbols=5537 (SZ 2894 / SH 2310 / BJ 333), rows=1326996
[2] lake:          partitions=248/248, rows=8951 (floor 1254547 / nominal 1290592), symbols=37/5204
[3] BJ ledger:     missing=333/333 (92xxxxx.BJ), present-in-lake=0, off-segment=0; sample: 920000.BJ 920001.BJ 920002.BJ 920003.BJ 920005.BJ ...
[4] cross-check:   dates=3 (2026-08-05, 2026-08-04, 2026-08-03), pairs=108, mismatches=0
[5] .tmp residue:  0
[6] coverage:      auction_symbol_count/5537 = 0.007 — PARTIAL
verdict: PARTIAL — 回填进行中/中断/上游源受阻, 不得视为完成 (fail-closed): missing_non_bj=5167, rows=8951 (floor 1242001), partitions=248/248 (exit 1)
suspected source-block: UNKNOWN — 未传 --ledger 运行台账; 注意: 上游 403/配额吞请求的空返回与 BJ 永久缺口同样记 empty_response (reason 无法区分, 诚实缺口见 FA-05-BJ-STANCE.md), 传 --ledger 即可归类
EXIT=1
```

- **fail-closed/partial-honest 行为符合交付要求**: 运行中/中断/源受阻的湖 → 退出 1, 诚实数字,
  绝不假装完成; 已写部分 (37 symbols) 交叉校验 0 mismatch — 一致性不变量与覆盖完整性分离。
- **行数预期从湖推导** (非硬编码): floor = kline_daily 非 BJ (symbol,date) 对数 1,254,547
  (新股/停牌短历史), nominal = 5204×248 = 1,290,592 — 两数都打印, 完整判定取
  `[0.99×floor, nominal]` 带 (实测 kline_daily 有 36,045 个非 BJ 缺口对, 硬编码 1,290,592
  ±1% 会对健康终态误报 partial)。
- **只读守卫**: 测试断言跑完脚本后湖文件树字节级不变。

## 运行事故记录 (FA-04 T1/T2 执行观测 — 上游 403 事件)

1. **启动 (T1)**: 08:23:33 首次 launch 产生 `no_scope` fail-closed 台账占位 (进程未留),
   08:27:06 二次 launch (pid 397197) 健康运行: `[progress] 回填 5537 个标的 × 248 日…` →
   `1/5537 … 32/5537 (成功 32, 失败 0)`, ~2.3s/标的, 湖从 2 pilot → 37 symbols / 8,951 rows。
   启动时刻与 EOD 窗口无冲突 (周末, 非 15:00-15:30 Asia/Shanghai)。
2. **403 源受阻 (T2 观测)**: 第 ~33 标的起上游 xyz MCP 持续 `403 Forbidden` (~200 次,
   10+ 分钟; 单请求复测仍 403) → operator 停止运行 (进程已退, 无终态台账 — CLI 仅完成时写
   `--out`; `/tmp/auction-backfill-v24.json` 仍是 08:23 的 `no_scope` 占位, 非失败信号)。
3. **诚实缺口 (已文档化)**: `xyz_provider.get_auction` 把 403 吞成空帧 (xyz_provider.py:192-196)
   → 服务层记 `empty_response` — 与 BJ 永久缺口同标签, `reason` 无法区分; 区分靠 symbol 集合
   (BJ=永久, 非 BJ=疑似源受阻)。详见 FA-05-BJ-STANCE.md §5。
4. **监控发现 (runbook 补充)**: 空响应分支 `continue` 在 per-symbol emit **之前** →
   大规模空返回事件时日志只有错误行、`[progress]` 冻结 — 与「日志完全不动」(死进程) 是两种
   状态: 前者是源受阻 mass-failure (作业在推进台账), 后者是真 stall。两者作业都存活,
   恢复路径同为 `--all --only-missing` 续跑, **绝不 SIGKILL 健康作业**。
5. **FA-04 单会话全量验收被源配额阻塞** (operator 判定): 恢复路径改走**分块突发策略** —
   小批量 symbol 批次 + 冷却 + `--only-missing` 续跑; 验收判据只看湖终态 (verify PASS),
   不要求单会话完成 (verify 脚本不假设单会话)。

## Top-up 程序 (T3, W-1 修正后)

- 因回填当时在跑 (无锁写缝) + 现已停止且上游受阻, 本波次**未执行顶补** — 程序就绪:
  `--all --only-missing --rpm 60` → 预期日志 `覆盖扫描: 跳过 5204 已全覆盖, 待回填 333 (BJ)`
  → 终态 `requested=333, backfilled=0, failed=333` (全 BJ empty_response), `rows=0`。
- **W-1 稳定性门 (修正)**: `requested == 0` 不可达 (BJ 333 永不被覆盖) → 判据改为
  **连续两次 `backfilled_symbols == 0 && rows == 0`**, `failed == 333` 全 BJ 为预期噪声。
- 源恢复后: 首轮顶补会抓回 403 期间未写的 ~5167 SZ/SH (这些标的在湖中无完整覆盖 →
  覆盖预扫描判为未覆盖 → 整窗重拉), 后续两轮 0 新增即稳定。

## Acceptance checklist (T6) — 现状

| # | Check | 状态 |
|---|---|---|
| 1 | 台账终态 dict | ⏳ 顺延 — 首次运行未到完成点; 恢复后由 `--out` 台账提供 |
| 2 | 台账诚实性 (failed 全 BJ empty_response) | ⏳ 顺延 — 预期终态 `failed=333` 全 BJ; 403 事件的非 BJ empty_response 已被 stance doc §5 归类为疑似源受阻 (非归档) |
| 3 | 湖: 248 分区 / ≈1,290,592 行 / ≈5204 symbols | ⏳ 源受阻 — verify 脚本就绪, 当前湖 37/5204 → PARTIAL exit 1 (fail-closed 正确) |
| 4 | 交叉校验 mismatch=0 | ✅ 已可验: 当前已写部分 0 mismatch (3 日 x 37 symbols) |
| 5 | 顶补稳定 (连续两次 0 新增) | ⏳ 顺延 — 上游恢复后执行 |
| 6 | BJ 天花板 333 / 0.940 | ✅ 已可验: 湖 BJ 缺失 333/333、湖内 BJ 0、口径小数 (0.007/0.940) 永不 "100%" |

## Deviations (相对 36-02-PLAN)

1. **W-1 (HIGH) 应用**: 顶补稳定性门 `backfilled==0 && rows==0` (非 `requested==0`);
   预期顶补日志 `跳过 5204 已全覆盖, 待回填 333`。计划 T3/T6 原文数字已修正 (见上)。
2. **W-5 (LOW) 应用**: `kline_daily` 视图实为 repository.py:146-147 (非 :162-164) —
   verify 脚本不依赖行号, 直接走 repo 注册视图。
3. **verify 脚本 pre-run「exit 0」验收被取代**: 预跑基线时刻已过 (36-01 落地即启动),
   且交付要求 dry-run 对进行中/中断湖必须 fail-closed → 脚本默认以「预期终态」为 PASS 门,
   pre-run 2-symbol 湖亦为 PARTIAL exit 1 (诚实); 替代证明 = 9 个 hermetic 测试含完整湖 PASS
   分支 + 实湖 dry-run (exit 1, 数字诚实)。
4. **无终态台账**: 运行被 operator 中止于完成点之前 → `--out` 从未写终态 dict
   (仅 08:23 的 `no_scope` 占位)。RUN-LEDGER/RUN-VERIFY 终态证据顺延至恢复后 (36-03 消费)。
5. **单会话全量 FA-04 阻塞**: 上游 403 持续 → operator 改走分块突发 + `--only-missing` 续跑;
   未写任何假定单会话完成的代码 (verify 判定只信湖终态)。
6. **未触碰 `backend/app/*`**: 诚实缺口 (403→empty_response 同标签、空响应分支跳过 emit)
   的代码修复不在本波次范围 (36-01 已落地, 契约禁止) — 已文档化, 建议后续 phase 修
   (a) 403/网络异常在 provider 层区分并上抛为结构化 reason; (b) empty 分支 emit 移至 continue 前)。
7. **仅新增 4 个文件** (验证脚本 + 其测试 + stance doc + 本 SUMMARY); `docs/features.md` 未动
   (36-03 所有), `frontend/src/pages/Watchlist.tsx` 未读未触。

## Handoff → 36-03

- FA-05 要点 (5 格式 verbatim / 94.0% 口径 / 源受阻区分) 折入 `docs/features.md` (36-03 T3 项 6)。
- 终态台账证据: 恢复后首轮顶补的 `--out` JSON + `verify_auction_backfill.py` 输出存档为
  `RUN-LEDGER-<TS>.json` / `RUN-VERIFY-<TS>.txt` (T6 要求)。
- 诚实缺口修复建议 (deviation 6) 纳入后续 phase 排期。

## Watchlist proof

`git status --short` (final): 唯一未暂存变更 = `M frontend/src/pages/Watchlist.tsx` — 其余全部已提交。
