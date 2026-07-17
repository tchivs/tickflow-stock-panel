"""RED contracts for governed daily Forecast inputs and CN-A sessions."""
from __future__ import annotations

import hashlib
import json
from datetime import date
from pathlib import Path

import polars as pl
import pytest

FIXTURES = Path(__file__).parent / "fixtures"
DAILY = FIXTURES / "governed_daily.parquet"
SESSIONS = FIXTURES / "cn_a_sessions.parquet"


def _calendar_frame() -> pl.DataFrame:
    frame = pl.read_parquet(SESSIONS)
    anchors = []
    for calendar_id, revision in frame.select(
        ["calendar_id", "calendar_revision"]
    ).unique(maintain_order=True).iter_rows():
        anchors.append(
            {
                "calendar_id": calendar_id,
                "calendar_revision": revision,
                "market": "CN-A",
                "session_id": "CNA-20250430",
                "trade_date": date(2025, 4, 30),
                "is_open": True,
                "sequence": 0,
            }
        )
    return pl.concat([pl.DataFrame(anchors, schema=frame.schema), frame])


class GovernedFixtureRepository:
    def __init__(self, frame: pl.DataFrame | None = None, *, asset_type: str = "stock", frequency: str = "daily") -> None:
        self.frame = (
            frame
            if frame is not None
            else pl.read_parquet(DAILY).filter(pl.col("case_id") == "valid").drop("case_id")
        )
        self.asset_type = asset_type
        self.frequency = frequency
        self.reads = 0

    def resolve_instrument(self, *, principal: str, instrument_id: str):
        if principal != "researcher-1" or instrument_id != "instrument-600000":
            raise LookupError("instrument not found")
        return {
            "instrument_id": instrument_id,
            "symbol": "600000.SH",
            "market": "CN-A",
            "asset_type": self.asset_type,
        }

    def get_daily(self, *, symbol: str, as_of: str):
        self.reads += 1
        return self.frame.filter(pl.col("trade_date") <= pl.lit(as_of).str.to_date())


def _services(tmp_path: Path, *, repository: GovernedFixtureRepository | None = None):
    from app.forecast.calendar import GovernedTradingCalendar
    from app.forecast.input import ForecastInputFreezer
    calendar = GovernedTradingCalendar(_calendar_frame())
    repo = repository or GovernedFixtureRepository()
    freezer = ForecastInputFreezer(repository=repo, calendar=calendar, artifact_root=tmp_path / "forecast-inputs")
    return freezer, repo, calendar


def _request(**overrides):
    from app.forecast.input import ForecastRequest
    payload = {
        "instrument_id": "instrument-600000",
        "horizon": 20,
        "catalog_id": "kronos-mini",
    }
    payload.update(overrides)
    return ForecastRequest.model_validate(payload)


def test_calendar_resolves_exact_governed_5_20_and_60_future_sessions(tmp_path):
    _freezer, _repo, calendar = _services(tmp_path)
    for horizon in (5, 20, 60):
        sessions = calendar.future_sessions(calendar_id="cn-a-v1", after_session_id="CNA-20250430", count=horizon)
        assert len(sessions) == horizon
        assert sessions[0].session_id == "CNA-20250506"
        assert sessions[-1].session_id.startswith("CNA-")


def test_calendar_rejects_insufficient_future_session_coverage(tmp_path):
    _freezer, _repo, calendar = _services(tmp_path)
    with pytest.raises(ValueError, match="insufficient"):
        calendar.future_sessions(calendar_id="cn-a-short-v1", after_session_id="CNA-20250430", count=20)


def test_calendar_never_approximates_weekdays_or_external_holidays(tmp_path, monkeypatch):
    def denied(*_args, **_kwargs):
        raise AssertionError("calendar approximation or network provider used")
    monkeypatch.setattr("pandas.bdate_range", denied)
    monkeypatch.setattr("socket.create_connection", denied)
    _freezer, _repo, calendar = _services(tmp_path)
    sessions = calendar.future_sessions(calendar_id="cn-a-v1", after_session_id="CNA-20250430", count=5)
    assert "CNA-20250501" not in {session.session_id for session in sessions}


def test_request_accepts_only_5_20_and_60_horizons():
    for horizon in (5, 20, 60):
        assert _request(horizon=horizon).horizon == horizon
    for horizon in (0, 1, 10, 30, 61, 120):
        with pytest.raises(ValueError):
            _request(horizon=horizon)


def test_request_forbids_browser_fingerprint_digest_scope_and_paths():
    forbidden = {
        "input_fingerprint": "0" * 64,
        "checkpoint_digest": "1" * 64,
        "principal": "forged",
        "symbol": "600000.SH",
        "local_model_dir": "/tmp/model",
        "quantiles": {},
        "paths": [],
        "status": "completed",
    }
    for key, value in forbidden.items():
        with pytest.raises(ValueError):
            _request(**{key: value})


def test_input_authorizes_one_persisted_stock_instrument(tmp_path):
    freezer, repo, _calendar = _services(tmp_path)
    frozen = freezer.freeze(request=_request(horizon=5), principal="researcher-1", as_of_session_id="CNA-20250430")
    assert frozen.instrument_id == "instrument-600000"
    assert frozen.symbol == "600000.SH"
    assert repo.reads == 1
    with pytest.raises(LookupError):
        freezer.freeze(request=_request(), principal="foreign", as_of_session_id="CNA-20250430")


def test_input_rejects_index_etf_intraday_and_portfolio_batch(tmp_path):
    for asset_type in ("index", "etf"):
        freezer, repo, _calendar = _services(tmp_path, repository=GovernedFixtureRepository(asset_type=asset_type))
        with pytest.raises(ValueError, match="stock"):
            freezer.freeze(request=_request(), principal="researcher-1", as_of_session_id="CNA-20250430")
        assert repo.reads == 0
    with pytest.raises(ValueError):
        _request(instrument_ids=["instrument-600000", "instrument-000001"])
    with pytest.raises(ValueError):
        _request(frequency="intraday")


def test_input_amount_coverage_is_all_or_none_before_freezing(tmp_path):
    partial_freezer, _repo, _calendar = _services(tmp_path)
    partial = partial_freezer.freeze(
        request=_request(), principal="researcher-1", as_of_session_id="CNA-20250430"
    )
    partial_frame = pl.read_parquet(partial.descriptor.managed_path)
    assert "amount" not in partial.feature_schema
    assert "amount" not in partial_frame.columns

    complete_source = (
        pl.read_parquet(DAILY)
        .filter(pl.col("case_id") == "valid")
        .drop("case_id")
        .with_columns(pl.col("amount").fill_null(pl.col("close") * pl.col("volume")))
    )
    complete_freezer, _repo, _calendar = _services(
        tmp_path / "complete", repository=GovernedFixtureRepository(complete_source)
    )
    complete = complete_freezer.freeze(
        request=_request(), principal="researcher-1", as_of_session_id="CNA-20250430"
    )
    assert complete.feature_schema[-1] == "amount"
    assert pl.read_parquet(complete.descriptor.managed_path)["amount"].null_count() == 0


def test_input_rejects_missing_required_columns_without_synthesizing_values(tmp_path):
    malformed = pl.read_parquet(DAILY).drop("volume")
    freezer, repo, _calendar = _services(tmp_path, repository=GovernedFixtureRepository(malformed))
    with pytest.raises(ValueError, match="volume"):
        freezer.freeze(request=_request(), principal="researcher-1", as_of_session_id="CNA-20250430")
    assert repo.reads == 1


def test_input_rejects_duplicate_unsorted_and_nonfinite_rows(tmp_path):
    source = pl.read_parquet(DAILY)
    cases = [
        source,
        source.sort("trade_date", descending=True),
        source.with_columns(pl.when(pl.arange(0, source.height) == 0).then(float("nan")).otherwise(pl.col("close")).alias("close")),
    ]
    for frame in cases:
        freezer, _repo, _calendar = _services(tmp_path, repository=GovernedFixtureRepository(frame))
        with pytest.raises(ValueError, match="duplicate|sorted|finite"):
            freezer.freeze(request=_request(), principal="researcher-1", as_of_session_id="CNA-20250430")


def test_input_enforces_as_of_boundary_without_future_leakage(tmp_path):
    freezer, _repo, _calendar = _services(tmp_path)
    frozen = freezer.freeze(request=_request(horizon=5), principal="researcher-1", as_of_session_id="CNA-20250430")
    restored = pl.read_parquet(frozen.descriptor.managed_path)
    assert restored["trade_date"].max().isoformat() == "2025-04-30"
    assert frozen.as_of_session_id == "CNA-20250430"
    assert all(session > "CNA-20250430" for session in frozen.future_session_ids)


def test_input_rejects_insufficient_lookback_and_catalog_context(tmp_path):
    short = pl.read_parquet(DAILY).tail(10)
    freezer, _repo, _calendar = _services(tmp_path, repository=GovernedFixtureRepository(short))
    with pytest.raises(ValueError, match="coverage|lookback"):
        freezer.freeze(
            request=_request(horizon=60),
            principal="researcher-1",
            as_of_session_id="CNA-20250430",
            lookback=64,
            max_context=512,
        )
    with pytest.raises(ValueError, match="context"):
        freezer.freeze(
            request=_request(),
            principal="researcher-1",
            as_of_session_id="CNA-20250430",
            lookback=513,
            max_context=512,
        )


def test_input_freezes_adjustment_calendar_schema_and_session_provenance(tmp_path):
    freezer, _repo, _calendar = _services(tmp_path)
    frozen = freezer.freeze(request=_request(horizon=20), principal="researcher-1", as_of_session_id="CNA-20250430")
    assert frozen.adjustment_policy == "raw-unadjusted"
    assert frozen.adjustment_revision == "adj-cn-a-v1"
    assert frozen.calendar_revision == "cn-a-calendar-2025-v1"
    assert len(frozen.historical_session_ids) >= frozen.lookback
    assert len(frozen.future_session_ids) == 20
    assert frozen.feature_schema == ["open", "high", "low", "close", "volume"]


def test_input_fingerprint_is_server_derived_complete_and_deterministic(tmp_path):
    freezer, _repo, _calendar = _services(tmp_path)
    first = freezer.freeze(request=_request(), principal="researcher-1", as_of_session_id="CNA-20250430")
    second = freezer.freeze(request=_request(), principal="researcher-1", as_of_session_id="CNA-20250430")
    assert first.input_fingerprint == second.input_fingerprint
    assert len(first.input_fingerprint) == 64
    manifest = json.loads(first.descriptor.metadata_json)
    expected = hashlib.sha256(json.dumps(manifest["fingerprint_payload"], sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    assert first.input_fingerprint == expected


def test_input_artifact_is_atomic_immutable_and_checksum_verified(tmp_path):
    freezer, _repo, _calendar = _services(tmp_path)
    frozen = freezer.freeze(request=_request(), principal="researcher-1", as_of_session_id="CNA-20250430")
    artifact = Path(frozen.descriptor.managed_path)
    assert artifact.exists()
    assert not list(artifact.parent.glob("*.tmp"))
    original = artifact.read_bytes()
    artifact.write_bytes(b"tampered")
    with pytest.raises(ValueError, match="checksum"):
        freezer.load(frozen.descriptor)
    artifact.write_bytes(original)
    assert freezer.load(frozen.descriptor).height > 0


def test_input_artifact_descriptor_is_root_contained_and_public_path_free(tmp_path):
    freezer, _repo, _calendar = _services(tmp_path)
    frozen = freezer.freeze(request=_request(), principal="researcher-1", as_of_session_id="CNA-20250430")
    public = frozen.descriptor.public()
    serialized = json.dumps(public)
    assert str(tmp_path) not in serialized
    assert set(public) == {"artifact_id", "schema_version", "byte_size", "checksum_sha256"}


def test_input_frame_bytes_and_artifact_checksum_bind_the_fingerprint(tmp_path):
    source = pl.read_parquet(DAILY).filter(pl.col("case_id") == "valid").drop("case_id")
    baseline_freezer, _repo, _calendar = _services(
        tmp_path / "baseline", repository=GovernedFixtureRepository(source)
    )
    baseline = baseline_freezer.freeze(
        request=_request(), principal="researcher-1", as_of_session_id="CNA-20250430"
    )

    changed = source.with_columns(
        pl.when(pl.col("session_id") == "CNA-20250430")
        .then(pl.col("close") + 0.01)
        .otherwise(pl.col("close"))
        .alias("close")
    )
    changed_freezer, _repo, _calendar = _services(
        tmp_path / "changed", repository=GovernedFixtureRepository(changed)
    )
    mutated = changed_freezer.freeze(
        request=_request(), principal="researcher-1", as_of_session_id="CNA-20250430"
    )

    assert mutated.input_fingerprint != baseline.input_fingerprint
    metadata = json.loads(baseline.descriptor.metadata_json)
    payload = metadata["fingerprint_payload"]
    assert payload["frame_payload_sha256"]
    assert payload["artifact_checksum_sha256"] == baseline.descriptor.checksum_sha256


def test_calendar_exact_as_of_sequence_rejects_missing_or_closed_anchor(tmp_path):
    from app.forecast.calendar import GovernedTradingCalendar

    frame = _calendar_frame()
    missing = GovernedTradingCalendar(
        frame.filter(pl.col("session_id") != "CNA-20250430")
    )
    with pytest.raises(ValueError, match="as-of"):
        missing.future_sessions(
            calendar_id="cn-a-v1", after_session_id="CNA-20250430", count=5
        )

    closed = GovernedTradingCalendar(
        frame.with_columns(
            pl.when(pl.col("session_id") == "CNA-20250430")
            .then(False)
            .otherwise(pl.col("is_open"))
            .alias("is_open")
        )
    )
    with pytest.raises(ValueError, match="open as-of"):
        closed.future_sessions(
            calendar_id="cn-a-v1", after_session_id="CNA-20250430", count=5
        )
