from __future__ import annotations

import types
from datetime import date
from typing import ClassVar

from app.api import screener as screener_api
from app.services.screener import ScreenerResult


class _CapturingScreenerService:
    calls: ClassVar[list[dict]] = []

    def __init__(self, repo, asset_type="stock"):
        self.repo = repo
        self.asset_type = asset_type

    def latest_date(self):
        return date(2026, 7, 15)

    def build_strategy_context(
        self,
        engine,
        as_of,
        strategy_ids,
        *,
        timeframe="1d",
        params_map=None,
        overrides_map=None,
        current=None,
    ):
        self.calls.append({
            "kind": "context",
            "strategy_ids": strategy_ids,
            "timeframe": timeframe,
            "params_map": params_map,
            "overrides_map": overrides_map,
        })
        return types.SimpleNamespace(as_of=as_of)

    def run_all_with_hits(self, as_of, strategy_ids=None, engine=None):
        """Stub for ScreenerService.run_all_with_hits — mirrors the real flow:
        load overrides → build_strategy_context → engine.run per non-PRESET strategy.
        """
        # 不追加 run_all_with_hits 到 calls — build_strategy_context 追加 context call,
        # 测试通过 calls[0] 获取 context call, 此处不应干扰 calls 顺序。
        as_of_str = str(as_of)
        sids = strategy_ids if strategy_ids else []

        # 镜像真实代码: 从 strategy_config 加载 override 配置
        from app.strategy import config as strategy_config
        data_dir = self.repo.store.data_dir
        all_overrides = strategy_config.list_overrides(data_dir)

        # engine_ids = 非 PRESET 策略 (走 engine.run)
        from app.services.screener import PRESET_STRATEGIES
        engine_ids = [sid for sid in sids if sid not in PRESET_STRATEGIES]

        # 镜像真实代码: 从 overrides 提取 params_map 传给 build_strategy_context
        params_map = {
            sid: dict(ov.get("params") or {})
            for sid, ov in all_overrides.items()
            if sid in engine_ids
        }
        strategy_context = None
        if engine and engine_ids:
            strategy_context = self.build_strategy_context(
                engine, as_of, engine_ids,
                current=None,
                params_map=params_map,
                overrides_map=all_overrides,
            )

        results = {}
        for sid in sids:
            overrides = all_overrides.get(sid, {})
            if sid in PRESET_STRATEGIES:
                results[sid] = {"total": 0, "as_of": as_of_str, "rows": []}
            elif engine and sid in engine_ids:
                r = engine.run(sid, strategy_context, overrides=overrides or None)
                results[sid] = {"total": r.total, "as_of": as_of_str, "rows": []}
            else:
                results[sid] = {"total": 0, "as_of": as_of_str, "rows": []}
        return results


class _CapturingStrategyEngine:
    calls: ClassVar[list[dict]] = []

    def has(self, strategy_id):
        return strategy_id == "builtin_strategy"

    def get(self, strategy_id):
        if not self.has(strategy_id):
            raise ValueError(f"unknown strategy: {strategy_id}")
        return types.SimpleNamespace(meta={"id": strategy_id})

    def run(self, strategy_id, context, *, pool=None, params=None, overrides=None):
        self.calls.append({
            "kind": "run",
            "strategy_id": strategy_id,
            "pool": pool,
            "params": params,
            "overrides": overrides,
        })
        return ScreenerResult(as_of=context.as_of, strategy=strategy_id)

    def run_all(self, context, *, params_map=None, overrides_map=None, strategy_ids=None):
        self.calls.append({
            "kind": "run_all",
            "params_map": params_map,
            "overrides_map": overrides_map,
            "strategy_ids": strategy_ids,
        })
        return {
            strategy_id: ScreenerResult(as_of=context.as_of, strategy=strategy_id)
            for strategy_id in strategy_ids or []
        }


def _api_request(tmp_path, engine):
    repo = types.SimpleNamespace(store=types.SimpleNamespace(data_dir=tmp_path))
    state = types.SimpleNamespace(repo=repo, strategy_engine=engine)
    return types.SimpleNamespace(app=types.SimpleNamespace(state=state))


def _install_api_fakes(monkeypatch):
    _CapturingScreenerService.calls = []
    _CapturingStrategyEngine.calls = []
    monkeypatch.setattr(screener_api, "ScreenerService", _CapturingScreenerService)
    monkeypatch.setattr(screener_api, "_load_ext_value_maps", lambda *_args: {})
    monkeypatch.setattr(screener_api, "_update_cache_strategy", lambda *_args: None)
    monkeypatch.setattr(screener_api.strategy_cache, "write_cache", lambda *_args: None)


def test_single_run_passes_saved_params_to_strategy_engine(monkeypatch, tmp_path):
    engine = _CapturingStrategyEngine()
    request = _api_request(tmp_path, engine)
    _install_api_fakes(monkeypatch)
    saved = {"params": {"threshold": 3.0, "enabled": False}}
    monkeypatch.setattr(screener_api.strategy_config, "load_override", lambda *_args: saved)

    screener_api.run_preset(
        screener_api.PresetRequest(
            strategy_id="builtin_strategy",
            as_of=date(2026, 7, 15),
        ),
        request,
    )

    context_call = _CapturingScreenerService.calls[0]
    run_call = _CapturingStrategyEngine.calls[0]
    assert context_call["params_map"] == {"builtin_strategy": saved["params"]}
    assert context_call["overrides_map"] == {"builtin_strategy": saved}
    assert run_call["params"] == saved["params"]
    assert run_call["overrides"] == saved


def test_batch_run_passes_saved_params_to_strategy_engine(monkeypatch, tmp_path):
    engine = _CapturingStrategyEngine()
    request = _api_request(tmp_path, engine)
    _install_api_fakes(monkeypatch)
    saved = {"params": {"threshold": 3.0, "enabled": False}}
    monkeypatch.setattr(
        screener_api.strategy_config,
        "list_overrides",
        lambda *_args: {"builtin_strategy": saved},
    )

    screener_api.run_all(
        request,
        body={"as_of": "2026-07-15", "strategy_ids": ["builtin_strategy"]},
    )

    context_call = _CapturingScreenerService.calls[0]
    # run_all_with_hits 调用 build_strategy_context (context call), 然后 engine.run (per-strategy)
    run_call = _CapturingStrategyEngine.calls[0]
    expected_params = {"builtin_strategy": saved["params"]}
    expected_overrides = {"builtin_strategy": saved}
    assert context_call["params_map"] == expected_params
    assert context_call["overrides_map"] == expected_overrides
    # engine.run 在 run_all_with_hits 路径不传 params (只有 run_preset 传 params)
    assert run_call["overrides"] == saved


def test_batch_summary_response_still_writes_full_cache(monkeypatch, tmp_path):
    engine = _CapturingStrategyEngine()
    request = _api_request(tmp_path, engine)
    _install_api_fakes(monkeypatch)
    written = []
    monkeypatch.setattr(screener_api.strategy_config, "list_overrides", lambda *_args: {})
    monkeypatch.setattr(screener_api.strategy_cache, "write_cache", lambda *args: written.append(args))

    payload = screener_api.run_all(
        request,
        body={
            "as_of": "2026-07-15",
            "strategy_ids": ["builtin_strategy"],
            "summary_only": True,
        },
    )

    assert payload == {
        "as_of": "2026-07-15",
        "results": {"builtin_strategy": {"total": 0, "as_of": "2026-07-15"}},
    }
    assert written[0][2]["builtin_strategy"]["rows"] == []
