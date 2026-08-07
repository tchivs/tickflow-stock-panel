#!/usr/bin/env python3
"""DEP-02 部署日新端点 200-body 验证脚本 (deploy_verify_endpoints.py)。

把 RESEARCH 沙箱实测通过的 200-body 全流程 (login → validation/backtest/backfill
键形状断言 → backfill job 轮询至终态) 固化为可重复交付物。**只读 + 触发面受控**:
除 backfill POST (默认 fail-closed 远未来窗, 零上游消耗) 外全部 GET; 不写数据湖、
不写任何业务分区、不回显凭证。

用途 (Phase 44 DEP-02):
    1. 401 先验 3/3: 无 cookie 下 validation/backtest/backfill 三端点均 401 ——
       认证门失效即系统异常, 任一非 401 立即中止 exit 1, 绝不继续验 200-body。
    2. 真实登录: POST /api/auth/login {"password": <DEP_PASSWORD>} → 200
       {ok, authenticated} + tf_session HttpOnly cookie (cookiejar 保存, 不回显)。
       密码从环境变量 DEP_PASSWORD 注入, 单次尝试 (auth.py 限流 5 次/300s,
       401 即停, 绝不重试循环)。
    3. validation: GET /api/research/auction/validation → 顶层 8 键 + coverage
       .symbols 5 键 + coverage.minute_stats 11 键 (caliber) + window
       requested/effective + strategies list。
    4. backtest: GET /api/research/backtest → {runs, count} + count == len(runs)
       + 每条 run 8 键 (run_id ^[0-9a-f]{12}$); 首条详情 GET
       /api/research/backtest/{run_id} → {manifest, stats, sample} (stats 4 键 /
       sample ≤ 20 行 / manifest 含 run_id/fingerprint/strategies/window)。
    5. backfill: POST /api/kline/auction/backfill, 默认 body 为远未来窗
       {"symbols":["600519.SH"],"start":"2099-01-01","end":"2099-01-02"} →
       no_scope/source_unavailable fail-closed, 零上游消耗; 断言 {status, job_id}
       (job_id ^[0-9a-f]{10}$); 轮询 /api/pipeline/jobs/{job_id} 至终态
       {succeeded, failed} → result W-5 9 键 (requested/backfilled_symbols/rows/
       dates/failed/failed_symbols/origin/rpm + fail-closed reason)。
    6. JSON 台账 (--out, 原子落盘) + stdout 摘要。

**全量回填绝不由本脚本触发** (36-02 配额纪律): 默认 fail-closed 体已双明示
(docstring + 台账字段); 真实小范围回填 = 运营显式 `--symbols --start --end`
三参数齐全才生效 (symbols 每项 ^\\d{6}\\.(SH|SZ|BJ)$, 上限 6000); 缺任一参数
或窗口不完整 → warning 且仍走默认 fail-closed 体。全量 5537 symbol 回填 =
运营手动 `python3 backend/scripts/auction_backfill.py` CLI, 脚本拒绝触发。

退出码:
    0  全部断言通过 (401 先验 3/3 + login 200 + 3 端点键形状 + job 终态 W-5)
    1  键形状/值集断言失败 (认证门失效 / DTO 契约漂移; 台账含差异详情)
    2  认证失败 (login 401, 单次尝试后立即停; 或任一端点意外 401)
    3  运行错误 (参数错误 / 网络 refused/timeout / 429 重试后仍失败 / job 超时)

部署日运行说明 (44-01 连通性预检 green 且 3018 已按 44-03 --apply 重建后执行):

    # 前置: 镜像 md5 4/4 == HEAD, 3018 /health 200
    DEP_PASSWORD=$(sed -n 's/^AUTH_PASSWORD=//p' .env) \
      python3 backend/scripts/deploy_verify_endpoints.py \
        --base-url http://127.0.0.1:3018 --out deploy-day-verify.json
    echo "exit=$?"   # 0 = 200-body 验证通过

判读: exit 0 且台账全 PASS → 部署日 200-body 验证通过, 记录在 44-03 重建配方
之后。human-check 记录面: 真实环境 data_gate 可能翻转 available / coverage 可能
含真实行 —— 本脚本只锁键形状与值集 (data_gate ∈ {available, empty}), 真实值
如实记录, 绝不回填假值。沙箱预检: --base-url http://127.0.0.1:3020 +
DEP_PASSWORD=Command_123 (temp 数据副本 auth.json, RESEARCH A2)。

零新增依赖: python3 stdlib (urllib.request + http.cookiejar + json + argparse)。
"""
from __future__ import annotations

import argparse
import http.cookiejar
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

# ── DTO 契约 (RESEARCH 沙箱实测锁死: 键形状 + 值集, 不锁精确值) ──────────────
_TOP_KEYS_VALIDATION = {
    "data_gate", "empty_reason", "generated_at", "window",
    "probe", "coverage", "skipped_ids", "strategies",
}
_SYMBOLS_KEYS = {
    "auction_symbol_count", "enriched_symbol_count", "symbol_coverage_ratio",
    "auction_rows_present", "auction_rows_expected",
}
_MINUTE_STATS_KEYS = {
    "caliber", "auction_symbol_count", "symbol_coverage_ratio", "unlock_threshold",
    "unlock_met", "dates_covered", "universe_size", "auction_volume_hands",
    "auction_amount_yuan", "amount_unknown_count", "source",
}
_RUN_KEYS = {
    "run_id", "origin", "created_at", "n_hits", "n_strategies", "window",
    "coverage", "strategy_version",
}
_STATS_KEYS = {"n_rows", "n_hits", "per_date", "per_strategy"}
_W5_KEYS = {
    "requested", "backfilled_symbols", "rows", "dates", "failed",
    "failed_symbols", "origin", "rpm",
}
_RUN_ID_RE = re.compile(r"^[0-9a-f]{12}$")
_JOB_ID_RE = re.compile(r"^[0-9a-f]{10}$")
_SYMBOL_RE = re.compile(r"^\d{6}\.(SH|SZ|BJ)$")
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

# 默认 fail-closed 触发体: 远未来窗 → no_scope/source_unavailable, 零上游消耗
_DEFAULT_BACKFILL_BODY = {
    "symbols": ["600519.SH"],
    "start": "2099-01-01",
    "end": "2099-01-02",
}


class ScriptError(Exception):
    """携带 exit 码的脚本级错误 (1 = 断言失败 / 2 = 认证失败 / 3 = 运行错误)。"""

    def __init__(self, code: int, stage: str, detail: str):
        super().__init__(f"[exit {code}] {stage}: {detail}")
        self.code = code
        self.stage = stage
        self.detail = detail


class HttpClient:
    """urllib + cookiejar 封装: 单 opener, cookie 自动保存 (tf_session), 429 尊重
    Retry-After 重试 1 次 (Phase 40 契约), 绝不重试 401。"""

    def __init__(self, base_url: str, timeout: int):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        jar = http.cookiejar.CookieJar()
        self._jar = jar
        self._opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(jar),
        )

    def request(self, method: str, path: str, body: dict | None = None,
                *, expect_401: bool = False) -> tuple[int, dict]:
        """发送请求, 返回 (http_code, parsed_json)。

        - 401 且 expect_401=False → ScriptError(2) (认证失败, 单次尝试即停);
        - 401 且 expect_401=True → 原样返回 (401 先验用);
        - 429 → 尊重 Retry-After 重试 1 次, 仍 429 → ScriptError(3);
        - 其他 HTTP 错误 → ScriptError(1) (认证门失效/异常状态即断言失败);
        - 网络 refused/timeout → ScriptError(3)。
        """
        url = f"{self.base_url}{path}"
        data = None
        headers = {"Accept": "application/json"}
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(url, data=data, headers=headers, method=method)

        code, resp = self._once(req)
        if code == 429:
            # Phase 40 契约: 尊重 Retry-After (秒或 HTTP-date), 仅重试 1 次
            retry_after = self._retry_after_seconds(resp)
            time.sleep(min(retry_after, 30.0))
            code, resp = self._once(req)
            if code == 429:
                raise ScriptError(3, "http", f"429 重试后仍限流: {path}")

        if code == 401 and not expect_401:
            raise ScriptError(2, "auth", f"{method} {path} → 401 未登录/会话过期")
        if 400 <= code < 500 and code != 401:
            raise ScriptError(1, "http", f"{method} {path} → {code} (认证门失效/异常状态)")
        return code, resp

    def _once(self, req: urllib.request.Request) -> tuple[int, dict]:
        try:
            with self._opener.open(req, timeout=self.timeout) as resp:
                raw = resp.read()
                code = resp.getcode()
        except urllib.error.HTTPError as e:
            code = e.code
            raw = e.read()
        except urllib.error.URLError as e:
            reason = getattr(e, "reason", e)
            raise ScriptError(3, "network", f"连接失败: {reason}") from None
        except TimeoutError:
            raise ScriptError(3, "network", f"请求超时 (> {self.timeout}s)") from None
        try:
            payload = json.loads(raw.decode("utf-8")) if raw else {}
        except (UnicodeDecodeError, json.JSONDecodeError):
            payload = {"_raw": raw.decode("utf-8", errors="replace")[:200]}
        return code, payload

    @staticmethod
    def _retry_after_seconds(resp: dict) -> float:
        h = resp.get("_headers", {}) if isinstance(resp, dict) else {}
        ra = h.get("retry-after") or h.get("Retry-After")
        if not ra:
            return 2.0
        try:
            return float(ra)
        except (TypeError, ValueError):
            return 2.0


# ── 断言 helpers (键缺失 = 失败, 非仅长度) ───────────────────────────────────

def _assert(cond: bool, stage: str, detail: str) -> None:
    if not cond:
        raise ScriptError(1, stage, detail)


def _require_keys(obj: dict, keys: set[str], stage: str, where: str) -> list[str]:
    missing = sorted(keys - set(obj.keys()))
    _assert(not missing, stage, f"{where} 缺键: {missing}")
    return missing


# ── 各端点校验 ───────────────────────────────────────────────────────────────

def _check_validation(http: HttpClient, ledger: dict) -> None:
    """GET /api/research/auction/validation → 8 顶层键 + coverage 两子结构 + 值集。"""
    stage = "validation"
    code, body = http.request("GET", "/api/research/auction/validation")
    _assert(code == 200, stage, f"期望 200, 实际 {code}")
    missing = _require_keys(body, _TOP_KEYS_VALIDATION, stage, "validation 顶层")
    data_gate = body.get("data_gate")
    _assert(data_gate in ("available", "empty"),
            stage, f"data_gate 值集外: {data_gate!r}")

    coverage = body.get("coverage")
    _assert(isinstance(coverage, dict), stage, "coverage 非 dict")
    symbols = coverage.get("symbols")
    _assert(isinstance(symbols, dict), stage, "coverage.symbols 非 dict")
    _require_keys(symbols, _SYMBOLS_KEYS, stage, "coverage.symbols")
    minute = coverage.get("minute_stats")
    _assert(isinstance(minute, dict), stage, "coverage.minute_stats 非 dict")
    _assert(len(minute) == len(_MINUTE_STATS_KEYS),
            stage, f"coverage.minute_stats 期望 {len(_MINUTE_STATS_KEYS)} 键, "
                   f"实际 {len(minute)}: {sorted(minute)}")
    _require_keys(minute, _MINUTE_STATS_KEYS, stage, "coverage.minute_stats")
    _assert(minute.get("caliber") == "statistical_minute_0930",
            stage, f"caliber 值集外: {minute.get('caliber')!r}")

    window = body.get("window")
    _assert(isinstance(window, dict), stage, "window 非 dict")
    # 实测定案: requested_start/requested_end/effective_start/effective_end (回夹双字段)
    _require_keys(window, {"requested_start", "requested_end",
                           "effective_start", "effective_end"}, stage, "window")
    probe = body.get("probe")
    _assert(isinstance(probe, dict), stage, "probe 非 dict")
    strategies = body.get("strategies")
    _assert(isinstance(strategies, list), stage, "strategies 非 list")
    if data_gate == "available":
        _assert(len(strategies) > 0, stage, "data_gate=available 但 strategies 空")
    skipped = body.get("skipped_ids")
    _assert(isinstance(skipped, list), stage, "skipped_ids 非 list")

    ledger["validation"] = {
        "code": code,
        "data_gate": data_gate,
        "empty_reason": body.get("empty_reason"),
        "top_keys": sorted(_TOP_KEYS_VALIDATION),
        "missing_keys": missing,
        "symbols_keys": sorted(_SYMBOLS_KEYS),
        "minute_stats_keys": sorted(_MINUTE_STATS_KEYS),
        "minute_stats_len": len(minute),
        "strategies_len": len(strategies),
        "window_requested_start": window.get("requested_start"),
        "window_effective_start": window.get("effective_start"),
        "window_requested_end": window.get("requested_end"),
        "window_effective_end": window.get("effective_end"),
        "probe_status": probe.get("status"),
        "ok": True,
    }


def _check_backtest(http: HttpClient, ledger: dict) -> None:
    """GET /api/research/backtest → {runs, count} + 8 键/run; 首条详情 {manifest,
    stats, sample}。"""
    stage = "backtest"
    code, body = http.request("GET", "/api/research/backtest")
    _assert(code == 200, stage, f"期望 200, 实际 {code}")
    _require_keys(body, {"runs", "count"}, stage, "backtest 顶层")
    runs = body.get("runs")
    count = body.get("count")
    _assert(isinstance(runs, list), stage, "runs 非 list")
    _assert(isinstance(count, int) and count == len(runs),
            stage, f"count({count}) != len(runs)({len(runs)})")

    bad_run = None
    for r in runs:
        if not isinstance(r, dict):
            bad_run = "run 条目非 dict"; break
        missing = _RUN_KEYS - set(r.keys())
        if missing:
            bad_run = f"run 缺键 {sorted(missing)}"; break
        if not _RUN_ID_RE.fullmatch(str(r.get("run_id", ""))):
            bad_run = f"run_id 非法: {r.get('run_id')!r}"; break
    _assert(bad_run is None, stage, f"{bad_run}")

    detail = None
    if runs:
        first = runs[0]
        run_id = str(first["run_id"])
        dcode, dbody = http.request("GET", f"/api/research/backtest/{run_id}")
        _assert(dcode == 200, stage, f"详情期望 200, 实际 {dcode} ({run_id})")
        _require_keys(dbody, {"manifest", "stats", "sample"}, stage, "run 详情顶层")
        stats = dbody.get("stats")
        _assert(isinstance(stats, dict), stage, "详情 stats 非 dict")
        _require_keys(stats, _STATS_KEYS, stage, "详情 stats")
        sample = dbody.get("sample")
        _assert(isinstance(sample, list), stage, "详情 sample 非 list")
        _assert(len(sample) <= 20, stage, f"sample 行数 {len(sample)} > 20")
        manifest = dbody.get("manifest")
        _assert(isinstance(manifest, dict), stage, "详情 manifest 非 dict")
        _require_keys(manifest, {"run_id", "fingerprint", "strategies", "window"},
                      stage, "详情 manifest")
        _assert(manifest.get("run_id") == run_id,
                stage, f"manifest.run_id({manifest.get('run_id')!r}) != {run_id}")
        detail = {
            "run_id": run_id,
            "stats_keys": sorted(_STATS_KEYS),
            "sample_len": len(sample),
            "manifest_run_id_ok": True,
            "ok": True,
        }
    else:
        # 诚实空态: 无 run 时跳过详情 (不伪造), 列表形状断言已过
        detail = {"skipped": "no_runs"}

    ledger["backtest"] = {
        "code": code,
        "runs": count,
        "count_ok": count == len(runs),
        "run_keys": sorted(_RUN_KEYS),
        "detail": detail,
        "ok": True,
    }


def _check_backfill(http: HttpClient, ledger: dict, args) -> None:
    """POST /api/kline/auction/backfill (默认 fail-closed 体) → {status, job_id}
    → 轮询 job 至终态 → result W-5 9 键。"""
    stage = "backfill"
    body = _resolve_backfill_body(args, ledger)
    code, resp = http.request("POST", "/api/kline/auction/backfill", body)
    _assert(code == 200, stage, f"期望 200, 实际 {code}")
    _require_keys(resp, {"status", "job_id"}, stage, "backfill POST 顶层")
    status = resp.get("status")
    _assert(status in ("started", "reused"), stage, f"status 值集外: {status!r}")
    job_id = str(resp.get("job_id", ""))
    _assert(_JOB_ID_RE.fullmatch(job_id), stage, f"job_id 非法: {job_id!r}")

    job_status, result = _poll_job(http, job_id, args.timeout, stage)

    result_keys = []
    if isinstance(result, dict):
        result_keys = sorted(result.keys())
        _require_keys(result, _W5_KEYS, stage, "job result (W-5)")
        if body == _DEFAULT_BACKFILL_BODY:
            # fail-closed 体 → 终态必含 reason (值如实记录不锁死, RESEARCH 实测
            # source_unavailable / no_scope; 缺 reason 即契约漂移)
            _assert("reason" in result, stage,
                    f"fail-closed 体终态缺 reason 键: {result_keys}")
    _assert(job_status in ("succeeded", "failed"),
            stage, f"job 未达终态: {job_status}")

    ledger["backfill"] = {
        "code": code,
        "status": status,
        "job_id": job_id,
        "body_used": _mask_body(body),
        "job_status": job_status,
        "result_keys": result_keys,
        "reason": (result or {}).get("reason"),
        "requested": (result or {}).get("requested"),
        "polled_s": round(time.time() - ledger["_t0"], 1),
        "ok": True,
    }
    # fail-closed 体 → 零上游放大证明 (requested 如实记录, 不锁值)
    if body == _DEFAULT_BACKFILL_BODY:
        ledger["backfill"]["fail_closed_default"] = True


def _resolve_backfill_body(args, ledger: dict) -> dict:
    """构造 backfill POST body。

    - 默认: 远未来窗 fail-closed 体 (零上游, 全量回填绝不触发)。
    - 显式: --symbols/--start/--end 三参数齐全 → 运营显式小范围 (校验格式);
      缺任一 → warning + 仍走默认 fail-closed 体 (双明示, T-44-02-02)。
    """
    explicit = (args.symbols is not None, args.start is not None, args.end is not None)
    if not any(explicit):
        ledger["backfill_note"] = "默认 fail-closed 远未来窗 (零上游); 全量回填 = 运营手动 CLI scripts/auction_backfill.py (36-02 配额纪律)"
        return dict(_DEFAULT_BACKFILL_BODY)

    if not all(explicit):
        print("[warning] --symbols/--start/--end 需三参数齐全才生效 (真实小范围, 运营显式决策); "
              "本次仍走默认 fail-closed 体 (零上游)。", file=sys.stderr)
        ledger["backfill_note"] = "参数不完整 → 强制默认 fail-closed 体 (脚本拒绝部分范围/全量触发)"
        return dict(_DEFAULT_BACKFILL_BODY)

    syms = [s.strip() for s in args.symbols.split(",") if s.strip()]
    if not syms:
        raise ScriptError(3, "args", "--symbols 为空 (拒绝触发无范围回填)")
    bad = [s for s in syms if not _SYMBOL_RE.fullmatch(s)]
    if bad:
        raise ScriptError(3, "args", f"非法 symbol: {bad} (期望 ^\\d{{6}}\\.(SH|SZ|BJ)$)")
    if len(syms) > 6000:
        raise ScriptError(3, "args", f"--symbols 上限 6000, 实际 {len(syms)} (全量 = 运营手动 CLI, 脚本拒绝)")
    for name, v in (("--start", args.start), ("--end", args.end)):
        if not _DATE_RE.fullmatch(v):
            raise ScriptError(3, "args", f"{name} 必须为 YYYY-MM-DD: {v!r}")
    if args.start > args.end:
        raise ScriptError(3, "args", f"--start({args.start}) 不能晚于 --end({args.end})")
    print(f"[info] 运营显式小范围回填: {len(syms)} symbol × [{args.start}, {args.end}] "
          "(merge-upsert 幂等; 全量 = 手动 CLI)", file=sys.stderr)
    ledger["backfill_note"] = "运营显式小范围 (merge-upsert 幂等); 全量 = 手动 CLI"
    return {"symbols": syms, "start": args.start, "end": args.end}


def _poll_job(http: HttpClient, job_id: str, timeout: int, stage: str):
    """GET /api/pipeline/jobs/{job_id} 每 2s 轮询至 status ∈ {succeeded, failed}。"""
    deadline = time.time() + timeout
    while True:
        code, job = http.request("GET", f"/api/pipeline/jobs/{job_id}")
        _assert(code == 200, stage, f"job 轮询期望 200, 实际 {code}")
        _assert(isinstance(job, dict) and "status" in job,
                stage, f"job 响应缺 status: {sorted(job) if isinstance(job, dict) else type(job)}")
        jstatus = job.get("status")
        if jstatus in ("succeeded", "failed"):
            return jstatus, job.get("result")
        if time.time() >= deadline:
            raise ScriptError(3, stage,
                              f"job {job_id} 轮询超时 (> {timeout}s), status={jstatus}")
        time.sleep(2.0)


def _mask_body(body: dict) -> dict:
    """台账用 body 摘录 (不含凭证; backfill body 无凭证, 但保持最小化)。"""
    return {k: (list(v) if isinstance(v, list) else v) for k, v in body.items()}


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="DEP-02 部署日新端点 200-body 验证 (401 先验 → login → "
                    "validation/backtest/backfill 键形状断言 → backfill job 轮询 W-5)",
    )
    parser.add_argument("--base-url", default="http://127.0.0.1:3018",
                        help="应用 base URL (沙箱预检 http://127.0.0.1:3020; 部署日 3018)")
    parser.add_argument("--timeout", type=int, default=30,
                        help="单请求超时 + job 轮询总时限 (秒, 默认 30)")
    parser.add_argument("--out", default=None,
                        help="JSON 台账落盘路径 (原子写入; 缺省仅 stdout 摘要)")
    parser.add_argument("--skip-backfill", action="store_true",
                        help="跳过 backfill 小节 (部署日已跑过真实回填时复用)")
    parser.add_argument("--symbols", default=None,
                        help="显式小范围回填 symbols (逗号分隔, 需与 --start/--end 同传)")
    parser.add_argument("--start", default=None, help="显式小范围起始日 YYYY-MM-DD")
    parser.add_argument("--end", default=None, help="显式小范围结束日 YYYY-MM-DD")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    password = os.environ.get("DEP_PASSWORD")
    if not password:
        print("[fatal] 缺少 DEP_PASSWORD 环境变量 (密码从 .env AUTH_PASSWORD 注入, "
              "绝不硬编码)。", file=sys.stderr)
        return 3

    ledger: dict = {
        "base_url": args.base_url,
        "checked_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "_t0": time.time(),
        "auth_401": {},
        "login": {},
        "ok": False,
    }
    http = HttpClient(args.base_url, args.timeout)
    try:
        # ── 1. 401 先验 3/3 (认证门失效即中止, T-44-02-03) ──────────────
        for method, path, body in (
            ("GET", "/api/research/auction/validation", None),
            ("GET", "/api/research/backtest", None),
            ("POST", "/api/kline/auction/backfill", {}),
        ):
            code, _ = http.request(method, path, body, expect_401=True)
            _assert(code == 401, "auth-401",
                    f"{method} {path} 无 cookie 期望 401, 实际 {code} — 认证门失效")
            ledger["auth_401"][path] = code
        if len(ledger["auth_401"]) != 3:
            raise ScriptError(1, "auth-401", f"401 先验仅 {len(ledger['auth_401'])}/3")

        # ── 2. 真实登录 (单次尝试, 401 即停 exit 2) ──────────────────────
        code, body = http.request("POST", "/api/auth/login", {"password": password})
        _assert(code == 200, "login", f"login 期望 200, 实际 {code}")
        _require_keys(body, {"ok", "authenticated"}, "login", "login body")
        _assert(body.get("ok") is True and body.get("authenticated") is True,
                "login", f"login 断言失败: {body}")
        cookie_ok = any(
            c.name == "tf_session" and c.value for c in http._jar
        )
        _assert(cookie_ok, "login", "未捕获 tf_session cookie")
        ledger["login"] = {"ok": True, "authenticated": True, "tf_session_cookie": True}

        # ── 3. validation ───────────────────────────────────────────────
        _check_validation(http, ledger)

        # ── 4. backtest 列表 + 首条详情 ──────────────────────────────────
        _check_backtest(http, ledger)

        # ── 5. backfill fail-closed + job 轮询 ──────────────────────────
        if not args.skip_backfill:
            _check_backfill(http, ledger, args)

        ledger["ok"] = True
        del ledger["_t0"]
        _emit_ledger(ledger, args.out)
        print(f"VERIFY OK: 401 先验 3/3 → login 200 → validation/backtest "
              f"形状过 → backfill job {ledger.get('backfill', {}).get('job_status', 'skipped')} "
              f"(exit 0)")
        return 0

    except ScriptError as e:
        ledger["ok"] = False
        ledger["error"] = {"stage": e.stage, "detail": e.detail}
        ledger.pop("_t0", None)
        _emit_ledger(ledger, args.out)
        print(f"[fail] exit {e.code}: {e.stage} — {e.detail}", file=sys.stderr)
        return e.code


def _emit_ledger(ledger: dict, out: str | None) -> None:
    """stdout 摘要 + 可选 JSON 台账 (原子落盘: tmp + os.replace)。"""
    print(json.dumps(ledger, ensure_ascii=False, indent=2, default=str))
    if out:
        p = Path(out)
        tmp = p.with_suffix(p.suffix + ".tmp")
        tmp.write_text(json.dumps(ledger, ensure_ascii=False, indent=2, default=str),
                       encoding="utf-8")
        os.replace(tmp, p)


if __name__ == "__main__":
    raise SystemExit(main())
