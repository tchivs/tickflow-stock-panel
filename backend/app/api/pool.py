"""股池 Hub API — 只读 ``GET /api/pool/*`` (POOL-03: 零执行权限)。

该模块只暴露 GET 端点: 不写库、不调 broker/order、不改变任何状态、不触发任何
计算或持久化。任何 mutating 路由或计算触发的引入都会触发 ``tests/test_pool_hub.py``
的 POOL-03 AST 守卫 (T-18-01, E4/E5)。
"""
from __future__ import annotations

import re
from datetime import date as date_type
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Request

from app.api.screener import _strategy_display_name
from app.services.pool_hub import build_pool_hub, build_pool_hub_snapshot
from app.services.pool_snapshot import list_snapshot_dates
from app.services.guest_masking import mask_guest_hub

router = APIRouter(prefix="/api/pool", tags=["pool"])

_AS_OF_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


@router.get("/hub")
def get_pool_hub(
    request: Request,
    as_of: Optional[str] = Query(None),
    concept: Optional[str] = Query(None),
):
    """返回单一 as_of 的股池 Hub (卡片计数 + 五列明细 + 交叉共振)。

    - ``as_of``: 期望数据日期; 与缓存不一致时仍回显缓存日期 (单一数据源)。
    - ``concept``: 概念筛选 (大小写不敏感子串), 只收窄 rows, total 保持权威全量。
    - 策略显示名服务端解析 (PRESET → 引擎 META → sid 兜底), 绝不来自客户端。
    """
    repo = request.app.state.repo
    data_dir = repo.store.data_dir
    engine = getattr(request.app.state, "strategy_engine", None)

    def name_for(sid: str) -> str:
        return _strategy_display_name(engine, sid)

    hub = build_pool_hub(data_dir, as_of=as_of, concept=concept, name_for=name_for)

    # 服务端声明展示模式 (GUEST-01, CONTEXT D-03): 已解析的会话 principal = VIP,
    # 否则 guest。模式绝不由客户端输入或行值推导 (T-19-02)。
    is_vip = getattr(request.state, "reviewer_principal", None) is not None
    hub["mode"] = "vip" if is_vip else "guest"
    if not is_vip:
        hub = mask_guest_hub(hub)
    return hub


@router.get("/dates")
def get_pool_dates(request: Request):
    """列出含冻结式点快照的可用日期 (ISO desc)。

    source of truth = ``screener_results/date=*`` 分区 glob (含 part.json 者)。
    GET-only 零写零执行 (POOL-05)。
    """
    data_dir = request.app.state.repo.store.data_dir
    dates = list_snapshot_dates(data_dir)
    return {"dates": dates, "count": len(dates), "latest": dates[0] if dates else None}


@router.get("/history")
def get_pool_history(
    request: Request,
    as_of: Optional[str] = Query(None),
    concept: Optional[str] = Query(None),
):
    """按 ``as_of`` 独立只读取池 (POOL-05) — 与 /hub 同形状, 快照缺失诚实空态。

    - ``as_of`` 严格校验 (``^\\d{4}-\\d{2}-\\d{2}$`` + ``date.fromisoformat``,
      防路径穿越 T-22-01): 缺失 → 200 空态; 非法 → 400。
    - 快照缺失 → ``available: False`` 空态 (200, 非 404); 快照存在 → 与 hub
      同形状投影 (``total`` 权威), ``updated_at`` = 快照 ``computed_at``。
    - ``concept`` 子串筛选沿用 hub 语义; ``mode`` + 游客脱敏与 /hub 一致。
    """
    data_dir = request.app.state.repo.store.data_dir
    engine = getattr(request.app.state, "strategy_engine", None)

    def name_for(sid: str) -> str:
        return _strategy_display_name(engine, sid)

    # as_of 严格双重校验后才允许拼路径 (绝不带非法输入进文件系统)
    if as_of is not None:
        if not _AS_OF_RE.fullmatch(as_of):
            raise HTTPException(status_code=400, detail="invalid as_of")
        try:
            date_type.fromisoformat(as_of)
        except ValueError:
            raise HTTPException(status_code=400, detail="invalid as_of")

    hub = build_pool_hub_snapshot(data_dir, as_of, concept=concept, name_for=name_for)

    is_vip = getattr(request.state, "reviewer_principal", None) is not None
    hub["mode"] = "vip" if is_vip else "guest"
    if not is_vip:
        hub = mask_guest_hub(hub)
    return hub
