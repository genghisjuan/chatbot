from __future__ import annotations

import time
from collections import defaultdict
from typing import Callable, Dict, Tuple

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from app.api.admin import router as admin_router
from app.api.chat import router as chat_router
from app.api.tts import router as tts_router
from app.core.config import settings
from app.services.analytics import AnalyticsService

# -----------------------------------------------------------------------------
# App configuration
# -----------------------------------------------------------------------------

_DOCS_PATHS = {"/health", "/docs", "/redoc", "/openapi.json"}
_STATIC_PREFIX = "/static/"
_FAVICON_PATH = "app/static/favicon.png"
_INDEX_PATH = "app/static/index.html"

# Disable API docs in production (only show on localhost)
# NOTE: Preserves existing behavior (string containment check on settings.ALLOWED_ORIGINS)
is_localhost = (
    "localhost" in settings.ALLOWED_ORIGINS or "127.0.0.1" in settings.ALLOWED_ORIGINS
)

app = FastAPI(
    title="Support Chatbot",
    version="1.0.0",
    docs_url="/docs" if is_localhost else None,
    redoc_url="/redoc" if is_localhost else None,
)


@app.on_event("startup")
async def startup_event() -> None:
    """Initialize analytics service and create database tables."""
    try:
        # Triggers AnalyticsService.__init__() which calls _init_db()
        _ = AnalyticsService()
    except Exception as e:
        # Preserve current behavior: print warning to stdout
        print(f"Warning: Failed to initialize analytics database: {e}")


# -----------------------------------------------------------------------------
# Middleware
# -----------------------------------------------------------------------------

# CORS Middleware - Must be added before other middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS.split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# SECURITY: Request Body Size Limit
MAX_REQUEST_BODY_SIZE = 15 * 1024 * 1024  # 15MB (allows 10MB file + form data overhead)


def _max_body_mb() -> int:
    return MAX_REQUEST_BODY_SIZE // (1024 * 1024)


def _should_skip_body_limit(request: Request) -> bool:
    if request.method in ("GET", "HEAD", "OPTIONS"):
        return True
    return request.url.path in _DOCS_PATHS


@app.middleware("http")
async def limit_request_body_size(request: Request, call_next):
    """
    Enforce request body size limit by tracking actual bytes read.

    This is more robust than header-only checks because:
    - Browsers may not send Content-Length for chunked/multipart uploads
    - Headers can be spoofed or inaccurate
    - We track actual memory consumption
    """
   
    if _should_skip_body_limit(request):
        return await call_next(request)

    # First check: Content-Length header (fast path)
    content_length = request.headers.get("content-length")
    if content_length and int(content_length) > MAX_REQUEST_BODY_SIZE:
        return JSONResponse(
            status_code=413,
            content={"detail": f"Request body too large (max {_max_body_mb()}MB)"},
        )

    # Second check: Track actual bytes as they're read (defense in depth)
    original_receive = request._receive  # type: ignore[attr-defined]
    bytes_received = 0

    async def size_limited_receive():
        nonlocal bytes_received
        message = await original_receive()

        if message["type"] == "http.request":
            body_chunk = message.get("body", b"")
            bytes_received += len(body_chunk)

            if bytes_received > MAX_REQUEST_BODY_SIZE:
                raise HTTPException(
                    status_code=413,
                    detail=f"Request body too large (max {_max_body_mb()}MB)",
                )

        return message

    request._receive = size_limited_receive  # type: ignore[attr-defined]

    try:
        return await call_next(request)
    except HTTPException as e:
        if e.status_code == 413:
            return JSONResponse(status_code=413, content={"detail": e.detail})
        raise


# Simple in-memory rate limiting (requests per minute)
RATE_LIMIT_REQUESTS = 60  # Max requests per minute per IP
RATE_LIMIT_WINDOW = 60  # Window in seconds

# Storage: IP -> (request_count, window_start_time)
rate_limit_storage: Dict[str, Tuple[int, float]] = defaultdict(lambda: (0, 0.0))


def _should_skip_rate_limit(request: Request) -> bool:
    return request.url.path == "/health" or request.url.path.startswith(_STATIC_PREFIX)


def _cleanup_rate_limit_storage(now: float) -> None:
    """Remove old IP entries to prevent memory leak (preserves existing behavior)."""
    if len(rate_limit_storage) <= 10000:
        return

    cutoff = now - (RATE_LIMIT_WINDOW * 2)
    cleaned = {
        ip: (count, window_start)
        for ip, (count, window_start) in rate_limit_storage.items()
        if window_start > cutoff
    }
    rate_limit_storage.clear()
    rate_limit_storage.update(cleaned)


@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    """Simple rate limiting - 60 requests per minute per IP."""
    if _should_skip_rate_limit(request):
        return await call_next(request)

    client_ip = request.client.host if request.client else "unknown"
    now = time.time()

    count, window_start = rate_limit_storage[client_ip]

    # Reset window if expired
    if now - window_start > RATE_LIMIT_WINDOW:
        count = 0
        window_start = now
        _cleanup_rate_limit_storage(now)

    # Check limit - return 429 with rate limit headers
    if count >= RATE_LIMIT_REQUESTS:
        retry_after = int(RATE_LIMIT_WINDOW - (now - window_start))
        return JSONResponse(
            status_code=429,
            content={"detail": "Rate limit exceeded. Please try again later."},
            headers={
                "X-RateLimit-Limit": str(RATE_LIMIT_REQUESTS),
                "X-RateLimit-Remaining": "0",
                "Retry-After": str(retry_after),
            },
        )

    rate_limit_storage[client_ip] = (count + 1, window_start)
    return await call_next(request)


# -----------------------------------------------------------------------------
# Routes
# -----------------------------------------------------------------------------

@app.get("/health", tags=["Health"])
async def health_check() -> Dict[str, str]:
    """Returns 200 OK if service is running."""
    return {"status": "healthy", "service": "support-chatbot"}


@app.get("/favicon.ico", include_in_schema=False)
async def favicon() -> FileResponse:
    return FileResponse(_FAVICON_PATH)


@app.get("/admin", include_in_schema=False)
@app.get("/admin/analytics", include_in_schema=False)
async def admin_page() -> FileResponse:
    return FileResponse("app/static/admin/index.html")


@app.get("/m", include_in_schema=False)
async def mobile_page() -> FileResponse:
    return FileResponse("app/static/mobile/index.html")


@app.get("/deal", include_in_schema=False)
async def deal_page() -> FileResponse:
    return FileResponse("app/static/deal/index.html")


# API Routers
app.include_router(admin_router, prefix="/api/v1/admin", tags=["Admin"])
app.include_router(chat_router, prefix="/api/v1", tags=["Chat"])
app.include_router(tts_router, prefix="/api/v1", tags=["TTS"])

# Mount static files
app.mount("/static", StaticFiles(directory="app/static"), name="static_assets")


@app.get("/", include_in_schema=False)
async def root_page(request: Request):
    """Serve desktop or redirect to mobile based on user-agent."""
    user_agent = request.headers.get("user-agent", "").lower()

    is_mobile = any(
        keyword in user_agent
        for keyword in (
            "mobile",
            "android",
            "iphone",
            "ipad",
            "ipod",
            "blackberry",
            "windows phone",
            "webos",
        )
    )

    if is_mobile:
        return RedirectResponse(url="/m", status_code=302)

    return FileResponse(_INDEX_PATH)
