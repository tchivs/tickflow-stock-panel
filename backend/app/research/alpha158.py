"""Alpha158 公式语料 — 移植自 microsoft/qlib (MIT License).

来源: qlib/contrib/data/loader.py ``Alpha158DL.get_feature_config()`` 默认配置
(qlib 仓库 main 分支)。默认 158 条 = kbar 9 + price 4 + volume 5 + 28 个
rolling 算子 x 5 个窗口; 本语料移植其中 133 条, 表达式语法从 qlib
(``Ref($close, 5)/$close``) 转写为本项目受控因子 DSL (``ref(close, 5)/close``)。

有意跳过的 5 类算子 (25 条, polars 表达式引擎无原生滚动算子, 需自定义核):
- BETA/RSQR/RESI: 滚动线性回归 (斜率 / R 平方 / 残差)
- RANK: 滚动窗口内当前值的分位 (qlib 默认配置自身也排除)
- IMAX/IMIN/IMXD: 滚动窗口极值下标 (Aroon 类)

转写适配 (语义等价, 已在模块测试中固化):
- ``$vwap``: 本项目无现成 vwap 字段, 用 ``amount/(volume*100+1e-12)`` 推导
  (amount 单位元, volume 单位手); 已对真实面板实证 99.98% 落在 [low, high]。
- ``Greater/Less`` (逐点二元): 转写为 DSL v3 的 ``max``/``min``。
- ``Mean($close>Ref($close,1), d)`` (上涨天占比): DSL 无比较算子, 用 sign
  分解 — CNTP = ``rolling_mean((sign(close-ref(close,1))+1)/2, d)``。
  平盘日按 0.5 计 (qlib 的 ``>`` 记 0), A 股平盘日极少, 影响可忽略。
- ``Log``: 转写为 ``log1p`` (qlib 公式本身也是 Log(x+1))。
- 所有滚动算子 ``min_samples=1``, 与既有 ``rolling_mean`` 约定一致;
  窗口头部的 null/NaN 由评估管线的非空过滤兜底。

导入器: ``scripts/import_alpha158.py`` (按 canonical expression 幂等)。
"""
from __future__ import annotations

from dataclasses import dataclass

# qlib Alpha158 默认 rolling 窗口
WINDOWS: tuple[int, ...] = (5, 10, 20, 30, 60)

# 分母护栏, 与 qlib 原式一致
_EPS: str = "1e-12"


@dataclass(frozen=True, slots=True)
class Alpha158Factor:
    """一条 Alpha158 公式的 DSL 转写。"""

    name: str
    expression: str
    description: str


def _kbar() -> list[Alpha158Factor]:
    return [
        Alpha158Factor("KMID", "(close-open)/open", "K 线实体: (收盘-开盘)/开盘"),
        Alpha158Factor("KLEN", "(high-low)/open", "K 线全幅: (最高-最低)/开盘"),
        Alpha158Factor("KMID2", "(close-open)/(high-low+1e-12)", "K 线实体占全幅比"),
        Alpha158Factor("KUP", "(high-max(open,close))/open", "上影线: (最高-max(开,收))/开盘"),
        Alpha158Factor("KUP2", "(high-max(open,close))/(high-low+1e-12)", "上影线占全幅比"),
        Alpha158Factor("KLOW", "(min(open,close)-low)/open", "下影线: (min(开,收)-最低)/开盘"),
        Alpha158Factor("KLOW2", "(min(open,close)-low)/(high-low+1e-12)", "下影线占全幅比"),
        Alpha158Factor("KSFT", "(2*close-high-low)/open", "收盘在全幅中的位移: (2x收-高-低)/开盘"),
        Alpha158Factor("KSFT2", "(2*close-high-low)/(high-low+1e-12)", "收盘位移占全幅比"),
    ]


def _price() -> list[Alpha158Factor]:
    # qlib price 配置: windows=[0], features=[OPEN, HIGH, LOW, VWAP] → 均 / close
    return [
        Alpha158Factor("OPEN0", "open/close", "开盘价相对收盘"),
        Alpha158Factor("HIGH0", "high/close", "最高价相对收盘"),
        Alpha158Factor("LOW0", "low/close", "最低价相对收盘"),
        Alpha158Factor("VWAP0", f"amount/(volume*100+{_EPS})/close", "成交均价相对收盘 (amount 元 / volume 手)"),
    ]


def _volume_features() -> list[Alpha158Factor]:
    factors = [Alpha158Factor("VOLUME0", f"volume/(volume+{_EPS})", "当日量比基准 (恒约 1, 保留与 qlib 一致)")]
    factors += [
        Alpha158Factor(f"VOLUME{d}", f"ref(volume, {d})/(volume+{_EPS})", f"{d} 日前成交量相对当日")
        for d in range(1, 5)
    ]
    return factors


def _rolling() -> list[Alpha158Factor]:
    factors: list[Alpha158Factor] = []
    for d in WINDOWS:
        factors += [
            Alpha158Factor(f"ROC{d}", f"ref(close, {d})/close", f"{d} 日价格变动率 ROC"),
            Alpha158Factor(f"MA{d}", f"rolling_mean(close, {d})/close", f"{d} 日均线相对收盘 (BIAS 类)"),
            Alpha158Factor(f"STD{d}", f"rolling_std(close, {d})/close", f"{d} 日收盘价标准差相对收盘 (波动率)"),
            Alpha158Factor(f"MAX{d}", f"rolling_max(high, {d})/close", f"{d} 日最高价相对收盘"),
            Alpha158Factor(f"MIN{d}", f"rolling_min(low, {d})/close", f"{d} 日最低价相对收盘"),
            Alpha158Factor(f"QTLU{d}", f"rolling_quantile(close, {d}, 0.8)/close", f"{d} 日收盘 80% 分位相对收盘"),
            Alpha158Factor(f"QTLD{d}", f"rolling_quantile(close, {d}, 0.2)/close", f"{d} 日收盘 20% 分位相对收盘"),
            Alpha158Factor(
                f"RSV{d}",
                f"(close-rolling_min(low, {d}))/(rolling_max(high, {d})-rolling_min(low, {d})+{_EPS})",
                f"{d} 日随机值 RSV (价格在区间内位置)",
            ),
            Alpha158Factor(f"CORR{d}", f"rolling_corr(close, log1p(volume), {d})", f"{d} 日收盘价与对数成交量相关性"),
            Alpha158Factor(
                f"CORD{d}",
                f"rolling_corr(close/ref(close, 1), log1p(volume/ref(volume, 1)), {d})",
                f"{d} 日价变动率与量变动率相关性",
            ),
            Alpha158Factor(
                f"CNTP{d}",
                f"rolling_mean((sign(close-ref(close, 1))+1)/2, {d})",
                f"{d} 日上涨天占比 (平盘记 0.5)",
            ),
            Alpha158Factor(
                f"CNTN{d}",
                f"rolling_mean((1-sign(close-ref(close, 1)))/2, {d})",
                f"{d} 日下跌天占比 (平盘记 0.5)",
            ),
            Alpha158Factor(f"CNTD{d}", f"rolling_mean(sign(close-ref(close, 1)), {d})", f"{d} 日涨跌天占比差"),
            Alpha158Factor(
                f"SUMP{d}",
                f"rolling_sum(max(close-ref(close, 1), 0), {d})/(rolling_sum(abs(close-ref(close, 1)), {d})+{_EPS})",
                f"{d} 日上涨分量占比 (RSI 类)",
            ),
            Alpha158Factor(
                f"SUMN{d}",
                f"rolling_sum(max(ref(close, 1)-close, 0), {d})/(rolling_sum(abs(close-ref(close, 1)), {d})+{_EPS})",
                f"{d} 日下跌分量占比 (= 1 - SUMP{d})",
            ),
            Alpha158Factor(
                f"SUMD{d}",
                f"(rolling_sum(max(close-ref(close, 1), 0), {d})-rolling_sum(max(ref(close, 1)-close, 0), {d}))"
                f"/(rolling_sum(abs(close-ref(close, 1)), {d})+{_EPS})",
                f"{d} 日涨跌分量差比 (SUMD = SUMP{d} - SUMN{d})",
            ),
            Alpha158Factor(f"VMA{d}", f"rolling_mean(volume, {d})/(volume+{_EPS})", f"{d} 日量均线相对当日量"),
            Alpha158Factor(f"VSTD{d}", f"rolling_std(volume, {d})/(volume+{_EPS})", f"{d} 日量标准差相对当日量"),
            Alpha158Factor(
                f"WVMA{d}",
                f"rolling_std(abs(close/ref(close, 1)-1)*volume, {d})"
                f"/(rolling_mean(abs(close/ref(close, 1)-1)*volume, {d})+{_EPS})",
                f"{d} 日量加权价格波动比",
            ),
            Alpha158Factor(
                f"VSUMP{d}",
                f"rolling_sum(max(volume-ref(volume, 1), 0), {d})/(rolling_sum(abs(volume-ref(volume, 1)), {d})+{_EPS})",
                f"{d} 日放量分量占比 (量 RSI 类)",
            ),
            Alpha158Factor(
                f"VSUMN{d}",
                f"rolling_sum(max(ref(volume, 1)-volume, 0), {d})/(rolling_sum(abs(volume-ref(volume, 1)), {d})+{_EPS})",
                f"{d} 日缩量分量占比 (= 1 - VSUMP{d})",
            ),
            Alpha158Factor(
                f"VSUMD{d}",
                f"(rolling_sum(max(volume-ref(volume, 1), 0), {d})-rolling_sum(max(ref(volume, 1)-volume, 0), {d}))"
                f"/(rolling_sum(abs(volume-ref(volume, 1)), {d})+{_EPS})",
                f"{d} 日放缩量分量差比",
            ),
        ]
    return factors


def build_alpha158() -> tuple[Alpha158Factor, ...]:
    """完整 Alpha158 移植树: kbar 9 + price 4 + volume 5 + 23 算子 x 5 窗口 = 133 条。"""
    factors = _kbar() + _price() + _volume_features() + _rolling()
    names = [f.name for f in factors]
    if len(names) != len(set(names)):
        duplicates = sorted({n for n in names if names.count(n) > 1})
        raise ValueError(f"alpha158 corpus has duplicate names: {duplicates}")
    return tuple(factors)


def provenance() -> dict[str, str]:
    """导入 registry 时写入的溯源字段。"""
    return {
        "source": "microsoft/qlib Alpha158DL",
        "url": "https://github.com/microsoft/qlib/blob/main/qlib/contrib/data/loader.py",
        "license": "MIT",
        "adapter": "athenaquant factor-dsl-v3 转写",
    }
