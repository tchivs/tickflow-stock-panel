"""涨幅轮动矩阵 API。

供「概念分析 → 涨幅RPS轮动」对话框调用。返回最近 N 个交易日的概念涨幅
排名矩阵:每列(日期)各自把所有概念按当天涨幅从高到低排序。
"""
from __future__ import annotations

import re
from datetime import date as date_type
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel

from app.services import rps_rotation
from app.services.concept_rotation_analyzer import analyze_rotation_stream

router = APIRouter(prefix="/api/rps", tags=["rps"])

_AS_OF_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


@router.get("/rotation")
def get_rotation(
    request: Request,
    days: int = Query(12, ge=7, le=30, description="最近 N 个交易日(7-30)"),
    as_of: Optional[str] = Query(None, description="维度映射取 D 日分区 (YYYY-MM-DD); 缺省最新"),
    kind: str = Query("concept", pattern="concept|industry", description="维度: concept 概念 / industry 行业"),
    level: int | None = Query(None, ge=1, le=3, description="行业层级(仅 kind=industry): 1/2/3 级"),
) -> dict:
    """维度涨幅轮动矩阵(概念或行业)。

    Returns:
        dates: 日期字符串列表(最新在最前)
        columns: {日期: [[成员名, 涨幅小数], ...]} 每列各自降序
        concept_count: 去重维度成员总数

    ``as_of`` 严格双重校验 (``^\\d{4}-\\d{2}-\\d{2}$`` + ``date.fromisoformat``,
    防路径穿越 T-28-03-01, 镜像 api/pool.py): 非法 → 400。
    """
    if as_of is not None:
        if not _AS_OF_RE.fullmatch(as_of):
            raise HTTPException(status_code=400, detail="invalid as_of")
        try:
            date_type.fromisoformat(as_of)
        except ValueError:
            raise HTTPException(status_code=400, detail="invalid as_of")
    return rps_rotation.build_rps_rotation(
        request.app.state.repo, days, as_of=as_of, kind=kind, level=level
    )


class AnalyzeRequest(BaseModel):
    """AI 维度轮动分析请求(概念或行业)。"""
    days: int = 12   # 分析最近 N 个交易日
    focus: str = ""  # 用户追加的关注点
    kind: str = "concept"  # "concept" 概念 / "industry" 行业
    level: int | None = None  # 行业层级(1/2/3), 仅 kind=industry 有效


