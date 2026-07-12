"""FastAPI 入口。"""
from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app import __version__
from app.api import analysis as analysis_menus, auth as auth_api, backtest, data, decision, ext_data, financials, indices, intraday, kline, market_recap, monitor_rules, alerts, overview, pipeline, portfolio, research, rps, screener, settings as settings_api, signals, stock_analysis, strategy, watchlist
from app.analysis import api as analysis_api
from app.advanced import api as advanced_api
from app.api.routes import router as core_router
from app.config import settings
from app.jobs import daily_pipeline
from app.operational.repository import OperationalRepository
from app.portfolio.service import PortfolioService
from app.services.quote_service import QuoteService
from app.tickflow import client as tf_client
from app.tickflow.policy import detect_capabilities
from app.tickflow.repository import DataStore, KlineRepository

logging.basicConfig(
    level=settings.log_level,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(
        "TickFlow Stock Panel v%s starting (mode=%s)",
        __version__, tf_client.current_mode(),
    )

    # 首次启动: 若配置了 AUTH_PASSWORD 环境变量且未设过密码, 用它初始化。
    # 公网部署免 SSH 端口转发; 已设过密码则不覆盖 (改密码走 UI)。
    try:
        from app.services import auth as auth_service
        auth_service.bootstrap_from_env()
    except Exception as e:  # noqa: BLE001
        logger.warning("auth bootstrap failed: %s", e)

    # 数据层
    store = DataStore()
    repo = KlineRepository(store)
    fixture_mode = os.environ.get("PHASE1_FIXTURE_MODE", "").strip().lower() in {"1", "true", "yes"}
    if fixture_mode:
        app.state.phase1_fixture_sync = daily_pipeline.run_phase1_fixture_sync(store.data_dir)
        store.db.close()
        store = DataStore()
        repo = KlineRepository(store)
        from app.services import preferences
        preferences.save({"onboarding_completed": True})
    else:
        app.state.phase1_fixture_sync = None
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
    from app.research.factor_registry import FactorRegistry
    from app.research.hypotheses import ConfiguredFactorHypothesisGateway, FactorHypothesisService
    from app.research.repository import ResearchRepository

    research_repository = ResearchRepository(operational.database_path)
    artifact_service = EvaluationArtifactService(store.data_dir)
    app.state.research_repository = research_repository
    app.state.factor_registry = FactorRegistry(research_repository)
    app.state.research_artifact_service = artifact_service
    app.state.experiment_catalog = ExperimentCatalog(research_repository)
    app.state.backtest_engine = BacktestEngine(repo)
    app.state.factor_evaluation_service = FactorEvaluationService(
        app.state.backtest_engine, app.state.factor_registry, artifact_service
    )
    app.state.factor_hypothesis_service = FactorHypothesisService(
        ConfiguredFactorHypothesisGateway.from_current_configuration()
    )
    app.state.research_strategy_handles = {}

    from app.advanced.authorization import AdvancedAuthorizationService, OperatorPolicy
    from app.advanced.evolution import EvolutionService
    from app.advanced.jobs import AdvancedJobService
    from app.advanced.policy import AdvancedPolicy
    from app.advanced.repository import AdvancedRepository
    from app.advanced.sandbox import CustomStrategySandboxService, LinuxIsolationLauncher
    from app.advanced.viewpoints import ViewpointService

    advanced_repository = AdvancedRepository(operational.database_path)
    advanced_repository.migrate()
    advanced_policy = AdvancedPolicy.bootstrap("advanced_policy_v1")
    app.state.advanced_repository = advanced_repository
    app.state.advanced_policy = advanced_policy
    app.state.viewpoint_service = ViewpointService(repository=advanced_repository, policy=advanced_policy)
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
            instruments=frozenset({"*"}),
            quota_per_window=max(advanced_policy.rate_limits.values()),
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
    app.state.advanced_sandbox_service = CustomStrategySandboxService(
        audit_path=operational.database_path,
        governed_input=store.data_dir,
        launcher=LinuxIsolationLauncher(),
    )

    def resolve_advanced_subject_scope(_request: Request) -> advanced_api.AdvancedSubjectScope:
        # Instruments are authenticated single-user research subjects; account-like
        # records must remain explicit server-side subjects.
        return advanced_api.AdvancedSubjectScope(
            frozenset(), unrestricted_kinds=frozenset({"instrument"})
        )

    def resolve_advanced_research_asset(_request: Request, asset_id: str) -> bool:
        # A browser identifier is only a lookup key. The persisted factor registry
        # remains the authority for whether it identifies a governed research asset.
        return isinstance(asset_id, str) and app.state.factor_registry.get_revision(asset_id) is not None

    app.state.resolve_advanced_subject_scope = resolve_advanced_subject_scope
    app.state.resolve_advanced_research_asset = resolve_advanced_research_asset
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
    from app.strategy.engine import StrategyEngine
    from app.strategy.monitor import StrategyMonitorService
    from app.services.screener import ScreenerService

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
    )
    app.state.strategy_engine = strategy_engine
    logger.info("strategy engine loaded: %d strategies", len(strategy_engine.list_strategies()))
    from app.advanced.experiments import ExperimentService
    from app.advanced.governed_runner import GovernedExperimentRunner, StrategyBacktestExperimentCollaborator
    from app.backtest.strategy import StrategyBacktestService

    app.state.experiment_service = ExperimentService(
        repository=advanced_repository,
        backtest_runner=GovernedExperimentRunner(
            collaborator=StrategyBacktestExperimentCollaborator(
                StrategyBacktestService(app.state.backtest_engine, strategy_engine)
            )
        ),
    )

    # 通用监控规则引擎: 启动时 reload 规则到内存态 (修复重启后告警失效)
    from app.strategy.monitor import MonitorRuleEngine
    from app.strategy import monitor_rules as mr_store
    from app.services import preferences
    monitor_engine = MonitorRuleEngine()
    monitor_engine.set_strategy_engine(strategy_engine)
    monitor_engine.set_data_dir(store.data_dir)
    # 复用 ScreenerService 的历史窗口加载器 (三级缓存, 启动预计算命中 ~0ms),
    # 让声明 filter_history 的策略 (如反包) 也能在实时监控里跑选股 → 盘中触发通知。
    monitor_engine.set_history_loader(_screener_svc._load_enriched_history)
    # ETF 版历史加载器: asset_type=etf 的 strategy 型规则用 (读 kline_etf_enriched)。
    monitor_engine.set_history_loader_etf(_etf_screener_svc._load_enriched_history)

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

    yield

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
    logger.info("shutdown")


app = FastAPI(
    title="TickFlow Stock Panel",
    version=__version__,
    description="A 股选股 + 回测面板 — TickFlow 适配",
    lifespan=lifespan,
)

# CORS: 允许局域网访问 (自托管场景, 放开所有来源)
# 注: allow_credentials=True 与 allow_origins=['*'] 不能共存 (浏览器规范),
# 本项目认证走 header (API Key), 不依赖 cookie, 故关闭 credentials 换取通配来源。
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ================================================================
# 访问认证中间件
# ================================================================
# 拦截所有 /api/ 请求, 三种状态:
#   1. 未设密码 + 本机/内网 → 放行(让本机用户访问面板 + 调 /api/auth/setup 设密码)
#   2. 未设密码 + 公网       → 拒绝(403, 防裸奔也防抢占; 引导本机设密码)
#   3. 已设密码              → 检查 session, 无效则 401(前端跳登录)
# 白名单: /api/auth/* (设密码/登录本身)、/health 等探活。
_AUTH_WHITELIST_PREFIX = ("/api/auth/",)
_AUTH_WHITELIST_EXACT = ("/health", "/api/health", "/openapi.json", "/docs", "/redoc")


@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    path = request.url.path
    # 仅 /api/ 走认证; 静态资源(前端页面/assets)放行, 由前端处理跳转
    if not path.startswith("/api/"):
        return await call_next(request)
    # 白名单放行(设密码/登录/探活本身不拦)
    if path.startswith(_AUTH_WHITELIST_PREFIX) or path in _AUTH_WHITELIST_EXACT:
        return await call_next(request)

    from app.services import auth as auth_service
    # 情况 1+2: 未设密码
    if not auth_service.is_configured():
        # 本机/内网 → 放行(服务器主人可访问, 并去 /login 设密码)
        if auth_api._is_local_network(auth_api._client_ip(request)):
            return await call_next(request)
        # 公网 → 拒绝。不裸奔, 也不给公网设密码的机会(防抢占)
        return JSONResponse(
            status_code=403,
            content={
                "detail": "面板尚未初始化访问密码,请通过 SSH/本机浏览器访问以设置密码",
                "code": "NOT_INITIALIZED",
            },
        )

    # 情况 3: 已设密码, 检查会话
    token = request.cookies.get(auth_api.COOKIE_NAME)
    if token and auth_service.is_valid_session(token):
        request.state.reviewer_principal = auth_service.resolve_authenticated_reviewer(token)
        return await call_next(request)
    # 未登录: 401(前端跳登录页)
    return JSONResponse(status_code=401, content={"detail": "未登录或会话已过期"})


# 路由
app.include_router(core_router)
app.include_router(auth_api.router)
app.include_router(kline.router)
app.include_router(watchlist.router)
app.include_router(screener.router)
app.include_router(backtest.router)
app.include_router(research.router)
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
app.include_router(settings_api.router)
app.include_router(strategy.router)
app.include_router(signals.router)
app.include_router(monitor_rules.router)
app.include_router(portfolio.router)
app.include_router(decision.router)
app.include_router(alerts.router)
app.include_router(rps.router)


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
        index = _static / "index.html"
        if index.exists():
            return FileResponse(
                index,
                headers={"Cache-Control": "no-store, must-revalidate"},
            )
        return {"error": "frontend not built"}
