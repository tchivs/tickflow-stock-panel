# Phase 40 UAT — stockdb 本地通道接入 (Local Source Channel)

**Phase:** 40 · **Requirements:** LOCAL-01..04 · **Date:** 2026-08-07
**Verifier:** `.planning/phases/40-stockdb-local-channel/40-VERIFICATION.md` — **passed** (4/4, behavior_unverified=2)

## Acceptance Criteria (user perspective)

| # | Criterion | Status | Evidence |
|---|-----------|--------|----------|
| UAT-1 | local_stockdb 适配器可用且诚实 (auction=False) | ✅ passed | name=local_stockdb; auction_probe.py:110 枚举 gate 排除; X-API-Key header-only (AST 判据 D); rpm=120 限频对齐; typed 错误 401/400/429 (禁 catch-all); 零新依赖 |
| UAT-2 | 配置 + 注册面完整 (链首/白名单/settings) | ✅ passed | config 两键 env 注入; lazy 单例 (a is b); _BUILTIN_CHAIN daily/minute 链首; 白名单含 local_stockdb (静默回退陷阱锁); health 三态; TestClient 200 |
| UAT-3 | 归一化契约锁死三差异 | ✅ passed | SH600519→600519.SH; volume==42689.0 且 !=4268900.0 (恒等 ×1); aware→naive pl.Date; 夹具冻结 live 体; 写湖仅经既有路径 |
| UAT-4 | 日K/分钟旁路 + 双源守卫 + 湖铁律 | ✅ passed | gap-merge daily+minute 去重; 空帧回退; 异常跳过+warning; 幂等写; 湖 schema 无 provenance 列; 通道身份日志; kline_sync.py 零改动 |
| UAT-5 | 全量回归 + live 冒烟 | ✅ passed | 全量 **1836 passed / 4 skipped**; live 冒烟 600519@2026-08-05 volume==42689.0 双源交叉锚点一致 (宿主); 空 key 401 typed 实测 |

## 诚实标注

- live 冒烟在宿主机跑 (容器内 127.0.0.1 连通性 UNKNOWN → Phase 44 DEP 验证)。
- ETag/304 缓存未启用 (研究建议, PLAN 未含) — 双源真实链长期行为待生产观测。
- 专用 AthenaQuant key 为建议未强制 (适配器接受任意 env key)。

## Verdict

**UAT passed** — 4/4 需求通过,5 项验收标准全绿;3 个人工项入日志 (key 轮换/容器内连通性/ETag 长期行为)。
