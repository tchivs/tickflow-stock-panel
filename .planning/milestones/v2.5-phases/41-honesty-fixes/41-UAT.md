# Phase 41 UAT — 诚实性修复 (Honesty Fixes)

**Phase:** 41 · **Requirements:** HON-01..02 · **Date:** 2026-08-07
**Verifier:** `.planning/phases/41-honesty-fixes/41-VERIFICATION.md` — **PASSED** (HON-01/02, behavior_unverified=3)

## Acceptance Criteria (user perspective)

| # | Criterion | Status | Evidence |
|---|-----------|--------|----------|
| UAT-1 | 403/配额窗与 BJ 真空可区分 | ✅ passed | SourceBlockedError typed 信号 (403 状态码面 + marker 文案面双分类器, 500/timeout→False); 台账第三类 source_blocked 两键形状三态互斥; BJ 真空仍记 empty_response |
| UAT-2 | 回填进度永不冻结 | ✅ passed | 6 条 fail-closed 提前返回路径全部终态 emit (行 217/242/247/286/290/293); 回归锁: 全空帧批量每 symbol 进度行 + failed 计数正确 |
| UAT-3 | 取消路径诚实 | ✅ passed | 独立 cancelled stage + 实际 pct (0/33); done 门 if not cancelled 消除二次 done/100 新发现 bug |
| UAT-4 | CLI 进度可观测 | ✅ passed | on_progress → stderr; --help 冒烟 exit 0 |
| UAT-5 | 既有契约保持 | ✅ passed | test_xyz_provider.py:126-137 空帧不抛契约 untouched 绿; 零新依赖; 全族 74 passed/2 skipped (skip=2 网络门控既有) |

## 诚实标注

- 上游配额窗 200 载荷文案面 marker 表待生产复现核对 (403 状态码面全覆盖)。
- 生产长任务真实取消路径未 live 观测 (fake job_store 测试绿)。
- pool_backfill.py:88-92,115 同类二次 done 反模式 — 观察项转 human_items,建议后续 phase 对齐。

## Verdict

**UAT passed** — HON-01/02 全通过,5 项验收全绿;36-03 事故模式(403 全记 empty_response + 进度冻结)机械关闭。
