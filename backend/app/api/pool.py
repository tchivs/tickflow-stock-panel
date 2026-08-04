"""股池 Hub API — 只读 ``GET /api/pool/hub`` (POOL-03: 零执行权限)。

该模块只暴露一个 GET 端点: 不写库、不调 broker/order、不改变任何状态。
任何 mutating 路由的引入都会触发 ``tests/test_pool_hub.py`` 的 POOL-03 AST 守卫
(T-18-01)。
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Query, Request

from app.api.screener import _strategy_display_name
from app.services.pool_hub import build_pool_hub

router = APIRouter(prefix="/api/pool", tags=["pool"])


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

    return build_pool_hub(data_dir, as_of=as_of, concept=concept, name_for=name_for)
