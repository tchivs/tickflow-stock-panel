"""盘前股池预览服务 (PM-01/02/03)。

复用与 EOD/回填完全相同的 ``ScreenerService.run_all_with_hits`` 单条代码路径,
as_of = 今日 T; 预览写入独立分区 ``premarket_results/date={T}/part.json``
(payload 含 ``window:"pre_open"`` / ``computed_at`` / ``provisional:true`` /
``degraded`` / probe 判定), **绝不调 strategy_cache.write_cache / 绝不写
screener_results** (EOD 语义不动; single-as_of 指针不污染)。

铁律 (镜像 pool_backfill.py:1-11):
- 绝不调 ``strategy_cache.write_cache`` / ``pool_snapshot.persist_point_snapshot``。
- 绝不 import 执行族模块 (broker/order/trade/execution/portfolio/position/account/
  transaction) 与 ``strategy_cache``。
- 绝不复制 kline.get_daily 的空库 live-fetch 兜底 (kline.py:159-181 反面教材);
  绝不写 kline_auction 湖 (tier-2 D6 不实现)。
- 绝不自算 open_gap (D2 单一实现 — 帧完整性由 compute_enriched_today 保证)。

本模块不 import 执行族模块与 strategy_cache — 保持平台一致性 (E1/E3 形)。
零新增运行时依赖。
"""
from __future__ import annotations

from datetime import date, datetime

from app.market_time import cn_today
from app.services import pool_snapshot
from app.services.auction_probe import resolve_auction_probe
from app.services.screener import ScreenerService


def build_premarket_preview(
    repo,
    engine=None,
    *,
    as_of: date | None = None,
    probe_resolver=None,
) -> dict:
    """构造盘前预览 payload (纯构造, 不写盘 — 落盘由调用方/job 决定)。

    - 今日帧来源: quote_service 盘前轮询已 flush 今日 live enriched 到 repo 内存
      缓存 (_load_enriched_for_date 优先级 1, screener.py:252-270); 无缓存 → 慢路径
      读 T 分区 → 盘前不存在 → 空帧 → ``available:false`` 诚实空态 (镜像
      _pool_eod_persist 966-975 skip 语义)。
    - probe 判定经 ``probe_resolver`` 注入点消费 (resolve_auction_probe 签名零改动);
      判定词汇 (status/source/probed_at/window/fallback/detail) 与
      /api/data/auction-probe 一致; 非 available → ``degraded:true`` (诚实降级,
      D4), 竞价列存在性 (auction_columns.real==[]) 由端点投影端声明。
    - **绝不**调 strategy_cache.write_cache / pool_snapshot.persist_point_snapshot
      (T-27-01-01); **绝不**自算 open_gap (D2 单一实现); **绝不**写 kline_auction
      湖 (tier-2 D6 不实现)。

    Args:
        repo: KlineRepository (含 store.data_dir + enriched 缓存读取面)。
        engine: 策略引擎 (None 容错只跑 PRESET)。
        as_of: 目标交易日 (默认今日北京时间); 传入 date 由调用方保证已定盘。
        probe_resolver: () -> AuctionProbeVerdict (测试注入点; 默认 resolve_auction_probe)。

    Returns:
        payload dict: 空 results → ``available:false``; 非空 → available:true +
        window/provisional/degraded/probe/strategy_version/results。
    """
    as_of = as_of or cn_today()
    probe_resolver = probe_resolver or resolve_auction_probe

    svc = ScreenerService(repo)
    results = svc.run_all_with_hits(as_of, engine=engine)

    probe = probe_resolver()
    verdict = probe.to_dict() if hasattr(probe, "to_dict") else probe

    if not results:
        return {
            "as_of": str(as_of),
            "available": False,
            "degraded": True,
            "window": "pre_open",
            "probe": verdict,
            "results": {},
        }

    return {
        "as_of": str(as_of),
        "available": True,
        "window": "pre_open",
        "computed_at": datetime.now().isoformat(timespec="seconds"),
        "provisional": True,
        "degraded": verdict.get("status") != "available",
        "probe": verdict,
        "strategy_version": (
            pool_snapshot.strategy_fingerprint(engine) if engine is not None else "unknown"
        ),
        "results": results,
    }
