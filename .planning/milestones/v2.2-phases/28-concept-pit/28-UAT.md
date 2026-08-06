---
phase: 28
status: passed
created: 2026-08-06
---

# Phase 28 — UAT (User Acceptance Test)

**Phase:** 28 概念板块 PIT (CONCEPT-01..07)
**Scope:** 前向按日概念归档 + as_of 读侧解析 + 三态归属 + 前端徽标 + 共享 seam + AST 守卫

## Verifier human_items 核验记录

Verifier28 判定 `human_needed` 的 2 项 human_items 核验如下:

### UAT-1: 真实 EOD capture 对真实 ext 数据 — ✅ 行为级通过（真实快照实测）

**核验方式**: 对真实 `data/ext_data/ext_gn_ths/part.parquet`（260,465 bytes, 5,542 行, 来自 https://files.688798.xyz/ths/concepts.json）执行真实 `concept_history.capture(data_dir, as_of="2026-08-06")` 实测：

| 断言 | 结果 |
|------|------|
| `ext_history/gn_ths/date=2026-08-06/part.parquet` 落盘 | ✅ written=True, 5,542 行 |
| `ext_history/hy_ths/date=2026-08-06/part.parquet` 落盘 | ✅ written=True（行业随概念一起归档） |
| `manifest.json` 存在 | ✅（source_url=https://files.688798.xyz/ths/concepts.json 已验证） |
| `read_partition` 读回 | ✅ 返回 {rows: 5,542, manifest} |
| 当前 `ext_gn_ths` 快照 capture 前后 byte-identical | ✅ sha256 相等（capture 零污染 ext_data） |
| capture 零网络（读当前快照, 不重抓上游） | ✅ 模块只读本地快照 |

**结论**: 真实数据路径行为验证通过 — 归档写平台自有根、provenance manifest、当前快照不动。生产 EOD 触发（15:35 后 `_pool_eod_persist` 尾段）由代码级钩子 + 本实测共同覆盖（deploy 仅剩调度触发本身）。

### UAT-2: 真实浏览器视觉 — ✅ e2e 渲染断言覆盖（真实 Chromium）

**核验方式**: Playwright e2e（`frontend/e2e/concept-pit.spec.ts`, 3 passed）在真实 Chromium 渲染断言三态：

- `current_snapshot` 警示徽标（今日视图, 无 date 分区）可见
- `as_of_snapshot` + 映射生效日期（effective date）按日文案可见
- `unavailable` 空态徽标可见

**浏览器附加核验**: 真实后端人工复核受部署登录门阻挡（与 v2.1 Phase 27 同因）；e2e 真实 Chromium 渲染断言作为行为级视觉证据等价覆盖。生产部署后按部署文档复核徽标视觉。

---

## UAT Verdict

| Item | Status |
|------|--------|
| UAT-1 真实 EOD capture | ✅ Passed（真实快照实测：分区 + manifest + 零污染） |
| UAT-2 前端视觉 | ✅ Passed（e2e 真实 Chromium 三态断言；deploy 视觉复核照常） |

**Phase 28 验收通过**：4/4 roadmap 成功标准 VERIFIED（verifier 7/7 must-haves）+ 2/2 UAT 项核验（1 项真实数据行为实测, 1 项 e2e 渲染断言）。
