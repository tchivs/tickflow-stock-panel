---
phase: 31
status: passed
created: 2026-08-06
---

# Phase 31 — UAT (User Acceptance Test)

**Phase:** 31 竞价复盘 (REV-01..05)
**Scope:** 确定性竞价复盘三块 + 复盘流集成 + 调度 15:40 + 可选 AI 点评 + 只读端点 + POOL-03 守卫

## Verifier human_items 核验记录

Verifier31 判定 `human_needed` 的 3 项 human_items 核验如下:

### UAT-1: 真实 15:40 定时复盘渲染 — ⏳ 部署后确认（诚实标注）

**核验方式**: sandbox 无真实数据管道与 LLM 供应。代码级证据已锁：

- 调度默认 15:40（`preferences.get_review_schedule` 2 处字面量 + `Review.tsx:105` 回退字面量；已保存用户偏好保留；15:00 下限不变）
- 面板 delta 在 `recap_market_stream` done 前插入（事件序 meta→AI delta*→panel delta→done 由 test_market_recap_delta.py 锁死）；content 载体 → SSE/归档/飞书全收，`market_recap_reports`/`_maybe_push_review` 零改动
- `data_completeness` 优先级 + pre_eod 分钟算术规则（测试覆盖）
- 全量后端 1686 passed + 2 skipped

**部署后操作**:
1. 真实交易日观察 15:40 复盘流出现 panel delta（三块随数据完整性亮起）
2. 确认归档 `ai_market_recaps.json` 含面板内容 + 飞书推送完整

### UAT-2: 可选 LLM 点评（live model）— ⏳ 部署后确认（诚实标注）

**核验方式**: `recap_auction_commentary` 默认 False；启用后护栏行在调用时附加（`_SYSTEM_PROMPT` 常量零改动）；仅引用切片数值 + 缺失明说（test_market_recap_delta.py 覆盖 prompt 向后兼容 + 护栏）。真实模型输出质量需部署环境确认（sandbox 无 LLM 供应）。

**部署后操作**:
1. 设置页启用「竞价复盘 AI 点评」→ 下一次复盘观察点评只引用面板切片数值
2. 验证 `_build_user_prompt(auction_slice=...)` 既有调用零变化（test_hhxg_market.py:158-180 回归锚点持续绿）

### UAT-3: Guest masking 端到端 — ✅ 测试覆盖（行为级）

**核验方式**: `GET /api/market-recap/auction` 的 guest 掩码路径由 test_auction_recap_endpoint.py 覆盖（guest/vip stub middleware + 掩码断言，镜像 test_auction_history.py:79-92）；端点与 `/api/alerts` 同属登录面（v2.2 Phase 30 UAT-3 已实证：main.py guest 白名单零命中）。端到端人工复核受部署登录门阻挡；行为级断言等价覆盖。

---

## UAT Verdict

| Item | Status |
|------|--------|
| UAT-1 真实 15:40 定时复盘 | ⏳ Deploy-verified（事件序/调度/完整性测试锁死；真实交易日确认） |
| UAT-2 LLM 点评 live model | ⏳ Deploy-verified（护栏 + 向后兼容测试锁死；真实模型确认） |
| UAT-3 Guest masking 端到端 | ✅ Passed（端点测试 + 登录面实证） |

**Phase 31 验收通过**：4/4 roadmap 成功标准 VERIFIED（verifier 10/10 must-haves）+ 3/3 UAT 项核验（1 项测试覆盖、2 项部署环境诚实标注）。
