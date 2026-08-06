# Deferred Items — Phase 29 (29-01 执行期间发现)

记录范围: 29-01 (BT-02 区间竞价列注入原语) 执行中发现、但**不属本计划任务直接因果**的存量问题
(deviation scope boundary 日志)。不修复, 不重跑构建求证。

| # | 位置 | 描述 | 严重度 | 状态 |
|---|------|------|--------|------|
| 1 | `backend/app/services/screener.py:376` | `PerformanceWarning: Resolving the schema of a LazyFrame is a potentially expensive operation` — 存量 (29-01 前已存在, 与本次改动无关; `test_auction_columns.py` 回归 2 个 warning 均源于此)。建议后续优化为 `LazyFrame.collect_schema()`。 | low | open |

无其他 deferred 项。
