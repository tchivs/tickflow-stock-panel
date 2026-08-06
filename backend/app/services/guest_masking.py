"""游客会话脱敏序列化变换 — GUEST-01/GUEST-02 (仅 DTO 边界, 显示层)。

本模块是游客会话在 API DTO 边界的唯一脱敏点:
- 纯拷贝: 对每个策略行重建一份 dict, 把 ``code`` / ``name`` / ``symbol``
  替换为 ``******``, 并省略 ``open_gap`` (ROADMAP 原文: 游客仅见 涨跌幅+概念板块,
  CONTEXT D-04)。``change_pct`` / ``concept_board`` / ``hit_factors`` /
  ``cross_resonance`` 原样保留 (关联因子是策略标签, 非 PII)。
- 只读/无写路径: 本模块严禁 import 任何 engine/persistence/execution 模块,
  也没有任何写文件操作 — ``tests/test_guest_masking.py`` 的 AST 守卫锁定
  这条不变量 (GUEST-02: 掩码绝不触碰策略引擎或持久化结果)。
"""
from __future__ import annotations

from typing import Any

#: 脱敏后的股票标识: 6 个星号 (CONTEXT D-04 / UI-SPEC masked cell)。
MASKED_IDENTITY = "******"

#: 游客可见字段白名单: 涨跌幅 / 概念板块 / 关联因子 (策略标签, 非 PII) / 交叉共振标记。
_GUEST_VISIBLE = frozenset({"change_pct", "concept_board", "hit_factors", "cross_resonance"})

#: 盘前告警游客可见白名单 — 盘前文案/状态标注非 PII (MON-06)。
#: 身份 (symbol/name/code) 固定掩码, 竞价值 (open_gap/auction_*/preopen_metrics) 与
#: 探测快照 (probe) 绝不带出; 所有者通道 (飞书/Telegram) 不受本掩码约束。
_GUEST_ALERT_VISIBLE = frozenset({
    "message", "severity", "window", "provisional", "degraded", "rule_name",
    "conditions", "occurred_at", "rule_id", "source", "type",
})


def mask_guest_hub(hub: dict) -> dict:
    """返回一份脱敏后的 Hub 新 dict (输入 ``hub`` 不被修改, GUEST-02)。

    每个策略行的 ``code`` / ``name`` / ``symbol`` 固定为 ``******``,
    ``open_gap`` 键被省略; 其余游客可见字段原样保留。策略级 ``id`` /
    ``name`` / ``total`` 以及顶层 ``as_of`` / ``updated_at`` /
    ``resonance_count`` 不变。服务层/持久化结果永远不被触碰。

    Phase 23 (H7/PIT-7): 顶层 ``auction_columns`` 竞价列存在性声明是价格/量
    敏感元信息, 在返回前 ``pop`` 剥离; 行级 ``auction_*``/``open_gap`` 已由
    ``_GUEST_VISIBLE`` 白名单重建 masked_row 时天然丢弃 (不在白名单)。
    """
    strategies: list[dict[str, Any]] = []
    for strategy in hub.get("strategies", []):
        if not isinstance(strategy, dict):
            strategies.append(strategy)
            continue
        rows: list[dict[str, Any]] = []
        for row in strategy.get("rows", []):
            if not isinstance(row, dict):
                continue
            masked_row: dict[str, Any] = {
                "code": MASKED_IDENTITY,
                "name": MASKED_IDENTITY,
                "symbol": MASKED_IDENTITY,
            }
            masked_row.update({key: row[key] for key in _GUEST_VISIBLE if key in row})
            rows.append(masked_row)
        strategies.append({**strategy, "rows": rows})
    masked = {**hub, "strategies": strategies}
    masked.pop("auction_columns", None)
    return masked


def mask_guest_alert(event: dict) -> dict:
    """返回脱敏后的告警事件副本 (MON-06, 防御性 DTO 守卫; 输入 ``event`` 不被修改)。

    - ``symbol`` / ``name`` / ``code`` → ``MASKED_IDENTITY`` (******);
    - 剥离 ``open_gap`` / ``auction_*`` / ``preopen_metrics`` / ``probe`` (竞价值与
      探测快照绝不带出);
    - 保留 ``message`` / ``severity`` / ``window`` / ``provisional`` / ``degraded`` /
      ``rule_name`` / ``conditions`` / ``occurred_at`` / ``rule_id`` / ``source`` /
      ``type`` (盘前文案与状态标注非 PII, 白名单重建镜像 mask_guest_hub 语义)。

    调用点现状: 当前 /api/alerts 为登录面 (无 guest 路径) — 本函数是**防御性守卫**:
    未来任何游客可见 alerts 渲染必须经此函数 (GUEST-01/02 DTO 边界原则)。
    飞书/Telegram 为所有者通道, 不受掩码约束 (诚实边界, MONITOR-PREOPEN 原文)。
    """
    masked: dict[str, Any] = {key: event[key] for key in _GUEST_ALERT_VISIBLE if key in event}
    masked["symbol"] = MASKED_IDENTITY
    masked["name"] = MASKED_IDENTITY
    masked["code"] = MASKED_IDENTITY
    return masked
