# main.py - Application Entry Point

## Overview

`main.py` is the FastAPI application entry point that initializes the Support Chatbot web server. It configures middleware, routes, and serves both API endpoints and static frontend files.

## What This File Does

**Primary Responsibilities:**
1. Initialize FastAPI application
2. Configure CORS for cross-origin requests
3. Implement rate limiting middleware (60 requests/minute per IP)
4. Register API routers (chat, admin, TTS)
5. Serve static frontend files and admin dashboard
6. Provide health check endpoint for monitoring

## Architecture

```
FastAPI App Initialization
├── CORS Middleware (first - allows localhost)
└── Rate Limiting Middleware
    ├── Exempt: /health, /static/*
    ├── Storage: In-memory dict
    └── Response: 429 with retry headers

API Routes
├── /health → Health check endpoint
├── /admin → Admin analytics dashboard
├── /api/v1/chat → Chat endpoints
├── /api/v1/admin → Admin analytics API
└── /api/v1/tts → Text-to-speech

Static Files
├── /static/* → CSS, JS, images
└── /* → Main chat interface (catch-all)
```

## Configuration

### CORS Settings
```python
allow_origins = [
    "http://localhost:8000",
    "http://127.0.0.1:8000"
]
# Production: Add your domain
```

### Rate Limiting
- **Limit**: 60 requests per minute per IP
- **Window**: 60 seconds (sliding window)
- **Storage**: In-memory (lost on restart)
- **Cleanup**: Automatic after 10,000 IPs
- **Headers**: X-RateLimit-Limit, X-RateLimit-Remaining, Retry-After

### Exempt Paths
- `/health` - Health monitoring (no rate limit)
- `/static/*` - Static assets (CSS, JS, images)

## API Endpoints

### Health Check
```http
GET /health
Response: {"status": "healthy", "service": "support-chatbot"}
Use: Load balancer health checks, uptime monitoring
```

### Admin Dashboard
```http
GET /admin
GET /admin/analytics
Response: HTML dashboard page
```

## Rate Limiting Details

### How It Works
1. Extract client IP from request
2. Check request count in current window
3. If over limit → return 429 with retry headers
4. Otherwise → increment counter, allow through

### Storage Schema
```python
rate_limit_storage: Dict[str, Tuple[int, float]] = {
    "192.168.1.1": (45, 1702148400.0),  # (count, window_start_time)
    "10.0.0.5": (12, 1702148420.0)
}
```

### Memory Cleanup
Triggered when storage exceeds 10,000 IPs:
- Removes entries older than 2x window (120 seconds)
- Prevents unbounded memory growth
- Rare in practice (would need 10k unique IPs per day)

## Middleware Execution Order

FastAPI executes middleware in **reverse order** of definition:

```
Request Flow:
1. CORS Middleware (added first)
   ↓
2. Rate Limiting Middleware
   ↓
3. Routes (endpoints)
```

This ensures CORS headers are added to all responses, including 429 rate limit errors.

## Usage Examples

### Starting the Server
```bash
# Development
uvicorn app.main:app --reload --port 8000

# Production
uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4
```

### Testing Rate Limiting
```python
import requests

# Make 65 requests rapidly
for i in range(65):
    response = requests.get("http://localhost:8000/api/v1/trending")
    print(f"Request {i+1}: {response.status_code}")
    if response.status_code == 429:
        print(f"Retry after: {response.headers['Retry-After']} seconds")
```

### Health Check Integration
```yaml
# Docker health check
healthcheck:
  test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
  interval: 30s
  timeout: 3s
  retries: 3
```

## Production Deployment

### Single Server
✅ Ready to deploy as-is

**Pros:**
- No external dependencies
- Simple deployment
- Sufficient for most use cases

**Cons:**
- Rate limit state lost on restart
- No horizontal scaling

### Multi-Server (Load Balanced)
⚠️ Requires modifications

**Issues:**
- In-memory rate limiting won't work (each server tracks separately)
- CORS origins need to be configured for production domain

**Solutions:**
```python
# Option 1: Redis-based rate limiting
# pip install redis
import redis
rate_limit_storage = redis.Redis(host='localhost', port=6379)

# Option 2: Use API Gateway (AWS ALB, Kong, NGINX)
# Remove rate limiting middleware, handle at gateway level

# Option 3: Sticky sessions at load balancer
# Route same IP to same server (preserves rate limit state)
```

## Troubleshooting

### Issue: CORS Errors in Browser
**Symptom**: `Access-Control-Allow-Origin` errors  
**Cause**: Frontend domain not in `allow_origins`  
**Fix**: Add your domain to line 18

### Issue: Rate Limiting Too Aggressive
**Symptom**: Users hitting limit during normal use  
**Cause**: Static files count toward limit, or limit too low  
**Fix**: 
- Increase `RATE_LIMIT_REQUESTS` (line 25)
- Add more paths to exemption (line 35)

### Issue: Memory Growing Over Time
**Symptom**: Increasing memory usage  
**Cause**: Lots of unique IPs, cleanup threshold too high  
**Fix**: Lower cleanup threshold from 10,000 (line 48)

### Issue: 500 Internal Server Error
**Symptom**: Middleware crashes  
**Cause**: Bug in rate limiting logic  
**Fix**: Check logs for traceback, verify cleanup logic at lines 47-56

## Best Practices

### Development
- Keep `allow_origins` as localhost only
- Use `--reload` flag for auto-restart
- Monitor console for errors

### Production
- Add production domain to CORS
- Use HTTPS (TLS)
- Set up health check monitoring
- Consider Redis for rate limiting if scaling
- Set `workers` based on CPU count
- Use environment variables for config

### Security
- Never use `allow_origins=["*"]` in production
- Keep rate limits reasonable (60/min is good default)
- Monitor for abuse via logs
- Implement authentication if needed

## File Dependencies

- **Routers**: `app.api.{chat, admin, tts}`
- **Config**: `app.core.config.settings`
- **Static**: `app/static/` directory
- **External**: FastAPI, Starlette, typing

## Related Documentation

- [docs/app/services/hash_manager.md](./services/hash_manager.md) - Ingestion state tracking
- [FastAPI Middleware Docs](https://fastapi.tiangolo.com/tutorial/middleware/)

