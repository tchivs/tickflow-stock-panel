"""FastAPI 入口 — 组装层。

职责边界 (拆分自 955 行单体):
  - ``app/bootstrap.py``   : lifespan 服务初始化/关停编排
  - ``app/api/security_middleware.py`` : 认证/游客/回环放行中间件
  - 本文件                 : FastAPI 实例、CORS、路由注册、异常处理、SPA 静态回退
"""

from __future__ import annotations

import logging
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
    phase5_real_host,
    pipeline,
    pool,
    portfolio,
    portfolio_panels,
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
)
from app.api import analysis as analysis_menus
from app.api import auth as auth_api
from app.api import settings as settings_api
from app.api.routes import router as core_router
from app.api.security_middleware import _LOCAL_ORIGINS, auth_middleware
from app.bootstrap import init_app_state, shutdown_app_state
from app.config import settings
from app.optional_modules import install_optional_module_routes
from app.tickflow.capabilities import CapabilityDenied

logging.basicConfig(
    level=settings.log_level,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_app_state(app)
    yield
    shutdown_app_state(app)


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

if phase5_real_host.telemetry_enabled():
    app.include_router(phase5_real_host.router)

install_optional_module_routes(app)


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
