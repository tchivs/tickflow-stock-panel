"""竞价策略历史验证只读报告 (BT-03/BT-04/BT-05, POOL-03 零执行, D-01)。

把 9 个竞价族策略在 enriched 历史窗口上的信号质量端到端装配为只读报告:
窗口解析/回夹回显 → warmup 面板装载 (get_enriched_range 快路径) →
attach_auction_columns_range 注入 (29-01 契约) → 策略枚举 + 互斥 branch 标注 (BT-05) →
候选掩码镜像 → 前瞻统计 (BT-04) → per_date → 报告 dict。端点 (29-03) 消费
``build_report``。

铁律 (镜像 premarket_pool.py:1-11 / auction_history.py 只读契约, POOL-03):
- 只读: 零写 5 个湖/缓存 (kline_auction / 选股结果湖 / 盘前结果湖 /
  单 as_of 运行期缓存指针 / frozen panel); 绝不创建/删除/覆盖任何文件。
- 零执行: 不 import 执行族模块 (broker/order/execution/trade/portfolio/position/
  account/transaction); 不 import 竞价同步/快照/回填/预览/选股触发面模块; 不触发
  任何策略批量执行/计算触发面。唯一执行面 = 策略定义 filter_fn (与选股服务既有信任面
  一致, 异常 fail-closed 全 False, 绝不冒泡 500)。
- 候选掩码语义镜像 backtest/strategy.py:522-570 (_build_candidate_filter_mask 的
  filter_fn 路径): 只读镜像 + docstring 锚点, 绝不 import app.backtest 模块。
- 本报告区间不受回测 186 天 guard 限制 (D-06): 回测 guard 保护组合回测/因子评估
  内存 (api/backtest.py:29-32, 默认关闭 config.py:103); 本报告是单面板向量化扫描,
  覆盖由 enriched 缓存边界决定, 窗口回夹 + requested/effective 双字段回显。

只读数据锚点:
- repo._enriched_history_cache: 单 as_of 运行期缓存指针 (enriched 历史缓存),
  只读 min/max 与区间; 绝不写回该指针。
- repo.get_enriched_range: 区间装载快路径; 缓存不覆盖返回 None → 诚实空
  (enriched_unavailable), 不复用慢路径 fallback (RESEARCH §2.2.1 风险 3)。
- repo.store.data_dir / "kline_auction" / "date=*": 分区目录 glob (经
  attach_auction_columns_range 只读消费), 仅按 date= 前缀严格解析。
"""
from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import date, datetime, timedelta, timezone

import polars as pl

from app.services.auction_columns import attach_auction_columns_range
from app.services.auction_probe import resolve_auction_probe
from app.strategy.engine import StrategyEngine
from app.tickflow.repository import KlineRepository

logger = logging.getLogger(__name__)

# 竞价族 9 策略硬编码 id 集 (做"属竞价族"筛选; 策略定义一律从 engine 取, 不 import builtin 模块)
_AUCTION_FAMILY_IDS = frozenset({
    "auction_fast_grab", "auction_allround", "t1_flash", "auction_intraday_confirm",
    "auction_alpha", "golden_230", "auction_bullish", "auction_preopen_quant",
    "auction_early_star",
})

# 缺省窗口: end 缺省 = enriched 最新交易日; start 缺省 = end − 120 自然日 (与 auction_history days=120 对齐)
_DEFAULT_WINDOW_DAYS = 120
# warmup 前导余量 (≥5 交易日, RESEARCH §2.1.4)
_WARMUP_DAYS = 14

_FORWARD_METRICS = ("next_day_open_ret", "next_day_close_ret", "open_gap_outcome")


def _null_metric() -> dict:
    """无有效行的指标聚合 (诚实 null, 绝不 0 填)。"""
    return {"mean": None, "median": None, "win_rate": None, "n": 0}


def _aggregate_metric(s: pl.Series) -> dict:
    """单指标聚合: mean/median/win_rate(有效行>0 比例)/n; 无有效行 → 全 null。"""
    valid = s.drop_nulls()
    n = valid.len()
    if n == 0:
        return _null_metric()
    return {
        "mean": float(valid.mean()),
        "median": float(valid.median()),
        "win_rate": float((valid > 0).mean()),
        "n": int(n),
    }


def _build_candidate_mask(panel: pl.DataFrame, s, params: dict) -> pl.Series:
    """生成策略候选层 mask — 语义镜像 backtest/strategy.py:522-570
    (_build_candidate_filter_mask 的 filter_fn 路径), 只读镜像绝不 import app.backtest。

    - filter_fn None → 全 True (镜像 strategy.py 无候选层 → true_mask);
    - filter_fn 异常 / 返回 None → 全 False (fail-closed, 镜像 strategy.py:551-552,
      异常仅记日志, 报告不携带异常文本 — T-29-02-06);
    - 竞价列缺席 → 策略 filter 内部 pl.lit(False) 守卫 (与引擎短路双保险一致, engine.py:345-348)。
    """
    false_mask = pl.Series("_cand", [False] * len(panel), dtype=pl.Boolean)
    if s.filter_fn is None:
        return pl.Series("_cand", [True] * len(panel), dtype=pl.Boolean)
    try:
        expr = s.filter_fn(panel, params)
        if expr is None:
            return false_mask
        result = panel.select(expr.alias("_cand"))
        if result.is_empty():
            return false_mask
        return result["_cand"].fill_null(False).cast(pl.Boolean)
    except Exception as exc:  # noqa: BLE001 — fail-closed, 绝不冒泡 500 (T-29-02-06)
        sid = s.meta.get("id", "?") if isinstance(s.meta, dict) else "?"
        logger.warning("strategy %s filter_fn failed (fail-closed): %s", sid, exc)
        return false_mask


class AuctionValidationService:
    """只读竞价策略历史验证报告装配服务 (BT-03)。

    probe_resolver 注入点镜像 premarket_pool.py:50-51 (缺省 resolve_auction_probe);
    probe 判定仅透传报告, 不参与历史闸门 (D-03 / REV-01 — 历史闸门 = 分区存在性,
    由 attach_auction_columns_range 主闸门承担)。
    """

    def __init__(
        self,
        repo: KlineRepository,
        engine: StrategyEngine,
        probe_resolver: Callable | None = None,
    ) -> None:
        self._repo = repo
        self._engine = engine
        self._probe_resolver = probe_resolver or resolve_auction_probe

    # ── 报告装配 ──────────────────────────────────────────────

    def build_report(
        self,
        *,
        start: date | None = None,
        end: date | None = None,
        strategy_ids: list[str] | None = None,
        symbols: list[str] | None = None,
    ) -> dict:
        """装配只读竞价策略历史验证报告 (BT-03)。

        1. 窗口解析 (D-06): end 缺省 = enriched 缓存最新日; start 缺省 = end − 120 自然日;
           窗口回夹到缓存覆盖 [cache_min, cache_max]; 缓存空 → 回退扫
           kline_daily_enriched/date=* 目录取 min/max; 仍无 → enriched_unavailable;
           回夹后 start > end → no_dates_in_window。绝不套用回测 186 天 guard (D-06)。
        2. warmup 面板装载: warmup_start = max(start − 14 自然日, cache_min) (PLAN-CHECK W-1:
           近缓存边界的窗口不得因 warmup 低于 cache_min 而误报 enriched_unavailable);
           get_enriched_range 快路径, None/空 → enriched_unavailable。
        3. 注入 (29-01 契约): attach_auction_columns_range → verification_panel +
           enabled_dates; data_gate/empty_reason 按 enabled∩enriched 判定。
        4. 枚举 (D-07): 9 竞价族 id ∩ engine; 未知 id → skipped_ids (不 500);
           参数恒 META 默认 (确定性跨日可比)。
        5. branch (BT-05): 4 个 requires_auction_data 恒 real (enabled 子面板,
           湖空 n_dates==0 绝不落 derived); auction_alpha real|derived; 4 个 EOD 代理恒 eod。
        6. 候选掩码 (镜像不 import) → hits/per_date/coverage。
        7. 前瞻统计 (BT-04): 结果日 = 全局交易日历 next-date (next_map 从 enriched_dates
           构建, 绝不 per-symbol shift(-1)); 三公式; 结果日缺行 → n_missing_outcomes
           统计排除, 绝不 0 填/前向填充; 每指标独立 n。
        """
        probe = self._probe_resolver()
        probe_dict = probe.to_dict() if hasattr(probe, "to_dict") else probe

        cache_min, cache_max = self._enriched_coverage()
        if cache_min is None or cache_max is None:
            return self._empty_report("enriched_unavailable", probe_dict=probe_dict)

        # 窗口解析 + 回夹 (D-06): requested_* 保留原始请求, effective_* 回夹到缓存覆盖
        end = end or cache_max
        start = start or (end - timedelta(days=_DEFAULT_WINDOW_DAYS))
        requested_start, requested_end = start, end
        start = max(start, cache_min)
        end = min(end, cache_max)
        window = {
            "requested_start": requested_start.isoformat(),
            "requested_end": requested_end.isoformat(),
            "effective_start": start.isoformat(),
            "effective_end": end.isoformat(),
        }
        if start > end:
            return self._empty_report("no_dates_in_window", window=window, probe_dict=probe_dict)

        # warmup 面板装载 (W1: warmup_start 夹到 cache_min, 诚实降级而非误报空)
        warmup_start = max(start - timedelta(days=_WARMUP_DAYS), cache_min)
        panel = self._repo.get_enriched_range(warmup_start, end, symbols=symbols)
        if panel is None or panel.is_empty():
            return self._empty_report("enriched_unavailable", window=window, probe_dict=probe_dict)

        # 注入 (29-01 契约; 历史闸门 = 分区存在性, D-03)
        panel, enabled_dates = attach_auction_columns_range(panel, start, end, self._repo)
        verification_panel = panel.filter(pl.col("date") >= start)
        enriched_dates = verification_panel["date"].unique().sort().to_list()
        auction_enabled_dates = sorted(set(enabled_dates) & set(enriched_dates))

        if auction_enabled_dates:
            data_gate, empty_reason = "available", None
        elif enriched_dates:
            data_gate, empty_reason = "empty", "no_auction_partitions"
        else:
            data_gate, empty_reason = "empty", "no_dates_in_window"

        # 策略枚举 (D-07)
        ids, skipped_ids = self._resolve_strategy_ids(strategy_ids)
        strategies: list[dict] = []
        for sid in ids:
            try:
                s = self._engine.get(sid)
            except ValueError:
                skipped_ids.append(sid)
                continue
            strategies.append(
                self._evaluate_strategy(s, verification_panel, auction_enabled_dates, enriched_dates)
            )

        return {
            "data_gate": data_gate,
            "empty_reason": empty_reason,
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "window": window,
            "probe": probe_dict,
            "coverage": {
                "auction_enabled_dates": [d.isoformat() for d in auction_enabled_dates],
                "auction_enabled_count": len(auction_enabled_dates),
                "enriched_dates": [d.isoformat() for d in enriched_dates],
                "enriched_count": len(enriched_dates),
                "coverage_ratio": (
                    len(auction_enabled_dates) / len(enriched_dates) if enriched_dates else 0.0
                ),
            },
            "skipped_ids": skipped_ids,
            "strategies": strategies,
        }

    # ── 窗口 / 空态 ───────────────────────────────────────────

    def _enriched_coverage(self) -> tuple[date | None, date | None]:
        """enriched 缓存覆盖 [min, max]; 缓存空 → 回退扫 kline_daily_enriched/date=* 目录
        (解析失败跳过); 仍无 → (None, None) → enriched_unavailable。"""
        cache = self._repo._enriched_history_cache
        if cache is not None and not cache.is_empty() and "date" in cache.columns:
            return cache["date"].min(), cache["date"].max()

        base = self._repo.store.data_dir / "kline_daily_enriched"
        dates: list[date] = []
        if base.exists():
            for part in base.glob("date=*"):
                name = part.name
                if not name.startswith("date="):
                    continue
                try:
                    dates.append(date.fromisoformat(name[len("date="):]))
                except ValueError:
                    continue
        if not dates:
            return None, None
        return min(dates), max(dates)

    def _empty_report(self, reason: str, *, window=None, probe_dict=None) -> dict:
        """诚实空态 200 形 dict (绝不 404/500/0 填, 镜像 premarket_pool 空态)。"""
        return {
            "data_gate": "empty",
            "empty_reason": reason,
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "window": window,
            "probe": probe_dict,
            "coverage": {
                "auction_enabled_dates": [],
                "auction_enabled_count": 0,
                "enriched_dates": [],
                "enriched_count": 0,
                "coverage_ratio": 0.0,
            },
            "skipped_ids": [],
            "strategies": [],
        }

    # ── 枚举 ──────────────────────────────────────────────────

    def _resolve_strategy_ids(self, strategy_ids: list[str] | None) -> tuple[list[str], list[str]]:
        """解析待评估策略 id 列表 + skipped_ids。

        - None → 9 个竞价族 ∩ engine (引擎缺失的族 id 记 skipped, 不静默消失);
        - 显式 [] → 空列表 (strategies: [], 镜像选股服务空列表语义);
        - 非空列表 → 竞价族 ∩ engine ∩ 请求集; 请求集不含任何可解析竞价族策略
          (全未知/越界) → 回落默认竞价族范围 (BT-03: 未知 id 记 skipped_ids,
          已知竞价族仍正常报告, 绝不因坏 id 静默清空报告);
         请求但未报告的 id (未知 / 非族 / 引擎缺失) → skipped_ids。
        """
        family = sorted(_AUCTION_FAMILY_IDS)
        engine_ids = set(self._engine._strategies)
        if strategy_ids is None:
            ids = [sid for sid in family if sid in engine_ids]
            skipped = [sid for sid in family if sid not in engine_ids]
        elif not strategy_ids:
            ids, skipped = [], []
        else:
            requested = list(strategy_ids)
            ids = [sid for sid in family if sid in engine_ids and sid in requested]
            if not ids:
                ids = [sid for sid in family if sid in engine_ids]
            skipped = [sid for sid in requested if sid not in ids]
        return ids, skipped

    # ── 策略评估 ──────────────────────────────────────────────

    def _evaluate_strategy(
        self,
        s,
        verification_panel: pl.DataFrame,
        auction_enabled_dates: list[date],
        enriched_dates: list[date],
    ) -> dict:
        """单策略评估: branch 选择 (BT-05 互斥) → 候选掩码 → hits/per_date/coverage →
        前瞻统计 (BT-04) → 报告行。"""
        meta = s.meta
        sid = str(meta.get("id", ""))
        requires = bool(meta.get("requires_auction_data", False))
        # 参数恒 META 默认 (镜像 engine.py:227-231 归一化后的 {p["id"]: p["default"]})
        params = {p["id"]: p["default"] for p in meta.get("params", [])}

        # branch 互斥 (BT-05): 每策略一次报告只取一个 branch 的统计
        if requires:
            branch = "real"
            eval_panel = verification_panel.filter(pl.col("date").is_in(auction_enabled_dates))
        elif sid == "auction_alpha":
            branch = "real" if auction_enabled_dates else "derived"
            eval_panel = (
                verification_panel.filter(pl.col("date").is_in(auction_enabled_dates))
                if branch == "real"
                else verification_panel
            )
        else:
            branch = "eod"
            eval_panel = verification_panel

        if eval_panel.is_empty():
            # 诚实空: n_dates==0, 不调掩码 (real 策略湖空绝不落 derived, D-02)
            n_dates = 0
            n_hits = 0
            coverage = 0.0
            per_date: list[dict] = []
            n_missing = 0
            forward_stats = {m: _null_metric() for m in _FORWARD_METRICS}
        else:
            n_dates = len(eval_panel["date"].unique())
            mask = _build_candidate_mask(eval_panel, s, params)
            hits = eval_panel.filter(mask)
            n_hits = hits.height
            coverage = (len(hits["date"].unique()) / n_dates) if n_dates else 0.0
            per_date = self._build_per_date(eval_panel, hits)
            forward_stats, n_missing = self._forward_stats(hits, verification_panel, enriched_dates)

        return {
            "id": sid,
            "name": str(meta.get("name", sid)),
            "branch": branch,
            "requires_auction_data": requires,
            "minute_confirm": "not_applied",  # kline_minute 0 分区 + 报告不调分钟确认层 (RESEARCH §9)
            "params": params,
            "n_dates": n_dates,
            "n_hits": n_hits,
            "coverage": coverage,
            "n_missing_outcomes": n_missing,
            "forward_stats": forward_stats,
            "per_date": per_date,
        }

    def _build_per_date(self, eval_panel: pl.DataFrame, hits: pl.DataFrame) -> list[dict]:
        """per_date: 评估面板全日期 (n_screened = 该日面板行数) 左联命中计数 (n_hits,
        缺命中的评估日 0 填 — 仅此处允许 0, 是"该日无命中"的真实计数而非伪造)。"""
        per = (
            eval_panel.group_by("date").len().rename({"len": "n_screened"})
            .join(hits.group_by("date").len().rename({"len": "n_hits"}), on="date", how="left")
            .with_columns(pl.col("n_hits").fill_null(0).cast(pl.Int64))
            .sort("date")
        )
        return [
            {
                "date": row["date"].isoformat(),
                "n_screened": int(row["n_screened"]),
                "n_hits": int(row["n_hits"]),
            }
            for row in per.iter_rows(named=True)
        ]

    # ── 前瞻统计 (BT-04) ──────────────────────────────────────

    def _forward_stats(
        self,
        hits: pl.DataFrame,
        verification_panel: pl.DataFrame,
        enriched_dates: list[date],
    ) -> tuple[dict[str, dict], int]:
        """前瞻统计 (BT-04 口径锁死):

        - 结果日 = 全局交易日历 next-date (next_map 从 enriched_dates 全局日期排序构建,
          绝不 per-symbol shift(-1) — 停牌标的行内 shift 会错配到 T+2);
        - 三公式: next_day_open_ret = open_{T+1}/open_T − 1 (open_T>0);
          next_day_close_ret = close_{T+1}/open_T − 1 (open_T>0);
          open_gap_outcome = open_{T+1}/close_T − 1 (close_T 非空且 >0, 否则单点剔除);
        - 结果日缺行 (停牌/退市) → n_missing_outcomes, 统计排除, 绝不 0 填/前向填充;
          每指标独立 n; 无有效行 → mean/median/win_rate 全 null。
        """
        if hits.is_empty():
            return {m: _null_metric() for m in _FORWARD_METRICS}, 0

        dates = list(enriched_dates)
        calendar = pl.DataFrame({"date": dates, "outcome_date": dates[1:] + [None]})
        hits = hits.join(calendar, on="date", how="left")

        outcomes = verification_panel.select(["symbol", "date", "open", "close"]).rename(
            {"date": "outcome_date", "open": "next_open", "close": "next_close"}
        )
        hits = hits.join(outcomes, on=["symbol", "outcome_date"], how="left")

        n_missing = int(hits.filter(pl.col("next_open").is_null()).height)

        hits = hits.with_columns(
            [
                pl.when(
                    pl.col("open").is_not_null() & (pl.col("open") > 0) & pl.col("next_open").is_not_null()
                )
                .then(pl.col("next_open") / pl.col("open") - 1.0)
                .otherwise(None)
                .alias("next_day_open_ret"),
                pl.when(
                    pl.col("open").is_not_null() & (pl.col("open") > 0) & pl.col("next_close").is_not_null()
                )
                .then(pl.col("next_close") / pl.col("open") - 1.0)
                .otherwise(None)
                .alias("next_day_close_ret"),
                pl.when(
                    pl.col("close").is_not_null() & (pl.col("close") > 0) & pl.col("next_open").is_not_null()
                )
                .then(pl.col("next_open") / pl.col("close") - 1.0)
                .otherwise(None)
                .alias("open_gap_outcome"),
            ]
        )
        return {m: _aggregate_metric(hits[m]) for m in _FORWARD_METRICS}, n_missing
