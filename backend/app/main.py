"""FastAPI 入口。"""
from __future__ import annotations

import ipaddress
import json
import logging
import os
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app import __version__
from app.advanced import api as advanced_api
from app.analysis import api as analysis_api
from app.api import (
    alerts,
    auction_backfill,
    auction_history,
    backtest,
    data,
    decision,
    ext_data,
    financials,
    indices,
    intraday,
    kline,
    market_recap,
    market_recap_auction,
    monitor_rules,
    overview,
    pipeline,
    pool,
    portfolio,
    research,
    research_auction,
    research_backtest,
    rps,
    screener,
    signals,
    stock_analysis,
    strategy,
    watchlist,
)
from app.api import research_alpha
from app.api import research_panels
from app.api import walkforward_sse
from app.api import analysis as analysis_menus
from app.api import auth as auth_api
from app.api import settings as settings_api
from app.api.routes import router as core_router
from app.config import settings
from app.jobs import daily_pipeline
from app.operational.repository import OperationalRepository
from app.optional_modules import install_optional_module_routes
from app.portfolio.service import PortfolioService
from app.portfolio.repository import PortfolioRepository
from app.services.quote_service import QuoteService
from app.tickflow import client as tf_client
from app.tickflow.policy import detect_capabilities
from app.tickflow.repository import DataStore, KlineRepository

logging.basicConfig(
    level=settings.log_level,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def _load_advanced_host_fixture() -> tuple[dict[str, object], "AdvancedFixtureReadiness"] | None:
    """Load deployment-owned host configuration before any fixture synchronization can write."""
    from pydantic import ValidationError

    from app.contracts.market_data import AdvancedFixtureReadiness

    advanced_fixture_path = os.environ.get("ADVANCED_HOST_FIXTURE", "").strip()
    if not advanced_fixture_path:
        return None
    try:
        fixture = json.loads(Path(advanced_fixture_path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise RuntimeError("advanced host fixture is unreadable") from error
    allowed_fields = {
        "policy", "advanced_subjects", "revoke_before_run_task_types",
        "runner_wall_clock_seconds", "research_asset_binding", "fixture_readiness",
    }
    if not isinstance(fixture, dict) or set(fixture) - allowed_fields:
        raise RuntimeError("advanced host fixture is malformed")
    try:
        readiness = AdvancedFixtureReadiness.model_validate_json(
            json.dumps(fixture.get("fixture_readiness"))
        )
    except ValidationError as error:
        raise RuntimeError("advanced host fixture readiness is malformed") from error
    return fixture, readiness


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(
        "AthenaQuant v%s starting (data_source_mode=%s)",
        __version__, tf_client.current_mode(),
    )

    # 首次启动: 若配置了 AUTH_PASSWORD 环境变量且未设过密码, 用它初始化。
    # 公网部署免 SSH 端口转发; 已设过密码则不覆盖 (改密码走 UI)。
    try:
        from app.services import auth as auth_service
        auth_service.bootstrap_from_env()
    except Exception as e:  # noqa: BLE001
        logger.warning("auth bootstrap failed: %s", e)

    advanced_host_fixture = _load_advanced_host_fixture()

    # DataStore construction is deferred until advanced fixture readiness has failed closed.
    fixture_mode = os.environ.get("PHASE1_FIXTURE_MODE", "").strip().lower() in {"1", "true", "yes"}
    if fixture_mode:
        readiness = None if advanced_host_fixture is None else advanced_host_fixture[1]
        app.state.phase1_fixture_sync = daily_pipeline.run_phase1_fixture_sync(
            settings.data_dir, readiness=readiness
        )
        from app.services import preferences
        preferences.save({"onboarding_completed": True})
    else:
        app.state.phase1_fixture_sync = None
    store = DataStore()
    repo = KlineRepository(store)
    app.state.datastore = store
    app.state.repo = repo
    operational = OperationalRepository(store.data_dir / "operational.db")
    operational.migrate()
    app.state.operational = operational
    from app.analysis.api import SubjectScope
    from app.analysis.evidence import EvidencePreparationService
    from app.analysis.evidence_loader import GovernedEvidenceLoader
    from app.analysis.graph import build_analysis_graph
    from app.analysis.lifecycle import LifecycleRuleService
    from app.analysis.repository import AnalysisRepository
    from app.analysis.service import AnalysisService

    analysis_repository = AnalysisRepository(operational.database_path)
    analysis_repository.migrate()
    app.state.analysis_repository = analysis_repository
    app.state.analysis_graph = build_analysis_graph(
        checkpoint_path=store.data_dir / "analysis_checkpoints.db"
    )
    # The only authenticated principal source is the request middleware. The router
    # passes that server value through this identity resolver to the lifecycle service.
    app.state.lifecycle_rule_service = LifecycleRuleService(
        repository=analysis_repository,
        reviewer_resolver=lambda principal: principal,
    )
    app.state.analysis_service = AnalysisService(
        repository=analysis_repository,
        evidence_preparer=EvidencePreparationService(),
        graph=app.state.analysis_graph,
        evidence_loader=GovernedEvidenceLoader(
            repository=repo,
            operational_repository=operational,
        ),
        lifecycle_rule_service=app.state.lifecycle_rule_service,
    )

    def resolve_analysis_subject_scope(_request: Request) -> SubjectScope:
        account_subjects = frozenset(
            ("account", str(account["id"])) for account in operational.list_accounts(include_archived=True)
        )
        # Instrument data is public within this authenticated single-user host;
        # portfolio accounts remain limited to existing server-side account records.
        return SubjectScope(account_subjects, unrestricted_kinds=frozenset({"instrument"}))

    app.state.resolve_analysis_subject_scope = resolve_analysis_subject_scope
    from app.backtest.engine import BacktestEngine
    from app.research.artifacts import EvaluationArtifactService
    from app.research.catalog import ExperimentCatalog
    from app.research.evaluation import FactorEvaluationService
    from app.research.factor_dsl import parse_factor
    from app.research.factor_registry import FactorRegistry
    from app.research.hypotheses import ConfiguredFactorHypothesisGateway, FactorHypothesisService
    from app.research.repository import ResearchRepository
    from app.research.universe import UniverseResolver

    research_repository = ResearchRepository(operational.database_path)
    artifact_service = EvaluationArtifactService(store.data_dir)
    app.state.portfolio_repository = PortfolioRepository(operational.database_path)
    app.state.research_repository = research_repository
    from app.research.run_service import ResearchRunService

    app.state.research_run_service = ResearchRunService(research_repository)
    app.state.factor_registry = FactorRegistry(research_repository)
    app.state.research_artifact_service = artifact_service
    app.state.experiment_catalog = ExperimentCatalog(research_repository)
    app.state.backtest_engine = BacktestEngine(repo)
    # WR-03: the PIT universe resolver (survivorship-bias guard) is bound to the
    # research repository and injected into the evaluation service so production
    # evaluation/admission runs carry membership fingerprints instead of always
    # falling back to ``config-symbols``.
    universe_resolver = UniverseResolver(research_repository)
    app.state.universe_resolver = universe_resolver
    app.state.factor_evaluation_service = FactorEvaluationService(
        app.state.backtest_engine, app.state.factor_registry, artifact_service, universe_resolver
    )
    app.state.factor_hypothesis_service = FactorHypothesisService(
        ConfiguredFactorHypothesisGateway.from_current_configuration()
    )
    app.state.research_strategy_handles = {}

    # WR-03: seed the PIT membership table at startup from the instruments
    # dimension (idempotent, append-only) so production manifests carry real
    # membership fingerprints.  ``seed_membership`` ignores rows without a
    # listing date or first bar, so this is a best-effort sync — never fatal on
    # a host whose instruments lake is empty.
    try:
        from app.research.universe import seed_membership

        instruments_frame = repo.get_instruments()
        enriched_frame, _ = repo.get_enriched_latest()
        seeded = seed_membership(
            research_repository,
            instruments_frame,
            enriched_frame,
            universe_name="cn-a-share",
        )
        if seeded:
            logger.info("seeded %d PIT universe membership rows (cn-a-share)", seeded)
    except Exception:  # noqa: BLE001 - best-effort startup sync, never fatal
        logger.warning("PIT universe membership seeding skipped", exc_info=True)

    from app.advanced.authorization import AdvancedAuthorizationService, OperatorPolicy
    from app.advanced.evolution import EvolutionService
    from app.advanced.jobs import AdvancedJobService
    from app.advanced.policy import AdvancedPolicy
    from app.advanced.repository import AdvancedRepository
    from app.advanced.sandbox import CustomStrategySandboxService, LinuxIsolationLauncher
    from app.advanced.viewpoints import ViewpointService

    class _GovernedViewpointSnapshot:
        """Read frozen viewpoint inputs exclusively through the governed Kline repository."""

        def __init__(self, governed_repository: KlineRepository) -> None:
            self._repository = governed_repository

        def evaluate_viewpoint(self, version: dict[str, object]) -> dict[str, object]:
            published_at = version.get("published_at")
            instrument = version.get("instrument")
            benchmark = version.get("benchmark")
            window_days = version.get("evaluation_window_days")
            asset_type = version.get("asset_type")
            if not isinstance(published_at, str) or not isinstance(instrument, str) or not isinstance(benchmark, str):
                return {"status": "unevaluable", "reason": "unsupported_scope"}
            if not isinstance(window_days, int) or window_days not in {20, 60, 120} or asset_type not in {"stock", "etf", "index"}:
                return {"status": "unevaluable", "reason": "unsupported_scope"}
            publication_date = datetime.fromisoformat(published_at).date()
            # A threefold calendar range safely covers the frozen trading-day window without a live quote read.
            end_date = publication_date + timedelta(days=window_days * 3)
            instrument_rows = self._repository.get_daily_asset(
                asset_type, instrument, publication_date, end_date, columns=["date", "close"]
            ).sort("date")
            if instrument_rows.height <= window_days:
                return {"status": "unevaluable", "reason": "missing_price"}
            benchmark_rows = self._repository.get_index_daily(
                benchmark, publication_date, end_date, columns=["date", "close"]
            ).sort("date")
            if benchmark_rows.height <= window_days:
                return {"status": "unevaluable", "reason": "missing_benchmark"}
            instrument_start = instrument_rows.row(0, named=True)
            instrument_end = instrument_rows.row(window_days, named=True)
            benchmark_start = benchmark_rows.row(0, named=True)
            benchmark_end = benchmark_rows.row(window_days, named=True)
            values = (instrument_start["close"], instrument_end["close"], benchmark_start["close"], benchmark_end["close"])
            if not all(isinstance(value, (int, float)) and value > 0 for value in values):
                return {"status": "unevaluable", "reason": "missing_price"}
            return {
                "status": "evaluated",
                "instrument_start": float(instrument_start["close"]),
                "instrument_end": float(instrument_end["close"]),
                "benchmark_start": float(benchmark_start["close"]),
                "benchmark_end": float(benchmark_end["close"]),
                "coverage_start": instrument_start["date"],
                "coverage_end": instrument_end["date"],
            }

    advanced_repository = AdvancedRepository(operational.database_path)
    advanced_repository.migrate()
    advanced_subjects: frozenset[str] | None = None
    revoke_before_run_task_types: frozenset[str] = frozenset()
    runner_wall_clock_seconds = 15
    research_asset_binding: dict[str, object] | None = None
    if advanced_host_fixture is not None:
        fixture, fixture_readiness = advanced_host_fixture
        subjects = fixture.get("advanced_subjects")
        if not isinstance(subjects, list) or not subjects or any(not isinstance(subject, str) or not subject for subject in subjects):
            raise RuntimeError("advanced host fixture subjects are malformed")
        advanced_policy = AdvancedPolicy.bootstrap(fixture.get("policy"))
        raw_binding = fixture.get("research_asset_binding")
        if raw_binding is not None:
            expected_binding = {"strategy_id", "name", "expression", "description", "hypothesis", "provenance"}
            if not isinstance(raw_binding, dict) or set(raw_binding) != expected_binding:
                raise RuntimeError("advanced host fixture research asset binding is malformed")
            if raw_binding.get("strategy_id") != "bullish_alignment" or not all(
                isinstance(raw_binding.get(field), str) and raw_binding[field].strip()
                for field in ("name", "expression", "description", "hypothesis")
            ) or not isinstance(raw_binding.get("provenance"), dict):
                raise RuntimeError("advanced host fixture research asset binding is malformed")
            research_asset_binding = dict(raw_binding)
        revoke_task_types = fixture.get("revoke_before_run_task_types", [])
        if not isinstance(revoke_task_types, list) or any(
            not isinstance(task_type, str) or task_type not in advanced_policy.agent_allowlist
            for task_type in revoke_task_types
        ):
            raise RuntimeError("advanced host fixture revoke configuration is malformed")
        advanced_subjects = frozenset(subjects)
        revoke_before_run_task_types = frozenset(revoke_task_types)
        configured_wall_clock = fixture.get("runner_wall_clock_seconds", runner_wall_clock_seconds)
        if not isinstance(configured_wall_clock, int) or not 15 <= configured_wall_clock <= 120:
            raise RuntimeError("advanced host fixture runner wall-clock is malformed")
        runner_wall_clock_seconds = configured_wall_clock
    else:
        advanced_policy = AdvancedPolicy.bootstrap("advanced_policy_v1")
    app.state.advanced_fixture_readiness = (
        None if advanced_host_fixture is None else advanced_host_fixture[1]
    )
    app.state.advanced_repository = advanced_repository
    app.state.advanced_policy = advanced_policy
    app.state.viewpoint_service = ViewpointService(repository=advanced_repository, policy=advanced_policy)
    app.state.viewpoint_market_snapshot = _GovernedViewpointSnapshot(repo)
    app.state.evolution_service = EvolutionService(
        repository=advanced_repository,
        reviewer_resolver=lambda principal: principal,
    )

    def advanced_operator_policy() -> OperatorPolicy:
        return OperatorPolicy(
            revision=advanced_policy.version,
            task_types=frozenset(advanced_policy.agent_allowlist),
            markets=frozenset({"CN-A"}),
            # The request-scoped resolver is the authority for individual instruments.
            # This wildcard is never exposed to clients and lets that resolver authorize
            # the server-created short-lived record without a browser token.
            instruments=advanced_subjects or frozenset({"*"}),
            rate_limits=advanced_policy.rate_limits,
        )

    advanced_authorization = AdvancedAuthorizationService(
        repository=advanced_repository,
        policy_loader=advanced_operator_policy,
        clock=lambda: datetime.now(UTC),
    )
    app.state.advanced_authorization_service = advanced_authorization
    app.state.advanced_job_service = AdvancedJobService(
        repository=advanced_repository,
        authorization_service=advanced_authorization,
        provider=lambda **_kwargs: None,
        sandbox=lambda **_kwargs: None,
        clock=lambda: datetime.now(UTC),
    )
    if revoke_before_run_task_types:
        def revoke_selected_fixture_job(job: dict[str, object]) -> None:
            if str(job["task_type"]) in revoke_before_run_task_types:
                advanced_repository.revoke_authorization(authorization_id=str(job["authorization_id"]))

        app.state.advanced_job_service.set_before_execution_hook(revoke_selected_fixture_job)
    app.state.advanced_sandbox_service = CustomStrategySandboxService(
        audit_path=operational.database_path,
        governed_input=store.data_dir,
        launcher=LinuxIsolationLauncher(),
    )

    def resolve_advanced_subject_scope(_request: Request) -> advanced_api.AdvancedSubjectScope:
        # Instruments are authenticated single-user research subjects; account-like
        # records must remain explicit server-side subjects.
        if advanced_subjects is None:
            return advanced_api.AdvancedSubjectScope(
                frozenset(), unrestricted_kinds=frozenset({"instrument"})
            )
        return advanced_api.AdvancedSubjectScope(
            frozenset(("instrument", subject) for subject in advanced_subjects)
        )

    def resolve_advanced_research_asset_binding(_request: Request, asset_id: str) -> dict[str, str] | None:
        """Resolve only an extant immutable installed-strategy binding for public work."""

        binding = research_repository.resolve_bound_strategy(asset_id)
        if not isinstance(binding, dict):
            return None
        strategy_id = binding.get("strategy_id")
        revision_id = binding.get("revision")
        if (
            binding.get("research_asset_id") != asset_id
            or not isinstance(strategy_id, str)
            or not isinstance(revision_id, str)
            or app.state.factor_registry.get_revision(revision_id) is None
        ):
            return None
        try:
            app.state.strategy_engine.get(strategy_id)
        except (AttributeError, ValueError):
            return None
        return binding

    def resolve_advanced_research_asset(request: Request, asset_id: str) -> bool:
        """Accept only the exact persisted lifecycle binding target, never a strategy ID."""

        return resolve_advanced_research_asset_binding(request, asset_id) is not None

    app.state.resolve_advanced_subject_scope = resolve_advanced_subject_scope
    app.state.resolve_advanced_research_asset = resolve_advanced_research_asset
    app.state.resolve_advanced_research_asset_binding = resolve_advanced_research_asset_binding
    # 指标异步预热标志: enriched 缓存在后台线程构建, 完成后置 True
    app.state.indicators_ready = False
    repo._on_warmup_done = lambda: setattr(app.state, "indicators_ready", True)  # noqa: SLF001

    # Polars 缓存预热 — enriched 的重计算 (107万行 compute_indicators) 推后台,
    # instruments/index/ETF 仍同步 (毫秒级)。应用立即 ready, 指标算完后自动替换。
    repo.refresh_cache(background=not fixture_mode)

    # 能力探测
    capset = detect_capabilities()
    app.state.capabilities = capset
    logger.info("ready; %d capabilities active", len(capset.all()))

    # 自定义数据源配置(可选): 失败只记录错误, 不影响 TickFlow 基准路径。
    try:
        from app.data_providers import custom as custom_sources
        custom_sources.load_all()
        logger.info("custom data sources loaded: %d", len(custom_sources.list_sources()))
    except Exception as e:  # noqa: BLE001
        logger.warning("custom data sources init failed: %s", e)

    # 全局行情服务
    qs = QuoteService()
    app.state.quote_service = qs
    qs.set_repo(repo)
    app.state.advanced_job_service.set_progress_publisher(qs.notify_advanced_progress)
    from app.advanced.workflow import AdvancedWorkflowServices, build_advanced_graph

    class _LifecycleAuthorizationAdapter:
        async def authorize_and_freeze(self, *, job_id: str, authorization_id: str, subject_ref: str) -> dict[str, object]:
            job = app.state.advanced_job_service.advance_workflow_stage(
                job_id=job_id, from_status="authorized", to_status="frozen", stage="frozen"
            )
            return {
                "authorization_id": authorization_id,
                "subject_ref": subject_ref,
                "frozen_evidence_refs": [f"job:{job['id']}:frozen"],
            }

    class _LifecycleDraftProvider:
        async def generate_draft(self, *, job_id: str, subject_ref: str, evidence_refs: list[str]) -> dict[str, object]:
            app.state.advanced_job_service.advance_workflow_stage(
                job_id=job_id, from_status="frozen", to_status="drafted", stage="drafted"
            )
            return {
                "kind": "viewpoint_draft",
                "rationale": f"Bounded server workflow for {subject_ref}",
                "evidence_refs": evidence_refs,
                "assumptions": [],
                "confidence": 0.0,
            }

    class _LifecycleGateAdapter:
        async def evaluate(self, *, job_id: str, draft: dict[str, object]) -> dict[str, bool]:
            del draft
            app.state.advanced_job_service.advance_workflow_stage(
                job_id=job_id, from_status="drafted", to_status="gates_complete", stage="gates_complete"
            )
            return {"passed": True}

    class _LifecycleOutcomeAdapter:
        async def record_once(self, *, job_id: str, outcome_type: str) -> dict[str, object]:
            return app.state.advanced_job_service.record_workflow_outcome(
                job_id=job_id, outcome_type=outcome_type
            )

    app.state.advanced_job_service.set_workflow(build_advanced_graph(
        checkpoint_path=store.data_dir / "advanced_checkpoints.db",
        services=AdvancedWorkflowServices(
            authorization=_LifecycleAuthorizationAdapter(),
            draft_provider=_LifecycleDraftProvider(),
            gates=_LifecycleGateAdapter(),
            outcomes=_LifecycleOutcomeAdapter(),
            thread_owner=lambda job_id: f"advanced-job-{job_id}",
        ),
    ))
    if not fixture_mode:
        qs.boot_check()
    app.state.portfolio_service = PortfolioService(
        repository=operational,
        quote_service=qs,
        governed_closes=repo,
    )
    from app.notifications.delivery import NotificationDeliveryService
    app.state.notification_delivery = NotificationDeliveryService(repository=operational)

    # QuoteService 需要访问 strategy_monitor 等单例
    # 先创建 strategy_monitor，再注入 app.state
    from app.strategy.monitor import StrategyMonitorService
    strategy_monitor = StrategyMonitorService()
    app.state.strategy_monitor = strategy_monitor
    qs.set_app_state(app.state)

    # 五档盘口 sealed 服务(真假涨停/跌停, 独立旁路线)
    from app.services.depth_service import DepthService
    depth_service = DepthService()
    depth_service.set_repo(repo)
    depth_service.set_app_state(app.state)
    app.state.depth_service = depth_service

    # Fixture acceptance must not start any polling, scheduler, or optional connector.
    if fixture_mode:
        app.state.scheduler = None
        app.state.depth_service = None
        app.state.wecom_bot_service = None
        app.state.pull_scheduler = None
    else:
        try:
            daily_pipeline.set_app_state(app.state)
            app.state.scheduler = daily_pipeline.start_scheduler(repo, capset)
        except Exception as e:  # noqa: BLE001
            logger.warning("scheduler not started: %s", e)
            app.state.scheduler = None
        try:
            depth_service.boot_check()
            depth_service.start_polling()
        except Exception as e:  # noqa: BLE001
            logger.warning("depth_service init failed: %s", e)
        try:
            from app.services.wecom_bot_service import WecomBotService
            wecom_bot_service = WecomBotService()
            wecom_bot_service.set_app_state(app.state)
            app.state.wecom_bot_service = wecom_bot_service
            wecom_bot_service.boot_check()
        except Exception as e:  # noqa: BLE001
            logger.warning("wecom_bot_service init failed: %s", e)
            app.state.wecom_bot_service = None
        from app.services.ext_pull import pull_scheduler
        pull_scheduler.start(store.data_dir)
        pull_scheduler.refresh(store.data_dir)
        app.state.pull_scheduler = pull_scheduler

    if fixture_mode:
        app.state.financial_scheduler = None
    else:
        # 财务调度器仅供显式同步使用；fixture runtime 不加载任何外部 provider。
        from app.services.financial_sync import financial_scheduler
        financial_scheduler.start(store.data_dir, capset)
        app.state.financial_scheduler = financial_scheduler

    # 策略引擎
    from app.services.minute_loader import make_minute_loader
    from app.services.screener import ScreenerService
    from app.strategy.engine import StrategyEngine
    from app.strategy.monitor import StrategyMonitorService

    _screener_svc = ScreenerService(repo)
    _etf_screener_svc = ScreenerService(repo, asset_type="etf")
    strategy_dirs = [
        Path(__file__).resolve().parent / "strategy" / "builtin",
        store.data_dir / "strategies" / "custom",
        store.data_dir / "strategies" / "ai",
    ]
    strategy_engine = StrategyEngine(
        enriched_loader=_screener_svc._load_enriched_for_date,
        enriched_history_loader=_screener_svc._load_enriched_history,
        strategy_dirs=strategy_dirs,
        minute_loader=make_minute_loader(store.data_dir),
    )
    app.state.strategy_engine = strategy_engine
    logger.info("strategy engine loaded: %d strategies", len(strategy_engine.list_strategies()))
    if research_asset_binding is not None:
        strategy_id = str(research_asset_binding["strategy_id"])
        try:
            strategy_engine.get(strategy_id)
        except ValueError as error:
            raise RuntimeError("advanced host fixture selects an unknown installed strategy") from error
        provenance = dict(research_asset_binding["provenance"])
        existing_binding = research_repository.get_strategy_asset_binding(strategy_id)
        if existing_binding is None:
            revision = app.state.factor_registry.create_factor(
                name=str(research_asset_binding["name"]),
                expression=str(research_asset_binding["expression"]),
                description=str(research_asset_binding["description"]),
                hypothesis=str(research_asset_binding["hypothesis"]),
                provenance=provenance,
            )
            existing_binding = research_repository.bind_strategy_asset(
                strategy_id=strategy_id, research_asset_id=revision.id, provenance=provenance
            )
        revision = app.state.factor_registry.get_revision(str(existing_binding["research_asset_id"]))
        declared_revision = (
            str(research_asset_binding["name"]).strip(),
            parse_factor(str(research_asset_binding["expression"])).canonical_expression,
            str(research_asset_binding["description"]).strip(),
            str(research_asset_binding["hypothesis"]).strip(),
        )
        persisted_revision = None if revision is None else (
            revision.name,
            revision.canonical_expression,
            revision.description,
            revision.hypothesis,
        )
        if (
            revision is None
            or existing_binding.get("provenance") != provenance
            or persisted_revision != declared_revision
        ):
            raise RuntimeError("advanced host fixture research asset binding conflicts with persisted lifecycle binding")
        app.state.advanced_research_asset_binding = existing_binding
    from app.advanced.experiments import ExperimentService
    from app.advanced.governed_runner import (
        GovernedExperimentRunner,
        StrategyBacktestExperimentCollaborator,
    )
    from app.backtest.strategy import StrategyBacktestService

    app.state.experiment_service = ExperimentService(
        repository=advanced_repository,
        backtest_runner=GovernedExperimentRunner(
            collaborator=StrategyBacktestExperimentCollaborator(data_dir=store.data_dir),
            wall_clock_seconds=runner_wall_clock_seconds,
            memory_limit_bytes=2 * 1_024 * 1_024 * 1_024,
            cpu_seconds=60,
        ),
        binding_resolver=research_repository.resolve_bound_strategy,
    )

    # 通用监控规则引擎: 启动时 reload 规则到内存态 (修复重启后告警失效)
    from app.services import preferences
    from app.strategy import monitor_rules as mr_store
    from app.strategy.monitor import MonitorRuleEngine
    monitor_engine = MonitorRuleEngine()
    monitor_engine.set_strategy_engine(strategy_engine)
    monitor_engine.set_data_dir(store.data_dir)
    # 复用 ScreenerService 的历史窗口加载器 (三级缓存, 启动预计算命中 ~0ms),
    # 让声明 filter_history 的策略 (如反包) 也能在实时监控里跑选股 → 盘中触发通知。
    monitor_engine.set_history_loader(_screener_svc._load_enriched_history)
    # ETF 版历史加载器: asset_type=etf 的 strategy 型规则用 (读 kline_etf_enriched)。
    monitor_engine.set_history_loader_etf(_etf_screener_svc._load_enriched_history)
    # 板块 loader: scope=sector 规则经 FreeStockDBProvider.get_boards 解析成员。
    # 服务器未配置 (127.0.0.1) 或查询失败时返回 [] → sector 规则 fail-closed 空。
    try:
        from app.data_providers import chain as provider_chain
        from app.data_providers.free_stockdb_provider import FreeStockDBProvider

        _fsdb = provider_chain.free_stockdb_provider()

        def _board_loader(sector: str | list[str]) -> list[dict]:
            # sector 支持板块显示名 (如 "5G") 或板块指数代码 (如 "300843.TI")。
            # get_boards 按 category-name 前缀做子串匹配, 先用它收窄到候选,
            # 再在候选里做精确匹配 (name/code), 避免 "5G" 误命中 "F5G概念"。
            if not sector or not isinstance(_fsdb, FreeStockDBProvider):
                return []
            names = [sector] if isinstance(sector, str) else list(sector)
            # 代码形式 (如 "300843.TI" 或 "300843"): get_boards 的 category-name
            # 子串收窄命中不了纯代码, 走 get_board_by_codes 按代码精确反查。
            if any(n.strip().split(".")[0].isdigit() for n in names if n.strip()):
                try:
                    frame = _fsdb.get_board_by_codes(names)
                except Exception as e:
                    logger.warning("board loader codes %s failed: %s", names, e)
                    frame = None
                if frame is not None and not frame.is_empty():
                    return frame.to_dicts()
                return []
            try:
                frame = _fsdb.get_boards(names)
                if frame is None or frame.is_empty():
                    return []
                rows = frame.to_dicts()
            except Exception as e:
                logger.warning("board loader %s failed: %s", sector, e)
                return []
            wanted = {str(n).strip().lower() for n in names if str(n).strip()}
            exact = [
                r for r in rows
                if str(r.get("name") or "").strip().lower() in wanted
                or str(r.get("code") or "").strip().lower() in wanted
            ]
            if exact:
                return exact
            # 精确未命中 → 退化为子串 (如 sector="白酒" 命中 "白酒概念")。
            return [
                r for r in rows
                if any(w in str(r.get("name") or "").lower() for w in wanted)
            ]
        monitor_engine.set_board_loader(_board_loader)
    except Exception as e:
        logger.warning("board loader unavailable, scope=sector rules will fail-closed: %s", e)

    # 自动迁移: 把旧 strategy_monitor_ids 同步为 type=strategy 规则 (统一到监控页)
    try:
        if preferences.get_strategy_monitor_enabled():
            ids = preferences.get_strategy_monitor_ids()
            if ids:
                names = {s.id: s.name for s in strategy_engine.list_strategies()}
                mr_store.migrate_strategy_monitors(store.data_dir, ids, names)
                logger.info("strategy monitor migrated: %d strategies", len(ids))
    except Exception as e:  # noqa: BLE001
        logger.warning("strategy monitor migration failed: %s", e)

    try:
        rules = mr_store.load_all(store.data_dir)
        monitor_engine.set_rules(rules)
        logger.info("monitor engine loaded: %d rules", monitor_engine.rule_count)
    except Exception as e:  # noqa: BLE001
        logger.warning("monitor engine load failed: %s", e)
    app.state.monitor_engine = monitor_engine

    from app.optional_modules import build_and_install_optional_module_host

    app.state.optional_module_host = build_and_install_optional_module_host(
        app=app,
        database_path=operational.database_path,
        data_root=store.data_dir,
        scheduler=app.state.scheduler,
        quote_service=qs,
        governed_repository=repo,
    )

    yield

    from app.optional_modules import shutdown_optional_module_host

    shutdown_optional_module_host(app)
    if app.state.scheduler:
        app.state.scheduler.shutdown(wait=False)
    ps = getattr(app.state, "pull_scheduler", None)
    if ps:
        ps.stop()
    fsc = getattr(app.state, "financial_scheduler", None)
    if fsc:
        fsc.stop()
    qs = getattr(app.state, "quote_service", None)
    if qs:
        qs.stop()
    dsvc = getattr(app.state, "depth_service", None)
    if dsvc:
        dsvc.stop_polling()
    wbot = getattr(app.state, "wecom_bot_service", None)
    if wbot:
        wbot.stop()
    tf_client.reset_clients()
    logger.info("shutdown")


app = FastAPI(
    title="AthenaQuant",
    version=__version__,
    description="Self-hosted A-share quantitative research platform",
    lifespan=lifespan,
)

# CORS is deployment-owned: only the loopback app and supported local dev origin
# may read credentialed API responses. Same-origin production requests need no CORS.
_LOCAL_AUTHORITIES = frozenset(
    authority
    for hostname in ("localhost", "127.0.0.1", "[::1]")
    for authority in (hostname, f"{hostname}:{settings.port}", f"{hostname}:5173")
)
_LOCAL_ORIGINS = frozenset(
    f"{scheme}://{authority}"
    for scheme in ("http", "https")
    for authority in _LOCAL_AUTHORITIES
)
_LOCAL_REVIEWER_PRINCIPAL = "local_owner_v1"

app.add_middleware(
    CORSMiddleware,
    allow_origins=sorted(_LOCAL_ORIGINS),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ================================================================
# 访问认证中间件
# ================================================================
_AUTH_WHITELIST_PREFIX = ("/api/auth/",)
_AUTH_WHITELIST_EXACT = ("/health", "/api/health", "/openapi.json", "/docs", "/redoc")

# 游客可读路径: 股池页的只读 GET 数据端点 (GUEST-01 / UI-SPEC) + 日期导航 (RQ5 E7)。
# 任何扩宽都会触发 tests/test_guest_masking.py 的守卫 (T-19-03)。
_GUEST_READ_GET_PATHS = frozenset({
    "/api/pool/hub",
    "/api/screener/strategies",
    "/api/pool/dates",
    "/api/pool/history",
    "/api/kline/auction/history",
    "/api/pool/premarket",  # PM-04: 盘前预览对游客只读 (与 hub 同语义, 掩码在前)
})


def _is_guest_readable(path: str, method: str) -> bool:
    """游客仅可读股池页数据的只读 GET 端点 (hub/strategies + 日期导航); 其他路径/方法一律不放行。"""
    return method == "GET" and path in _GUEST_READ_GET_PATHS


def _is_trusted_unconfigured_request(request: Request) -> bool:
    """Admit only exact deployment-owned loopback Host/Origin combinations."""
    if request.client is None:
        return False
    try:
        if not ipaddress.ip_address(request.client.host).is_loopback:
            return False
    except ValueError:
        return False
    host = request.headers.get("host", "").casefold()
    if host not in _LOCAL_AUTHORITIES:
        return False
    origin = request.headers.get("origin")
    return origin is None or origin.casefold() in _LOCAL_ORIGINS


@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    path = request.url.path
    if not path.startswith("/api/"):
        return await call_next(request)

    from app.services import auth as auth_service

    if not auth_service.is_configured():
        if _is_trusted_unconfigured_request(request):
            request.state.reviewer_principal = _LOCAL_REVIEWER_PRINCIPAL
            return await call_next(request)
        return JSONResponse(
            status_code=403,
            content={
                "detail": "面板尚未初始化访问密码,请通过 SSH/本机浏览器访问以设置密码",
                "code": "NOT_INITIALIZED",
            },
        )

    if path.startswith(_AUTH_WHITELIST_PREFIX) or path in _AUTH_WHITELIST_EXACT:
        return await call_next(request)

    token = request.cookies.get(auth_api.COOKIE_NAME)
    if token and auth_service.is_valid_session(token):
        principal = auth_service.resolve_authenticated_reviewer(token)
        if principal:
            request.state.reviewer_principal = principal
            return await call_next(request)
    # 游客分支 (GUEST-01): 无有效会话时, 仅放行股池页的两个只读 GET 端点;
    # 不设置 reviewer_principal (池端点据此派生 mode="guest")。其余一律 401。
    if _is_guest_readable(path, request.method):
        return await call_next(request)
    return JSONResponse(status_code=401, content={"detail": "未登录或会话已过期"})


# 路由
app.include_router(core_router)
app.include_router(auth_api.router)
app.include_router(kline.router)
# CHART-01 只读竞价历史聚合 (GET /api/kline/auction/history, POOL-03 零执行)
app.include_router(auction_history.router)
# AQ-02 竞价历史回填触发端点 (POST /api/kline/auction/backfill, 运营操作)
app.include_router(auction_backfill.router)
app.include_router(watchlist.router)
app.include_router(pool.router)
app.include_router(screener.router)
app.include_router(backtest.router)
app.include_router(research.router)
# BT-03 竞价策略历史验证只读报告 (POOL-03 零执行)
app.include_router(research_auction.router)
# BT-09 竞价回测结果只读查询 (POOL-03 零执行)
app.include_router(research_backtest.router)
app.include_router(intraday.router)
app.include_router(indices.router)
app.include_router(overview.router)
app.include_router(analysis_menus.router)
app.include_router(analysis_api.router)
app.include_router(advanced_api.router)
app.include_router(pipeline.router)
app.include_router(data.router)
app.include_router(ext_data.router)
app.include_router(financials.router)
app.include_router(stock_analysis.router)
app.include_router(market_recap.router)
# REV-05 竞价复盘只读面板端点 (POOL-03 零执行)
app.include_router(market_recap_auction.router)
app.include_router(settings_api.router)
app.include_router(strategy.router)
app.include_router(research_alpha.router)
app.include_router(research_panels.router)
app.include_router(portfolio.router)
app.include_router(decision.router)
app.include_router(research_panels.router)
app.include_router(portfolio_panels.router)
app.include_router(walkforward_sse.router)
app.include_router(alerts.router)
app.include_router(rps.router)

install_optional_module_routes(app)



# 能力门控异常 → 403(而非默认 500)
# 业务代码用 capset.require(Cap.X) 断言能力,缺失时抛 CapabilityDenied;
# 若不注册 handler 会冒泡成 500 Internal Server Error,对前端不友好且语义错误。
from fastapi import Request
from fastapi.responses import JSONResponse

from app.tickflow.capabilities import CapabilityDenied


@app.exception_handler(CapabilityDenied)
async def capability_denied_handler(request: Request, exc: CapabilityDenied) -> JSONResponse:
    return JSONResponse(
        status_code=403,
        content={"detail": str(exc), "suggestion": exc.suggestion},
    )

# 生产期静态文件(前端 dist)
_static = Path(settings.static_dir)
if _static.exists():
    if (_static / "assets").exists():
        app.mount("/assets", StaticFiles(directory=_static / "assets"), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    def spa_fallback(full_path: str):  # noqa: ARG001
        """所有未匹配路径回退到 index.html — React Router 接管。

        index.html 禁止缓存 (Cache-Control: no-store), 确保浏览器每次拿到
        最新版本引用的 JS/CSS 文件名 (assets 带 hash, 可长缓存)。
        """
        # 未匹配的 /api/* 必须是 404 JSON — 前端 fetch 到 HTML 会解析失败,
        # 且会掩盖拼错的路径 / 缺失的路由。SPA 回退只服务非 API 路径。
        if full_path.startswith("api/") or full_path == "api":
            return JSONResponse(status_code=404, content={"detail": "Not Found"})
        index = _static / "index.html"
        if index.exists():
            return FileResponse(
                index,
                headers={"Cache-Control": "no-store, must-revalidate"},
            )
        return {"error": "frontend not built"}
