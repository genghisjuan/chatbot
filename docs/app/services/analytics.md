# Analytics Service Documentation

## Overview
The **Analytics Service** (`analytics.py`) is responsible for tracking user interactions, categorizing queries via LLM, and generating "Smart Trends" based on query volume and recency.

## Architecture
- **Database**: Uses SQLAlchemy (sync) with `SessionLocal` for connection management.
- **Concurrency**: Integates with `asyncio` by offloading blocking synchronous DB operations to a thread pool (`loop.run_in_executor`).
- **Caching**: Implements an in-memory cache with `asyncio.Lock` to prevent race conditions during expensive LLM trend generation.

## Key Features
- **Query Logging**: Logs every user message with metadata (tokens, timestamp).
- **Auto-Categorization**: Uses GPT-4o to classify queries into pre-defined support topics (e.g., "Printer Issues", "Network/Connectivity").
- **Smart Trends**: identifying top 5 trending issues using weighted recency scoring and LLM clustering.
- **Feedback & Escalation Tracking**: Records user feedback (up/down vote) and human handoff events.

## API Reference

### `AnalyticsService` Class

#### `log_query(message: str, ...)`
Logs a query.
- *Async Behavior*: "Fire and forget". Schedules the DB write on the event loop's executor to avoid blocking the main thread.

#### `get_trending_topics(hours: int = 720) -> List[dict]`
Returns top trending topics.
- *Cache*: 1-minute TTL.
- *Thread Safety*: Uses `AsyncLock` to ensure only one trend generation calculation runs at a time.

## Usage Examples

```python
from app.services.analytics import AnalyticsService

analytics = AnalyticsService()

# 1. Log a user query (non-blocking)
analytics.log_query(
    message="My printer is broken",
    input_tokens=50,
    output_tokens=150
)

# 2. Get trends (async)
trends = await analytics.get_trending_topics()
for topic in trends:
    print(f"{topic['label']}: {topic['count']}")
```

## Best Practices
1.  **Don't Await Logs**: `log_query`, `log_feedback`, and `log_escalation` are designed to be called without `await` if strictly needed, but internal implementation handles the offloading. 
2.  **Database Connection**: The service manages its own `SessionLocal`. Ensure `settings.DATABASE_URL` is configured.

