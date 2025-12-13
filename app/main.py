from fastapi import FastAPI, Request, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse, RedirectResponse
from app.api.admin import router as admin_router
from app.api.chat import router as chat_router
from app.api.tts import router as tts_router
from app.core.config import settings
from app.services.analytics import AnalyticsService
import time
from collections import defaultdict
from typing import Dict, Tuple, Any

# Disable API docs in production (only show on localhost)
is_localhost = "localhost" in settings.ALLOWED_ORIGINS or "127.0.0.1" in settings.ALLOWED_ORIGINS

app = FastAPI(
    title="Support Chatbot",
    version="1.0.0",
    docs_url="/docs" if is_localhost else None,  # Disable Swagger UI in production
    redoc_url="/redoc" if is_localhost else None  # Disable ReDoc in production
)

# Initialize database on startup
@app.on_event("startup")
async def startup_event():
    """Initialize analytics service and create database tables"""
    try:
        # This will trigger AnalyticsService.__init__() which calls _init_db()
        _ = AnalyticsService()
    except Exception as e:
        print(f"Warning: Failed to initialize analytics database: {e}")


# CORS Middleware - Must be added before other middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS.split(","),  # Load from environment config
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Simple in-memory rate limiting (requests per minute)
RATE_LIMIT_REQUESTS = 60  # Max requests per minute per IP
RATE_LIMIT_WINDOW = 60  # Window in seconds

# Storage: IP -> (request_count, window_start_time)
rate_limit_storage: Dict[str, Tuple[int, float]] = defaultdict(lambda: (0, 0.0))

@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    """Simple rate limiting - 60 requests per minute per IP"""
    # Skip rate limiting for health check and static assets
    if request.url.path == "/health" or request.url.path.startswith("/static/"):
        return await call_next(request)
    
    client_ip = request.client.host if request.client else "unknown"
    current_time = time.time()
    
    count, window_start = rate_limit_storage[client_ip]
    
    # Reset window if expired
    if current_time - window_start > RATE_LIMIT_WINDOW:
        count = 0
        window_start = current_time
        # Cleanup: Remove old IP entries to prevent memory leak
        if len(rate_limit_storage) > 10000:
            cutoff = current_time - (RATE_LIMIT_WINDOW * 2)
            # Build new dict BEFORE clearing to avoid losing data
            cleaned = {
                ip: (c, w) for ip, (c, w) in rate_limit_storage.items()
                if w > cutoff
            }
            rate_limit_storage.clear()
            rate_limit_storage.update(cleaned)
    
    # Check limit - return 429 with rate limit headers
    if count >= RATE_LIMIT_REQUESTS:
        retry_after = int(RATE_LIMIT_WINDOW - (current_time - window_start))
        return JSONResponse(
            status_code=429,
            content={"detail": "Rate limit exceeded. Please try again later."},
            headers={
                "X-RateLimit-Limit": str(RATE_LIMIT_REQUESTS),
                "X-RateLimit-Remaining": "0",
                "Retry-After": str(retry_after)
            }
        )
    
    # Increment counter
    rate_limit_storage[client_ip] = (count + 1, window_start)
    
    return await call_next(request)



# Health check endpoint for monitoring
@app.get("/health", tags=["Health"])
async def health_check() -> Dict[str, str]:
    """Returns 200 OK if service is running"""
    return {"status": "healthy", "service": "support-chatbot"}

@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    return FileResponse("app/static/favicon.png")

# Helper to serve admin page
@app.get("/admin", include_in_schema=False)
@app.get("/admin/analytics", include_in_schema=False)
async def admin_page() -> FileResponse:
    return FileResponse("app/static/admin/index.html")

# Helper to serve mobile page
@app.get("/m", include_in_schema=False)
async def mobile_page() -> FileResponse:
    return FileResponse("app/static/mobile/index.html")

# CORS already added above (before rate limiting middleware)

# API Routers
app.include_router(admin_router, prefix="/api/v1/admin", tags=["Admin"])
app.include_router(chat_router, prefix="/api/v1", tags=["Chat"])
app.include_router(tts_router, prefix="/api/v1", tags=["TTS"])

# Mount static files
app.mount("/static", StaticFiles(directory="app/static"), name="static_assets")

# Root handler with mobile detection
@app.get("/", include_in_schema=False)
async def root_page(request: Request):
    """Serve desktop or redirect to mobile based on user-agent"""
    user_agent = request.headers.get("user-agent", "").lower()
    
    # Check for mobile devices
    is_mobile = any(keyword in user_agent for keyword in [
        "mobile", "android", "iphone", "ipad", "ipod",
        "blackberry", "windows phone", "webos"
    ])
    
    if is_mobile:
        return RedirectResponse(url="/m", status_code=302)
    else:
        return FileResponse("app/static/index.html")
