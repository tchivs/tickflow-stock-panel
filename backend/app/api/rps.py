"""涨幅轮动矩阵 API。

供「概念分析 → 涨幅RPS轮动」对话框调用。返回最近 N 个交易日的概念涨幅
排名矩阵:每列(日期)各自把所有概念按当天涨幅从高到低排序。
"""
from __future__ import annotations

import re
from datetime import date as date_type
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.services import rps_rotation
from app.services.concept_rotation_analyzer import analyze_rotation_stream

router = APIRouter(prefix="/api/rps", tags=["rps"])

_AS_OF_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


@router.get("/rotation")
def get_rotation(
    request: Request,
    days: int = Query(12, ge=7, le=30, description="最近 N 个交易日(7-30)"),
    as_of: Optional[str] = Query(None, description="概念映射取 D 日分区 (YYYY-MM-DD); 缺省最新"),
) -> dict:
    """概念涨幅轮动矩阵。

    Returns:
        dates: 日期字符串列表(最新在最前)
        columns: {日期: [[概念名, 涨幅小数], ...]} 每列各自降序
        concept_count: 去重概念总数

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
    return rps_rotation.build_rps_rotation(request.app.state.repo, days, as_of=as_of)


class AnalyzeRequest(BaseModel):
    """AI 概念轮动分析请求。"""
    days: int = 12   # 分析最近 N 个交易日
    focus: str = ""  # 用户追加的关注点


@router.post("/rotation-analyze")
async def analyze_rotation(request: Request, req: AnalyzeRequest):
    """AI 概念轮动分析 — NDJSON 流式返回。

    装配轮动矩阵信号 + 大盘背景 → 分析提示词 → 流式调用 LLM →
    逐 chunk 以 NDJSON 推给前端(每行一个 JSON)。

    协议:
      {"type":"meta","days","summary"}
      {"type":"delta","content":"..."}
      {"type":"error","message":"..."}
      {"type":"done"}
    """
    repo = request.app.state.repo
    quote_service = getattr(request.app.state, "quote_service", None)
    depth_service = getattr(request.app.state, "depth_service", None)
    days = max(7, min(30, req.days))

    async def stream_gen():
        async for chunk in analyze_rotation_stream(
            repo, days, req.focus, quote_service, depth_service,
        ):
            yield chunk + "\n"

    return StreamingResponse(
        stream_gen(),
        media_type="application/x-ndjson",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
