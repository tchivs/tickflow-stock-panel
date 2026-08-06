"""竞价策略历史验证只读报告 (BT-03, POOL-03 零执行, D-01)。

只读 ``GET /api/research/auction/validation`` —— 9 个竞价/盘前策略在 enriched
历史窗口上的信号质量报告 (29-02 服务契约 ``AuctionValidationService.build_report``)。
本模块只暴露 GET 端点: 不写湖/缓存 (kline_auction / 选股结果湖 / 盘前结果湖 /
单 as_of 运行期缓存指针 / frozen panel)、不 import 执行族、不触发任何计算/同步/
回填; 任何 mutating 路由、写路径 pattern 或执行族 import 的引入都会触发
``tests/test_auction_validation.py`` 的 POOL-03 AST 守卫 (BT-06, 镜像
test_pool_hub.py E1/E3/E4/E5 与 test_auction_history.py 单文件变体)。

- 诚实数据门 (D-02): 空湖/enriched 空 → 200 ``data_gate:"empty"`` dict
  (含 empty_reason/coverage/window/probe), 绝不 404/500/0 填; probe 判定由服务层
  probe_resolver 解析一次仅透传 (D-03), 不参与历史闸门。
- 研究报告区间不受回测 186 天 guard 限制 (D-06): 本报告是单面板向量化扫描,
  覆盖由 enriched 缓存边界决定 (窗口回夹 + requested/effective 双字段回显)。
- 无 guest 掩码: 本端点位于 main.py 全量 auth 之后, 不读 ``reviewer_principal``,
  不动 guest 白名单。
"""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, HTTPException, Query, Request

from app.services.auction_validation import AuctionValidationService

router = APIRouter(prefix="/api/research", tags=["research"])


def _bad_request(error: Exception) -> HTTPException:
    return HTTPException(status_code=400, detail={"code": "RESEARCH_VALIDATION", "message": str(error)})


def _split_csv(raw: str | None) -> list[str] | None:
    """逗号分隔参数解析: ``None`` → ``None`` (服务层缺省); 空串 → ``[]``
    (显式空列表语义, 镜像选股服务); 否则按逗号拆分去空白。"""
    if raw is None:
        return None
    if not raw.strip():
        return []
    return [part.strip() for part in raw.split(",") if part.strip()]


@router.get("/auction/validation")
def auction_validation(
    request: Request,
    strategy_ids: str | None = Query(None, description="逗号分隔策略 id 列表; 缺省 = 9 个竞价族"),
    start: date | None = Query(None, description="报告起始日 (含); 缺省 = end − 120 自然日"),
    end: date | None = Query(None, description="报告结束日 (含); 缺省 = enriched 最新交易日"),
    symbols: str | None = Query(None, description="逗号分隔标的列表; 缺省 = 全市场"),
) -> dict:
    """竞价策略历史验证只读报告 (BT-01/BT-03, T-29-03-01 参数防线)。

    - ``start``/``end`` 为 date 类型 → 非法格式 FastAPI 422 (镜像 research.py
      Query date 行为); 逗号分隔参数白名单解析 (空串 → 空列表)。
    - ``start > end`` → 400 ``RESEARCH_VALIDATION`` (复制 research.py:86-87 逐字)。
    - 空湖/enriched 空 → 200 诚实 dict (data_gate/empty_reason/coverage), 绝不
      404/500/0 填 (D-02); 未知 strategy id → 服务层 skipped_ids 记录 (200, 不 500)。
    - probe 由服务层 probe_resolver 解析一次仅透传 (D-03), 不参与历史闸门。
    """
    if start is not None and end is not None and start > end:
        raise _bad_request(ValueError("start must not be after end"))

    repo = request.app.state.repo
    engine = request.app.state.strategy_engine
    svc = AuctionValidationService(repo, engine)
    return svc.build_report(
        start=start,
        end=end,
        strategy_ids=_split_csv(strategy_ids),
        symbols=_split_csv(symbols),
    )
