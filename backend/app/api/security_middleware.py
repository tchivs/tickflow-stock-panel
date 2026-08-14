"""HTTP 访问认证中间件 — 从 ``app.main`` 提取, 行为不变。

承载: 认证白名单、游客只读端点、部署归属回环放行 (未初始化密码时的
SSH/本机访问), 以及主认证流 (cookie 会话 → reviewer_principal)。
注册方式 (main.py)::

    from app.api.security_middleware import auth_middleware
    app.middleware("http")(auth_middleware)
"""

from __future__ import annotations

import ipaddress

from fastapi import Request
from fastapi.responses import JSONResponse

from app.api import auth as auth_api
from app.config import settings

# CORS is deployment-owned: only the loopback app and supported local dev origin
# may read credentialed API responses. Same-origin production requests need no CORS.
_LOCAL_AUTHORITIES = frozenset(
    authority
    for hostname in ("localhost", "127.0.0.1", "[::1]")
    for authority in (hostname, f"{hostname}:{settings.port}", f"{hostname}:5173")
)
_LOCAL_ORIGINS = frozenset(
    f"{scheme}://{authority}" for scheme in ("http", "https") for authority in _LOCAL_AUTHORITIES
)
_LOCAL_REVIEWER_PRINCIPAL = "local_owner_v1"

_AUTH_WHITELIST_PREFIX = ("/api/auth/",)
_AUTH_WHITELIST_EXACT = ("/health", "/api/health", "/openapi.json", "/docs", "/redoc")

# 游客可读路径: 股池页的只读 GET 数据端点 (GUEST-01 / UI-SPEC) + 日期导航 (RQ5 E7)。
# 任何扩宽都会触发 tests/test_guest_masking.py 的守卫 (T-19-03)。
_GUEST_READ_GET_PATHS = frozenset(
    {
        "/api/pool/hub",
        "/api/screener/strategies",
        "/api/pool/dates",
        "/api/pool/history",
        "/api/kline/auction/history",
        "/api/pool/premarket",  # PM-04: 盘前预览对游客只读 (与 hub 同语义, 掩码在前)
    }
)


def is_guest_readable(path: str, method: str) -> bool:
    """游客仅可读股池页数据的只读 GET 端点 (hub/strategies + 日期导航); 其他路径/方法一律不放行。"""
    return method == "GET" and path in _GUEST_READ_GET_PATHS


def is_trusted_unconfigured_request(request: Request) -> bool:
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


async def auth_middleware(request: Request, call_next):
    path = request.url.path
    if not path.startswith("/api/"):
        return await call_next(request)

    from app.services import auth as auth_service

    if not auth_service.is_configured():
        if is_trusted_unconfigured_request(request):
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
    if is_guest_readable(path, request.method):
        return await call_next(request)
    return JSONResponse(status_code=401, content={"detail": "未登录或会话已过期"})
