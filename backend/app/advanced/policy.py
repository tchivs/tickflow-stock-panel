"""Deployment-owned advanced policy bootstrap with no browser configuration path."""
from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from hashlib import sha256
from typing import Any

ADVANCED_POLICY_VERSION = "advanced_policy_v1"


def _canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


@dataclass(frozen=True)
class AdvancedPolicy:
    """Server-loaded profile, benchmark, and task authorization policy."""

    version: str
    source_profiles: Mapping[str, Mapping[str, object]]
    benchmark_defaults: Mapping[str, str]
    benchmark_overrides: frozenset[str]
    agent_allowlist: Mapping[str, tuple[str, ...]]
    rate_limits: Mapping[str, int]
    fingerprint: str

    @classmethod
    def bootstrap(cls, configured: str | Mapping[str, Any] | None) -> AdvancedPolicy:
        """Load only the supported deployment policy, failing closed when absent or malformed."""
        if configured == ADVANCED_POLICY_VERSION:
            configured = {
                "version": ADVANCED_POLICY_VERSION,
                "source_profiles": {"operator-research-v1": {"market_scopes": ["CN-A"]}},
                "benchmark_defaults": {"stock": "000300.SH", "etf": "000300.SH", "index": "000001.SH"},
                "benchmark_overrides": ["000300.SH", "000905.SH", "000852.SH"],
                "agent_allowlist": {"research_draft": ["CN-A"], "experiment": ["CN-A"], "strategy_evaluation": ["CN-A"]},
                "rate_limits": {"research_draft": 10, "experiment": 5, "strategy_evaluation": 5},
            }
        if not isinstance(configured, Mapping):
            raise ValueError("advanced policy bootstrap is required")
        required = {"version", "source_profiles", "benchmark_defaults", "benchmark_overrides", "agent_allowlist", "rate_limits"}
        if set(configured) != required or configured.get("version") != ADVANCED_POLICY_VERSION:
            raise ValueError("advanced policy bootstrap is malformed")
        profiles = configured["source_profiles"]
        defaults = configured["benchmark_defaults"]
        overrides = configured["benchmark_overrides"]
        allowlist = configured["agent_allowlist"]
        limits = configured["rate_limits"]
        if not isinstance(profiles, Mapping) or set(profiles) != {"operator-research-v1"}:
            raise ValueError("advanced policy source profiles are malformed")
        profile = profiles["operator-research-v1"]
        if not isinstance(profile, Mapping) or profile.get("market_scopes") != ["CN-A"]:
            raise ValueError("advanced policy source profile scope is malformed")
        if defaults != {"stock": "000300.SH", "etf": "000300.SH", "index": "000001.SH"}:
            raise ValueError("advanced policy benchmark defaults are malformed")
        if not isinstance(overrides, list) or set(overrides) != {"000300.SH", "000905.SH", "000852.SH"}:
            raise ValueError("advanced policy benchmark overrides are malformed")
        if not isinstance(allowlist, Mapping) or not isinstance(limits, Mapping):
            raise ValueError("advanced policy agent controls are malformed")
        normalized = {
            "version": ADVANCED_POLICY_VERSION,
            "source_profiles": {"operator-research-v1": {"market_scopes": ["CN-A"]}},
            "benchmark_defaults": dict(defaults),
            "benchmark_overrides": sorted(overrides),
            "agent_allowlist": {str(key): sorted(value) for key, value in allowlist.items() if isinstance(value, list)},
            "rate_limits": {str(key): value for key, value in limits.items() if isinstance(value, int) and value > 0},
        }
        if len(normalized["agent_allowlist"]) != len(allowlist) or len(normalized["rate_limits"]) != len(limits):
            raise ValueError("advanced policy agent controls are malformed")
        return cls(
            version=ADVANCED_POLICY_VERSION,
            source_profiles={"operator-research-v1": {"market_scopes": ("CN-A",)}},
            benchmark_defaults=dict(defaults),
            benchmark_overrides=frozenset(overrides),
            agent_allowlist={key: tuple(value) for key, value in normalized["agent_allowlist"].items()},
            rate_limits=dict(normalized["rate_limits"]),
            fingerprint=sha256(_canonical_json(normalized).encode()).hexdigest(),
        )

    def resolve_benchmark(self, *, source_profile: str, market_scope: str, asset_type: str, requested: str | None) -> str:
        profile = self.source_profiles.get(source_profile)
        if profile is None or market_scope not in profile["market_scopes"]:
            raise ValueError("source profile or scope is not permitted")
        if requested is not None:
            if requested not in self.benchmark_overrides:
                raise ValueError("benchmark override is not permitted")
            return requested
        try:
            return self.benchmark_defaults[asset_type]
        except KeyError as error:
            raise ValueError("asset type has no benchmark policy") from error
