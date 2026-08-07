# 44-03-SUMMARY — DEP-03/04: D1..D8 runbook + rebuild 配方 (wave 3)

**Executor**: ExecP4403 (wave 3, 44-deploy-day)
**Date**: 2026-08-07
**Repo**: /home/orca/source/AthenaQuant
**Plan**: `.planning/phases/44-deploy-day/44-03-PLAN.md` (DEP-03/DEP-04; 0 blockers, 4 warnings)
**HEAD at run**: `9965087` (44-02 summary landed during run; backend md5 baseline unchanged from 8cbce15)

## Deliverables (all committed)

| File | Purpose |
|---|---|
| `backend/scripts/deploy_day_runbook.sh` | DEP-03: D1..D8 三态判定 + JSON 台账 + 分钟点亮门 (只读, 零写入) |
| `backend/scripts/deploy_rebuild.sh` | DEP-04: preflight 模式 (build→temp→boot→md5→零残留) + `--apply` 部署日步骤文档化 |
| `docs/deploy-verification.md` | v2.5 部署日执行面节 (md5 基线 / 连通性定案 / 凭证链 / 脚本清单 / D1..D8 引用 / root-owned 卷清单 / chown 流程 / 执行顺序 / 诚实标注) |
| `.planning/phases/44-deploy-day/44-03-SUMMARY.md` | 本文件 |

## Sandbox verification (honest, all three-state branches exercised)

### deploy_day_runbook.sh (沙箱全项三态)
- **D1** 真实 data (T=2026-08-07): premarket ABSENT → `degraded` 诚实 (部署日 job 首建); fixture 键齐全 → `pass`; fixture strategy_cache 09:10 写入 → `BLOCKER` (隔离破坏)
- **D4** 0 行 → `skipped` (fail-closed 通过态); fixture DB 缺 → `degraded`
- **D2** 当日 enriched 缺失 → `degraded`; fixture (2026-08-05 enriched 5293 行 + snapshot_origin=eod) → `pass`; 0 行分区 → `BLOCKER` (空断言)
- **D6** 无归档 → `degraded` 诚实 (LLM 复盘默认关); 手动均值计算路径验证 (0.005313)
- **D5** 无归档 → `degraded` (pending_human 注记); 三块源在场检查
- **D7** ext_history ABSENT → `degraded`; fixture 双 kind + 零副作用 → `pass`; fixture ext_data 当日写入 → `BLOCKER`
- **D8 sidecar** fixture 三闸门全 pass → `pass`; 台账 skipped=no_data → `skipped_no_data` 零告警; 缺分区 fail-closed → `degraded`
- **minute_light** `--now 09:45` → `not_before_1530` (盘中拒绝, exit 0); 0 分区 → `empty_lake_fail_closed` (诚实通过态); fixture 分区+引擎命中 → `lit`; 分区在场无命中无注记 → `BLOCKER` (exit 2)
- **D3** 未配置 → `conditional_not_configured` 通过态
- BLOCKER 汇总 exit 2 (fixture 3×BLOCKER 验证); 台账键集 {item,date,verdict,evidence,ts} 全项齐全; 零写入哨兵 (kline_auction 248→248, *.tmp 0→0, mtimes 不变)
- 报告层 minute_confirm 不参与 (代码审查确认, 用 backtest_results manifest/part.parquet 引擎结果)

### deploy_rebuild.sh (preflight 沙箱全流程, 2 runs)
- Run 2 (final): build warm **1s** / boot **17s** / `/health` **200** / md5 **4/4 == HEAD** / residue {container:0, port:0, tmpdir:0} / zero_write ok / **exit 0**
- `--apply --dry-run` 打印 `docker compose up -d` + `chown -R 999:995` (grep == 2)
- 3018 陈旧容器哨兵全程零触碰 (只读); temp 副本 root 容器法 (源只读挂载) 实测宿 cp 被 root-owned 0700 阻挡 → fallback 触发
- `docker ps | grep -c preflight` == 0; `ss -tln | grep -c :3020` == 0

### docs (grep 对齐)
- `### v2.5 部署日执行面` 存在 (1); HEAD md5 4 值在文档且与实测一致 (`32468e15…/4e33c236…/a48c48fa…/b05e01c7…`); 旧基线 1be3288b/901d11a9 仅「已过期」语境; 脚本清单 4 项; root-owned 卷清单 + chown 流程完整
- `frontend/src/pages/Watchlist.tsx`: 零读取零触碰 (diff 仅用户既有 unstaged 修改, 本阶段 commit 不含)

## Tests
- 既有回归: `tests/test_auction_backfill_full_universe.py` **14 passed** (脚本无 backend 代码改动; 全量回归 orchestrator 统一跳过)
- 新脚本验证: bash -n 双脚本 + 沙箱三态全项 (如上) + 计划 verify 序列 (jq 断言全部通过)

## Deviations (all honest, none affecting verdict)
1. temp 副本路径用 `/tmp/preflight-data-4403` (44-01 ExecP4401 自建自清其 `/tmp/preflight-data`; 互不踩踏, 已协调)
2. preflight run 1 遇 `set -o pipefail` + root-owned 目录 find Permission denied → exit 1; 修复 = find 管道 `|| true` + 哨兵基线移到 baseline 段 (对真实数据目录而非 temp); run 2 全绿
3. D2 当日 (2026-08-07) enriched 分区不存在 (EOD 未跑) → 诚实 `degraded` (计划 verify 的 "enriched 251 分区 → pass" 以 fixture 历史日期 2026-08-05 验证 pass 分支)
4. D6/D5 复盘归档路径: LLM 复盘默认关 (preferences.py:441) → 沙箱无归档 → 诚实 degraded + pending_human 注记, 绝不伪造 pass

## 诚实边界 (unchanged)
部署日真实事件 (premarket 落盘 / sidecar 点亮 / 分钟湖写入 / 3018 重建替换) = 真实交易日/部署动作观测, operator 在观测窗逐项三态记录; 沙箱证的是脚本逻辑与 DTO 形状。
