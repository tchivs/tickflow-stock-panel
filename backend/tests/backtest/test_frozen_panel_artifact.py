from __future__ import annotations

import json
from datetime import date

import polars as pl
import pytest
from polars.testing import assert_frame_equal


def _scope() -> dict[str, object]:
    return {
        "strategy_id": "fixture_momentum",
        "symbols": ["600000.SH"],
        "start": "2024-01-02",
        "end": "2024-06-28",
        "asset_type": "stock",
        "mode": "full",
    }


def _panel() -> pl.DataFrame:
    return pl.DataFrame(
        {
            "symbol": ["600000.SH", "600000.SH"],
            "date": [date(2023, 12, 29), date(2024, 1, 2)],
            "open": [7.0, 7.2],
            "close": [7.1, 7.3],
            "signal_fixture": [False, True],
        }
    )


def test_frozen_panel_artifact_round_trips_only_when_scope_and_checksums_match(tmp_path):
    from app.backtest.frozen_panel import FrozenPanelArtifactStore

    store = FrozenPanelArtifactStore(tmp_path / "research-artifacts")
    reference = store.create(scope=_scope(), panel=_panel())

    restored = store.load(reference=reference, expected_scope=_scope())

    assert_frame_equal(restored, _panel())
    assert reference["schema_version"] == "frozen-panel-artifact-v1"
    assert reference["scope_checksum"]
    assert reference["panel_checksum"]
    assert reference["metadata_checksum"]


@pytest.mark.parametrize("failure", ["absent", "partial", "tampered", "version", "scope", "checksum"])
def test_frozen_panel_artifact_fails_closed_for_invalid_or_tampered_inputs(tmp_path, failure):
    from app.backtest.frozen_panel import FrozenPanelArtifactError, FrozenPanelArtifactStore

    store = FrozenPanelArtifactStore(tmp_path / "research-artifacts")
    reference = store.create(scope=_scope(), panel=_panel())
    artifact_dir = store.root / reference["artifact_id"]
    metadata_path = artifact_dir / "metadata.json"
    panel_path = artifact_dir / "panel.parquet"

    if failure == "absent":
        panel_path.unlink()
    elif failure == "partial":
        metadata_path.unlink()
    elif failure == "tampered":
        panel_path.write_bytes(b"not parquet")
    elif failure == "version":
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        metadata["schema_version"] = "frozen-panel-artifact-v0"
        metadata_path.write_text(json.dumps(metadata), encoding="utf-8")
    elif failure == "scope":
        reference = {**reference, "scope_checksum": "0" * 64}
    elif failure == "checksum":
        reference = {**reference, "panel_checksum": "0" * 64}

    with pytest.raises(FrozenPanelArtifactError):
        store.load(reference=reference, expected_scope=_scope())
