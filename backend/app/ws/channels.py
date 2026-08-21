"""频道名常量 + 频道→事件类型映射 (D-08)。

频道命名:
  quotes      — 行情
  alerts      — 告警
  portfolio   — 持仓
  review      — 复盘
  depth       — 五档
  run:{run_id}        — 任务进度 (动态)
  analysis:{symbol}   — AI 分析 (动态)
"""
from __future__ import annotations

# 静态频道名
QUOTES = "quotes"
ALERTS = "alerts"
PORTFOLIO = "portfolio"
REVIEW = "review"
DEPTH = "depth"

# 动态频道前缀
RUN_PREFIX = "run:"
ANALYSIS_PREFIX = "analysis:"

# 频道 → 事件类型映射 (用于反向查询: 某事件属于哪个频道)
CHANNEL_EVENT_MAP: dict[str, list[str]] = {
    QUOTES: ["quotes_updated", "strategy_results_updated"],
    ALERTS: ["strategy_alert"],
    PORTFOLIO: ["portfolio_updated"],
    REVIEW: ["review_progress"],
    DEPTH: ["depth_updated"],
}
