# Phase 39 UAT — 部署验证与残留 (Deploy Verification & Residue)

**Phase:** 39 · **Requirements:** DV-01..04 · **Date:** 2026-08-07
**Verifier:** `.planning/phases/39-deploy-verification/39-VERIFICATION.md` — **passed** (4/4, behavior_unverified=3, 零伪造)

## Acceptance Criteria (user perspective)

| # | Criterion | Status | Evidence |
|---|-----------|--------|----------|
| UAT-1 | D8 部署配方预检 — build HEAD + 独立容器 boot + 新端点在场 + md5 parity | ✅ passed | build **66s exit 0** (preflight 70bcda0bcc2c);boot 18s `/health 200 v1.2.0`;openapi 301 路径含 **3/3 新路由**;md5 parity **4/4 preflight==HEAD** vs stale 3018 全 DIFFER;POST 从未发送;零残留 (容器/临时数据/3020 全释放),3018 陈旧容器 untouched |
| UAT-2 | 部署清单 v2.4 刷新 — 8 项实测事实 + parity | ✅ passed | deploy-verification.md v2.4 节 (line 196, +25/-0 append);8+ 事实全带 source refs;`## ` 集保持 10;header-drift 0;banner blockquote 原样;HEAD 2453366 |
| UAT-3 | 诚实缺口汇总 — 4 gaps × 证据+owner+trigger+pass-state | ✅ passed | GAPS.md: G1 premarket 双门禁 / G2 BJ 上限 94.0% / G3 分钟 live-day gate / G4 AI-key 默认关;15 anchors 抽查逐字命中;pass-state 全 fail-closed 诚实 |
| UAT-4 | 观测窗口计划 — D1..D8 日历 + 排序约束 | ✅ passed | OBSERVATION-WINDOW.md 8 行日历 + 5 条显式约束 (D4 after D1 / D5 after D2 / D7 ≥5 交易日 / D3 conditional / D8 rebuild) + 填表模板;与 runbook 逐项一致 |
| UAT-5 | 部署面诚实 — 401 门不伪造 200;真实日观察 deploy-gated | ✅ passed | 3 新端点 401 如实记录 (auth-gated);200-body 验证 deploy-time;D1/D2/D4/D5/D7 观测入日历;behavior_unverified=3 明示 |

## 诚实标注

- 沙箱预检 ≠ 真实部署:新端点 200-body、真实交易日观察、D3 外部源、全量 campaign(配额 ~2h 窗/≤40 burst/数周)全部 deploy-gated,零伪造。
- 预检镜像 (inert) 留在 docker store — 无容器实例,cleanup 声明 (容器+临时数据+端口) 全部确认。

## Verdict

**UAT passed** — 4/4 需求通过,5 项验收标准全绿,deploy-gated 项全部日历化 + 诚实标注。
