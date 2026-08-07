# Phase 44 UAT — 部署日执行面 (Deploy-Day Execution)

**Phase:** 44 · **Requirements:** DEP-01..04 · **Date:** 2026-08-07
**Verifier:** `.planning/phases/44-deploy-day/44-VERIFICATION.md` — **PASSED** (4/4, behavior_unverified=7)

## Acceptance Criteria (user perspective)

| # | Criterion | Status | Evidence |
|---|-----------|--------|----------|
| UAT-1 | 凭证/连通性前置 | ✅ MET | .env.example 网关定案注释 (172.18.0.1, 127.0.0.1 refused 实测);deploy_check_connectivity.sh 四模式三态退出码 0/1/2/3;md5 live 核实 HEAD 4/4 (32468e15/4e33c236/a48c48fa/b05e01c7) ∧ 陈旧 3018 4/4 DIFFER — 重建确有必要 |
| UAT-2 | 3 端点 200-body 验证脚本 | ✅ MET | deploy_verify_endpoints.py:401 先验 3/3 → login tf_session → validation 8 键 / backtest {runs,count}+详情 / backfill fail-closed 远未来窗 (构造零上游, requested 如实) + W-5 9 键;exit 0/1/2/3;全 stdlib 零依赖 |
| UAT-3 | D1..D8 runbook 脚本化 | ✅ MET | deploy_day_runbook.sh 全项三态 + JSON 台账 + BLOCKER exit 2;分钟点亮门墙钟 <930min → not_before_1530,引擎 auction_intraday_confirm 命中 (报告层不参与);只读 dry-run 9 项诚实态 exit 0 |
| UAT-4 | 3018 rebuild 配方 | ✅ MET | deploy_rebuild.sh preflight 全流程 (build/boot/health/md5 4/4/零残留) + --apply 五步 (compose up -d + chown -R 999:995 root 容器法, --dry-run grep==2);deploy-verification.md v2.5 节落地 |
| UAT-5 | 守卫 | ✅ MET | 零新依赖 (stdlib-only);Watchlist 零触碰;3018 Up 3 days 仅 1 次只读 exec;:3020 无残留;4 脚本 + .env.example 硬编码键 0 |

## 诚实标注

- **部署日真实事件全部 human-verify 标注** (7 项): 真实登录 200-body 验收、D1..D8 观测 (首个真实交易日)、3018 替换执行、分钟点亮、chown 执行、日志检查、真实 key 配置 — 沙箱已证机制, 真实执行待部署日。
- backfill 验证用远未来窗构造 (requested=0 零上游消耗, 如实记录不锁死)。
- 陈旧容器 4/4 DIFFER 如实 — rebuild 必要性强证据。

## Verdict

**UAT passed** — DEP-01..04 全通过,5 项验收全绿;部署日一次跑通面完整 (连通性/200-body/runbook/rebuild 四脚本),真实事件全部 deploy-gated + human-verify 清单化。
