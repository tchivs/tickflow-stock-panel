"""FastAPI 入口 — 组装层。

职责边界 (拆分自 955 行单体):
  - ``app/bootstrap.py``   : lifespan 服务初始化/关停编排
  - ``app/api/security_middleware.py`` : 认证/游客/回环放行中间件
  - 本文件                 : FastAPI 实例、CORS、路由注册、异常处理、SPA 静态回退

upstream v0.2 并入 (保持拆分结构不变):
  - 文件日志 (data/backend.log, RotatingFileHandler)
  - 单实例 mining 进程锁 + MiningJobManager 中断作业恢复
  - 回测矩阵 managed generation 固定 + 磁盘缓存后台预热
  - extensions 二次开发系统 (路由注册 + 启动钩子)
  - mining / regime 路由
"""

from __future__ import annotations

import logging
import sys
from contextlib import asynccontextmanager
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
    audit,
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
    mining,
    monitor_rules,
    overview,
    phase5_real_host,
    pipeline,
    pool,
    portfolio,
    portfolio_panels,
    regime,
    research,
    research_alpha,
    research_alpha_sse,
    research_auction,
    research_backtest,
    research_panels,
    research_promotion,
    rps,
    screener,
    signals,
    stock_analysis,
    strategy,
    walkforward_sse,
    watchlist,
    workbench,
)
from app.api import analysis as analysis_menus
from app.api import auth as auth_api
from app.api import settings as settings_api
from app.api.routes import router as core_router
from app.api.security_middleware import _LOCAL_ORIGINS, auth_middleware
from app.bootstrap import init_app_state, shutdown_app_state
from app.config import settings
from app.enriched_generation import EnrichedGenerationUnavailableError
from app.extensions.loader import (
    configure_backend_extensions,
    current_extension_context,
    start_backend_extensions,
)
from app.optional_modules import install_optional_module_routes
from app.services.matrix_prewarm_owner import MatrixCachePrewarmOwner
from app.services.mining_process_lock import MiningProcessLock
from app.tickflow.capabilities import CapabilityDenied

logging.basicConfig(
    level=settings.log_level,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

# 追加文件日志: uvicorn (含 --reload 开发模式) 默认只有 StreamHandler, 同步/管道等
# 运行时日志仅出现在 dev 终端, 关掉或滚屏后即丢失, 排查「同步后日志没落」时无处可查。
# 落盘到 data/backend.log 与桌面版 (desktop.py:_setup_logging → desktop.log) 行为对齐,
# 事后可查。桌面版 (frozen) 已由 desktop.py 写 desktop.log, 此处跳过避免重复落盘。
# RotatingFileHandler 防止长期运行/频繁 reload 导致文件无限增长。
if not getattr(sys, "frozen", False):
    try:
        from logging.handlers import RotatingFileHandler

        _log_path = settings.data_dir / "backend.log"
        _log_path.parent.mkdir(parents=True, exist_ok=True)
        _file_handler = RotatingFileHandler(
            _log_path, maxBytes=10 * 1024 * 1024, backupCount=3,
            mode="a", encoding="utf-8", errors="replace",
        )
        _file_handler.setFormatter(
            logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
        )
        logging.getLogger().addHandler(_file_handler)
    except Exception as _e:  # noqa: BLE001
        logger.warning("文件日志初始化失败, 仅输出到终端: %s", _e)


def _start_upstream_addons(app: FastAPI) -> MatrixCachePrewarmOwner:
    """启动 upstream v0.2 新增的服务级装配 (在 bootstrap init_app_state 之后)。

    - MiningJobManager: 恢复中断的挖掘作业, 供 /api/mining/* 使用
    - matrix generation 固定: 避免首批并发 worker 各自创建版本
    - matrix 磁盘缓存预热: enriched refresh 完成后自动后台预热
    """
    repo = app.state.repo
    store = app.state.datastore

    from app.services.mining_manager import MiningJobManager

    mining_manager = MiningJobManager(store.data_dir)
    recovered_mining_runs = mining_manager.recover_interrupted()
    app.state.mining_manager = mining_manager
    if recovered_mining_runs:
        logger.warning("recovered %d interrupted mining runs", recovered_mining_runs)

    # 在接受回测请求前固定 managed generation，避免首批并发 worker 各自创建版本。
    if settings.backtest_matrix_disk_cache_enabled:
        try:
            repo.get_matrix_data_generation("stock")
        except EnrichedGenerationUnavailableError as exc:
            logger.warning("enriched generation requires a full rebuild: %s", exc)

    matrix_prewarm_owner = MatrixCachePrewarmOwner()

    def _schedule_matrix_cache_prewarm() -> None:
        if (
            not settings.backtest_matrix_disk_cache_enabled
            or not settings.backtest_matrix_cache_prewarm
        ):
            return

        def _prewarm() -> None:
            from app.backtest.engine import BacktestEngine
            from app.backtest.matrix import MatrixPrewarmCancelledError
            from app.backtest.strategy import prewarm_matrix_cache
            from app.services.heavy_job_limiter import (
                HeavyJobCancelledError,
                shared_heavy_job_limiter,
            )

            try:
                latest = repo.latest_enriched_date("stock")
                if latest is None:
                    logger.info("matrix cache prewarm skipped: no stock enriched data")
                    return

                with shared_heavy_job_limiter.slot(
                    "normal",
                    cancel_event=matrix_prewarm_owner.cancel_event,
                ):
                    result = prewarm_matrix_cache(
                        BacktestEngine(repo),
                        app.state.strategy_engine,
                        asset_type="stock",
                        latest_date=latest,
                        years=settings.backtest_matrix_cache_prewarm_years,
                        cancel_event=matrix_prewarm_owner.cancel_event,
                    )
                logger.info("matrix cache prewarm done: %s", result)
            except (HeavyJobCancelledError, MatrixPrewarmCancelledError):
                logger.info("matrix cache prewarm cancelled")
            except Exception:  # noqa: BLE001
                logger.exception("matrix cache prewarm failed")

        if not matrix_prewarm_owner.schedule(_prewarm):
            logger.info("matrix cache prewarm already running or shutting down, skip")

    repo._on_refresh_done = _schedule_matrix_cache_prewarm  # noqa: SLF001
    if repo.enriched_ready:
        _schedule_matrix_cache_prewarm()

    # 源码内二次开发启动钩子: 仅暴露稳定只读上下文, 单个扩展失败不影响核心启动。
    extension_registry = getattr(app.state, "extension_registry", None)
    if extension_registry is not None:
        start_backend_extensions(
            current_extension_context(data_dir=store.data_dir, repository=repo),
            extension_registry,
        )

    return matrix_prewarm_owner


def _stop_upstream_addons(app: FastAPI, matrix_prewarm_owner: MatrixCachePrewarmOwner) -> None:
    """关停 upstream v0.2 新增服务 (在 bootstrap shutdown_app_state 之前)。"""
    repo = getattr(app.state, "repo", None)
    if repo is not None:
        repo._on_refresh_done = None  # noqa: SLF001
    if not matrix_prewarm_owner.shutdown(timeout=5.0):
        logger.warning("matrix cache prewarm did not stop within 5 seconds")
    mmanager = getattr(app.state, "mining_manager", None)
    if mmanager:
        mmanager.shutdown()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 单实例进程锁: 同一 data 目录只允许一个后端实例持有 mining/回测写路径。
    mining_process_lock = MiningProcessLock(settings.data_dir)
    mining_process_lock.acquire()
    matrix_prewarm_owner: MatrixCachePrewarmOwner | None = None
    try:
        init_app_state(app)
        matrix_prewarm_owner = _start_upstream_addons(app)
        try:
            yield
        finally:
            if matrix_prewarm_owner is not None:
                _stop_upstream_addons(app, matrix_prewarm_owner)
            shutdown_app_state(app)
    finally:
        mining_process_lock.release()


app = FastAPI(
    title="AthenaQuant",
    version=__version__,
    description="Self-hosted A-share quantitative research platform",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=sorted(_LOCAL_ORIGINS),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ================================================================
# 访问认证中间件 (实现见 app/api/security_middleware.py)
# ================================================================
app.middleware("http")(auth_middleware)


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
# 因子挖掘全链路 (upstream v0.2)
app.include_router(mining.router)
app.include_router(research.router)
# BT-03 竞价策略历史验证只读报告 (POOL-03 零执行)
app.include_router(research_auction.router)
# BT-09 竞价回测结果只读查询 (POOL-03 零执行)
app.include_router(research_backtest.router)
app.include_router(intraday.router)
app.include_router(indices.router)
app.include_router(overview.router)
# 情绪周期/主线识别 (upstream v0.2)
app.include_router(regime.router)
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
app.include_router(signals.router)
app.include_router(monitor_rules.router)
app.include_router(portfolio.router)
app.include_router(decision.router)
app.include_router(research_alpha.router)
app.include_router(research_alpha_sse.router)
app.include_router(research_promotion.router)
app.include_router(research_panels.router)
app.include_router(portfolio_panels.router)
app.include_router(walkforward_sse.router)
app.include_router(alerts.router)
app.include_router(rps.router)
app.include_router(audit.router)
app.include_router(workbench.router)

if phase5_real_host.telemetry_enabled():
    app.include_router(phase5_real_host.router)

install_optional_module_routes(app)

# 二次开发路由与小粒度策略在所有核心路由后注册, 禁止覆盖核心路径。
extension_registry, extension_load_errors = configure_backend_extensions(app)
app.state.extension_registry = extension_registry
app.state.extension_load_errors = extension_load_errors


# 能力门控异常 → 403(而非默认 500)
# 业务代码用 capset.require(Cap.X) 断言能力,缺失时抛 CapabilityDenied;
# 若不注册 handler 会冒泡成 500 Internal Server Error,对前端不友好且语义错误。
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
    def spa_fallback(full_path: str):
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
