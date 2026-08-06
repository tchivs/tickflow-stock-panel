"""竞价复盘只读聚合 API (REV-05, POOL-03 零执行权限)。

只读 ``GET /api/market-recap/auction`` —— 独立于 AI 复盘流的确定性竞价复盘面板
(与复盘流内嵌面板共用 ``build_auction_recap`` / ``render_auction_recap_markdown``
装配与渲染, 同源不漂移)。本模块只暴露 GET 端点: 不写湖/缓存/预览/报告、不触发
任何计算/同步/回填、不 import 执行族与单 as_of 运行期缓存指针; 空态 → 200
available:false 诚实空态 (绝不 404/500/0 填充); guest 会话 → 逐标的身份与竞价值
掩码 (聚合统计与状态标注保留)。任何 mutating 路由、写路径 pattern 或执行族
import 的引入都会触发 ``tests/test_auction_recap_guard.py`` 的 POOL-03 AST 守卫
(REV-05 验收 6)。本模块与 ``services/auction_recap.py`` 是守卫目标。

- ``as_of`` 严格双重校验 (镜像 api/pool.py:99-107 防路径穿越): 非 None 时正则
  fullmatch + ``date.fromisoformat`` 双检, 非法 → 400 ``invalid as_of``; 缺省 →
  ``ScreenerService.latest_date()`` (与复盘缺省口径一致), latest 无值 → 诚实空态。
- 诚实空态: 无任何 present 块 → 200 ``{available: False, data_completeness, blocks: {},
  reason}`` (绝不 404/500/0 填, 镜像 auction_history 空态契约)。
- guest 脱敏 (R12 锁定 DTO): 逐标的身份 (symbol/name/code → MASKED_IDENTITY) 与
  逐标的竞价值/open_gap 剥离 (Top N 行只留掩码身份 + 排名); 聚合统计 (家数/占比/
  兑现率/n_missing) 与状态标注 (provisional/degraded/data_completeness/note/source)
  保留; probe verdict 剥离 (镜像 mask_guest_alert 剥 probe 先例); guest 视图不含
  markdown 渲染文本 (掩码视图无渲染文本, 诚实)。
"""
from __future__ import annotations

import logging
import re
from datetime import date

from fastapi import APIRouter, HTTPException, Query, Request

from app.services.auction_recap import build_auction_recap, render_auction_recap_markdown
from app.services.guest_masking import MASKED_IDENTITY

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/market-recap", tags=["market-recap"])

# as_of 严格格式 (镜像 pool.py:24): 防非法输入进文件系统分区路径 (T-31-03-01)
_AS_OF_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

#: guest 视图竞价值键: 逐标的数值行一律剥离 (镜像 mask_guest_alert 剥 open_gap/
#: auction_* 语义; 聚合统计 non-PII 保留)
_SENSITIVE_VALUE_KEYS = ("auction_amount", "auction_volume", "open_gap", "auction_volume_ratio")

#: guest 视图身份键: 固定掩码 (MASKED_IDENTITY, R12)
_IDENTITY_KEYS = ("symbol", "name", "code")


def _masked_row(row: dict) -> dict:
    """逐标的行脱敏: 身份掩码 + 竞价值剥离, 其余 (排名/状态) 保留。"""
    masked: dict = {key: MASKED_IDENTITY for key in _IDENTITY_KEYS}
    for k, v in row.items():
        if k in _IDENTITY_KEYS or k in _SENSITIVE_VALUE_KEYS:
            continue
        masked[k] = v
    return masked


def _mask_block(blk: dict) -> dict:
    """单块脱敏: 深拷贝语义, 聚合统计与状态标注原样保留, probe 剥离。"""
    masked = {k: v for k, v in blk.items() if k != "probe"}
    for key in ("top_n", "rows"):
        rows = masked.get(key)
        if isinstance(rows, list):
            masked[key] = [_masked_row(r) for r in rows if isinstance(r, dict)]
    return masked


def _mask_guest_recap(panel: dict) -> dict:
    """面板 guest 视图 (R12 DTO 锁定): blocks 同构, per-symbol 数值行脱敏;
    聚合 (n_symbols/total_amount/分布/策略统计/n_missing) 与状态标注保留;
    probe/竞价值/markdown 绝不带出。"""
    masked_blocks: dict = {}
    for name, blk in (panel.get("blocks") or {}).items():
        if not isinstance(blk, dict):
            masked_blocks[name] = blk
            continue
        masked_blocks[name] = _mask_block(blk)
        # real_auction_activity 聚合金额/家数是聚合统计 (非 PII), 保留;
        # preopen_signal_quality 策略统计整表保留 (无 per-symbol 行)
    return {**panel, "blocks": masked_blocks}


@router.get("/auction")
def get_auction_recap(request: Request, as_of: str | None = Query(None)) -> dict:
    """确定性竞价复盘面板 (只读, REV-05 验收 1-5)。

    - as_of 严格双重校验 (regex fullmatch + fromisoformat) → 非法 400 invalid as_of
      (防路径穿越 T-31-03-01); 缺省 → ScreenerService.latest_date()。
    - 无任何 present 块 → 200 诚实空态 (available:false, 绝不 404/500/0 填)。
    - guest (无 reviewer_principal) → 掩码视图; vip → 明文 + markdown。
    """
    repo = request.app.state.repo
    engine = getattr(request.app.state, "strategy_engine", None)

    # as_of 严格双重校验后才允许拼路径 (镜像 pool.py:99-107, 绝不带非法输入进文件系统)
    if as_of is not None:
        if not _AS_OF_RE.fullmatch(as_of):
            raise HTTPException(status_code=400, detail="invalid as_of")
        try:
            date.fromisoformat(as_of)
        except ValueError:
            raise HTTPException(status_code=400, detail="invalid as_of")
        as_of_date = date.fromisoformat(as_of)
    else:
        # 缺省口径: 与复盘一致 (ScreenerService.latest_date); 无数据日 → 诚实空态
        from app.services.screener import ScreenerService

        latest = ScreenerService(repo).latest_date()
        if latest is None:
            return {
                "available": False,
                "as_of": None,
                "data_completeness": "no_auction_lake",
                "blocks": {},
                "reason": "当日无可用竞价复盘数据",
            }
        as_of_date = latest

    panel = build_auction_recap(repo, as_of_date, engine)

    present_blocks = {
        k: v for k, v in (panel.get("blocks") or {}).items()
        if isinstance(v, dict) and v.get("present")
    }
    if not present_blocks:
        return {
            "available": False,
            "as_of": as_of_date.isoformat(),
            "data_completeness": panel.get("data_completeness"),
            "blocks": {},
            "reason": "当日无可用竞价复盘数据",
        }

    is_vip = getattr(request.state, "reviewer_principal", None) is not None
    if not is_vip:
        return {**_mask_guest_recap(panel), "available": True}
    return {**panel, "available": True, "markdown": render_auction_recap_markdown(panel)}
