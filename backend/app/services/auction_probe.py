"""竞价数据探测 (DATA-03)。

服务端权威判定平台是否拥有真实的 9:15–9:25 集合竞价匹配数据。
诚实规则 (T-16-01): 只有被观测到的 [09:15:00, 09:25:59] 内时间戳才能产生
``available``; 09:30 起的连续竞价 bar 永远不会被标记为集合竞价数据。
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timezone
from enum import StrEnum
from typing import Any, Callable

import polars as pl

# 探测使用的样本标的 —— 只用于探测数据源是否返回窗口内行, 不参与任何策略。
PROBE_SYMBOL = "000001"

# 集合竞价匹配数据窗口: 09:15:00 – 09:25:59
WINDOW_START = time(9, 15, 0)
WINDOW_END = time(9, 25, 59)
# 用分钟粒度做边界判定 (与 [09:15:00, 09:25:59] 语义一致)
_WINDOW_START_MIN = 9 * 60 + 15
_WINDOW_END_MIN = 9 * 60 + 25

NOT_CONFIGURED_DETAIL = "尚未配置竞价数据源；配置后平台将自动探测 9:15–9:25 集合竞价匹配数据的可用性。"
FAIL_CLOSED_DETAIL = "平台未检测到可用的集合竞价匹配数据，已退化到派生开盘涨幅因子（open / prev_close − 1）。09:30 起的连续竞价 bar 不会被标记为集合竞价数据。"

# error 详情只透出截断的异常消息 (T-16-05 信息泄露 mitigation)
_ERROR_DETAIL_MAX = 200


class AuctionProbeStatus(StrEnum):
    not_configured = "not_configured"
    available = "available"
    fail_closed = "fail_closed"
    error = "error"


@dataclass(frozen=True)
class AuctionProbeVerdict:
    """服务端权威的竞价数据探测判定。前端只渲染该判定, 不做客户端合成。"""

    status: AuctionProbeStatus
    source: str | None
    probed_at: str | None
    detail: str
    window: str = "09:15-09:25"
    fallback: str = "open_gap"

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": str(self.status),
            "source": self.source,
            "probed_at": self.probed_at,
            "window": self.window,
            "fallback": self.fallback,
            "detail": self.detail,
        }


# source_resolver: () -> list[provider]; fetcher: (provider, symbols, trade_date) -> pl.DataFrame
SourceResolver = Callable[[], list[Any]]
Fetcher = Callable[[Any, list[str], date], pl.DataFrame]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _last_trade_date() -> date:
    """探测目标交易日: 优先本地日K最新分区日期, 否则今天。"""
    try:
        from app.config import settings

        base = settings.data_dir / "kline_daily"
        if base.is_dir():
            dates = [d.name[5:] for d in base.iterdir() if d.is_dir() and d.name.startswith("date=")]
            if dates:
                return date.fromisoformat(max(dates))
    except Exception:  # noqa: BLE001
        pass
    return date.today()


def _default_sources() -> list[Any]:
    """枚举竞价数据候选源: (a) 配置了 auction 数据集的自定义源; (b) 声明 auction 能力的内置源。"""
    from app.data_providers import chain as provider_chain
    from app.data_providers import custom as custom_sources

    candidates: list[Any] = []
    seen: set[str] = set()

    for name in sorted(custom_sources.names()):
        if custom_sources.provider_has_dataset(name, "auction"):
            try:
                candidates.append(custom_sources.get_provider(name))
                seen.add(name)
            except Exception:  # noqa: BLE001
                continue

    known: set[str] = set()
    for ds_names in provider_chain._BUILTIN_CHAIN.values():  # noqa: SLF001
        known.update(ds_names)
    for name in sorted(known - seen):
        try:
            provider = provider_chain._get_provider(name)  # noqa: SLF001
        except Exception:  # noqa: BLE001
            continue
        if getattr(getattr(provider, "capabilities", None), "auction", False):
            candidates.append(provider)
            seen.add(name)

    return candidates


def _default_fetcher(provider: Any, symbols: list[str], trade_date: date) -> pl.DataFrame:
    return provider.get_auction(symbols, trade_date)

def _has_in_window_rows(rows: pl.DataFrame) -> bool:
    """严格按观测时间戳分类 (T-16-01)。

    供应商的标签 / 能力声明永远不能授予可用性 —— 只有落在 [09:15:00, 09:25:59]
    窗口内的行可以。空输入、缺列、解析失败一律按未命中处理 (fail-closed)。
    """
    if rows is None or rows.is_empty() or "datetime" not in rows.columns:
        return False
    try:
        dt = pl.col("datetime").cast(pl.Datetime("us"), strict=False)
        minutes = dt.dt.hour().cast(pl.Int32) * 60 + dt.dt.minute().cast(pl.Int32)
        in_window = rows.filter(
            (minutes >= _WINDOW_START_MIN) & (minutes <= _WINDOW_END_MIN)
        )
    except Exception:  # noqa: BLE001
        return False
    return not in_window.is_empty()


def resolve_auction_probe(
    *,
    source_resolver: SourceResolver | None = None,
    fetcher: Fetcher | None = None,
) -> AuctionProbeVerdict:
    """计算竞价数据探测判定。

    两个注入点都默认指向生产实现, 测试可用假 provider / 假 fetcher 强制每个状态。
    """
    resolver = source_resolver or _default_sources
    fetch = fetcher or _default_fetcher

    candidates = resolver()
    if not candidates:
        return AuctionProbeVerdict(
            status=AuctionProbeStatus.not_configured,
            source=None,
            probed_at=None,
            detail=NOT_CONFIGURED_DETAIL,
        )

    provider = candidates[0]
    source_name = str(getattr(provider, "name", "unknown"))
    try:
        rows = fetch(provider, [PROBE_SYMBOL], _last_trade_date())
    except Exception as exc:  # noqa: BLE001
        return AuctionProbeVerdict(
            status=AuctionProbeStatus.error,
            source=source_name,
            probed_at=_now_iso(),
            detail=str(exc)[:_ERROR_DETAIL_MAX],
        )

    if _has_in_window_rows(rows):
        return AuctionProbeVerdict(
            status=AuctionProbeStatus.available,
            source=source_name,
            probed_at=_now_iso(),
            detail="已检测到 9:15–9:25 集合竞价匹配数据。",
        )

    return AuctionProbeVerdict(
        status=AuctionProbeStatus.fail_closed,
        source=source_name,
        probed_at=_now_iso(),
        detail=FAIL_CLOSED_DETAIL,
    )
