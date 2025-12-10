# Admin Analytics API Documentation

## Overview

**File**: [`app/api/admin.py`](file:///c:/Users/John/.gemini/antigravity/scratch/support_chatbot/app/api/admin.py)

The Admin Analytics API provides comprehensive endpoints for monitoring and analyzing chatbot performance, user interactions, and operational costs. This module powers the analytics dashboard with real-time statistics, historical trends, feedback analysis, and expense tracking.

---

## Table of Contents

1. [Summary](#summary)
2. [Architecture](#architecture)
3. [Endpoints](#endpoints)
   - [GET /summary](#get-summary)
   - [GET /messages-trend](#get-messages-trend)
   - [GET /feedback](#get-feedback)
   - [GET /feedback-trend](#get-feedback-trend)
   - [GET /feedback/export](#get-feedbackexport)
   - [GET /top-categories](#get-top-categories)
   - [GET /spend](#get-spend)
   - [POST /expenses](#post-expenses)
4. [Data Models](#data-models)
5. [Security & Validation](#security--validation)
6. [Best Practices](#best-practices)

---

## Summary

This module implements **8 RESTful API endpoints** for analytics, divided into four functional areas:

| Area | Endpoints | Purpose |
|------|-----------|---------|
| **Dashboard Stats** | `/summary` | Real-time KPIs (messages, feedback, escalations) |
| **Trend Analysis** | `/messages-trend`, `/feedback-trend` | Time-series data with multiple granularities |
| **Feedback Management** | `/feedback`, `/feedback/export` | User feedback retrieval and CSV export |
| **Cost Tracking** | `/top-categories`, `/spend`, `/expenses` | Query categorization and expense monitoring |

**Key Features**:
- ✅ UTC timezone standardization
- ✅ Comprehensive input validation
- ✅ Dependency injection for database sessions
- ✅ Security hardening (path traversal prevention)
- ✅ Flexible time ranges and granularities

---

## Architecture

### Database Connection

```python
engine = create_engine(settings.DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
```

Uses SQLAlchemy with a session factory pattern. All endpoints use dependency injection via `get_db()` to ensure proper session lifecycle management.

### Dependency Injection

```python
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
```

Ensures database connections are always closed, even if exceptions occur.

### Data Models

The module interacts with five primary database tables:
- **QueryLog**: User queries and chatbot responses
- **FeedbackLog**: User feedback ratings (up/down)
- **EscalationLog**: Cases escalated to human agents
- **ExpenseLog**: Manual expense entries
- **Base**: SQLAlchemy declarative base

---

## Endpoints

### GET /summary

**Purpose**: Provides dashboard overview statistics for today, this week, and this month.

**Parameters**: None

**Response**:
```json
{
  "messages_today": 45,
  "messages_week": 312,
  "messages_month": 1205,
  "positive_feedback_score": 87.5,
  "negative_feedback_score": 12.5,
  "total_feedback": 128,
  "positive_count": 112,
  "negative_count": 16,
  "containment_rate": 94.2,
  "fallback_rate": 8.3,
  "total_escalations": 18
}
```

**Key Metrics**:
- **Messages**: Counted by day/week/month using UTC timestamps
- **Feedback Score**: Percentage of up vs down votes
- **Containment Rate**: `(total_sessions - escalations) / total_sessions × 100`
- **Fallback Rate**: Percentage of queries that triggered fallback responses

**Special Handling**:
- Logs a warning if escalations exist without corresponding sessions (data integrity issue)
- Returns 100% containment if no sessions exist and no escalations

**Implementation Notes**:
- Uses SQLite's `func.date()` for date-only comparisons
- String-based timestamp comparisons for week/month calculations
- All calculations use UTC timezone

---

### GET /messages-trend

**Purpose**: Returns time-series data of message counts for trend visualization.

**Parameters**:
| Parameter | Type | Default | Validation | Description |
|-----------|------|---------|------------|-------------|
| `days` | int | 7 | 1-365 | Number of days to include |
| `start_date` | str | null | ISO format | Custom range start (YYYY-MM-DD) |
| `end_date` | str | null | ISO format | Custom range end (YYYY-MM-DD) |
| `granularity` | str | "day" | Enum | Time bucket size |
| `db` | Session | - | Injected | Database session |

**Valid Granularities**: `15min`, `minute`, `hour`, `day`, `month`

**Response**:
```json
{
  "trend": [
    {"date": "2024-12-01", "count": 42},
    {"date": "2024-12-02", "count": 38},
    {"date": "2024-12-03", "count": 51}
  ]
}
```

**Behavior**:
- **Custom Range**: Uses `start_date` and `end_date` if both provided
- **Default Range**: Last N days from today (UTC)
- **15-minute Buckets**: Uses SQLite's `printf` for safe string formatting
- **Empty Buckets**: Included in response with `count: 0` for continuous visualization

**Example Usage**:
```bash
# Last 30 days by day
GET /messages-trend?days=30

# Custom range by hour
GET /messages-trend?start_date=2024-12-01&end_date=2024-12-07&granularity=hour
```

---

### GET /feedback

**Purpose**: Retrieves paginated list of user feedback entries with optional filtering.

**Parameters**:
| Parameter | Type | Default | Validation | Description |
|-----------|------|---------|------------|-------------|
| `rating` | str | null | `up` or `down` | Filter by rating |
| `period` | str | null | `day`, `week`, `month` | Preset time period |
| `start_date` | str | null | ISO format | Custom range start |
| `end_date` | str | null | ISO format | Custom range end |
| `limit` | int | 100 | 1-1000 | Maximum results |
| `db` | Session | - | Injected | Database session |

**Response**:
```json
{
  "feedback": [
    {
      "id": 1,
      "timestamp": "2024-12-08T18:30:00+00:00",
      "user_query": "How do I reset my password?",
      "bot_response": "You can reset your password by...",
      "rating": "up"
    }
  ]
}
```

**Filtering Logic**:
1. If `start_date` and `end_date` provided → custom range
2. Else if `period` provided → preset period (day/week/month)
3. Else → all feedback (limited by `limit`)

**Implementation Notes**:
- Timestamps converted to UTC with timezone info for ISO format
- Results ordered by most recent first
- Null-safe: returns empty strings for missing fields

---

### GET /feedback-trend

**Purpose**: Returns time-series data of positive/negative feedback counts.

**Parameters**: Same as `/messages-trend`

**Response**:
```json
{
  "trend": [
    {"date": "2024-12-01", "up": 35, "down": 5},
    {"date": "2024-12-02", "up": 42, "down": 3}
  ],
  "baseline_up": 142,
  "baseline_down": 18
}
```

**Baseline Calculation**:
- Counts all feedback **before** `start_dt`
- Prevents misleading 0% satisfaction at chart start
- Used by frontend to show historical context

**Use Cases**:
- Sentiment analysis over time
- Identifying periods of poor user experience
- A/B testing result visualization

---

### GET /feedback/export

**Purpose**: Exports feedback data as downloadable CSV file.

**Parameters**: Same filtering as `/feedback` endpoint

**Response**:
- **Content-Type**: `text/csv`
- **Filename**: `feedback_{period}_{rating}.csv`

**CSV Format**:
```csv
Timestamp,User Query,Bot Response,Rating
2024-12-08T18:30:00+00:00,"How do I reset?","You can reset by...","up"
```

**Security**:
- Filename sanitization prevents path traversal attacks
- Replaces `/`, `\`, and `..` with underscores
- Example: `../../etc/passwd` → `feedback_.._.._.._etc_passwd_all.csv`

**Implementation Notes**:
- Uses Python's `csv.writer` for proper escaping
- Handles null values gracefully
- Memory-efficient for large exports (streaming)

---

### GET /top-categories

**Purpose**: Returns most common query categories for analysis.

**Parameters**:
| Parameter | Type | Default | Validation | Description |
|-----------|------|---------|------------|-------------|
| `days` | int | 7 | 1-365 | Time window |
| `limit` | int | 10 | 1-100 | Max categories |
| `db` | Session | - | Injected | Database session |

**Response**:
```json
{
  "categories": [
    {"category": "Account Issues", "count": 145},
    {"category": "Billing Questions", "count": 89},
    {"category": "Technical Support", "count": 67}
  ]
}
```

**Use Cases**:
- Identifying common user pain points
- Training data gap analysis
- Resource allocation planning

---

### GET /spend

**Purpose**: Calculates OpenAI API costs and token usage across time periods.

**Parameters**: None

**Response**:
```json
{
  "today": {
    "input_tokens": 15420,
    "output_tokens": 8930,
    "embedding_tokens": 2340,
    "total_tokens": 26690,
    "chat_cost": 0.007659,
    "embedding_cost": 0.000047,
    "misc_cost": 0.000000,
    "cost": 0.007706,
    "query_count": 45
  },
  "week": { /* ... */ },
  "month": { /* ... */ },
  "all_time": { /* ... */ },
  "avg_cost_per_query": 0.000171,
  "pricing": {
    "input_per_1m": 0.15,
    "output_per_1m": 0.60,
    "embedding_per_1m": 0.02,
    "model": "gpt-4o-mini + text-embedding-3-small"
  }
}
```

**Pricing Model** (as of Dec 2024):
- **Input tokens**: $0.15 per 1M tokens
- **Output tokens**: $0.60 per 1M tokens
- **Embeddings**: $0.02 per 1M tokens (text-embedding-3-small)

**Cost Calculation**:
```python
total_cost = (input_tokens × 0.00000015) + 
             (output_tokens × 0.0000006) + 
             (embedding_tokens × 0.00000002) + 
             misc_expenses
```

**Implementation Notes**:
- All costs rounded to 6 decimals for precision
- `misc_cost` includes manual expenses from `ExpenseLog`
- Prevents division by zero when calculating averages

---

### POST /expenses

**Purpose**: Adds manual expense entries for non-API costs.

**Request Body**:
```json
{
  "category": "Infrastructure",
  "description": "AWS hosting costs",
  "amount": 125.50,
  "date": "2024-12-01"
}
```

**Validation**:
- `category`: 1-100 characters, required
- `description`: 1-500 characters, required
- `amount`: Must be positive, max $1,000,000
- `date`: Optional, must match `YYYY-MM-DD` format

**Response**:
```json
{"status": "success"}
```

**Error Responses**:
- **400**: Invalid date format
- **422**: Validation error (negative amount, too long description, etc.)

**Use Cases**:
- Tracking hosting costs
- Recording third-party service fees
- Manual expense adjustments

---

## Data Models

### ExpenseCreate (Pydantic)

```python
class ExpenseCreate(BaseModel):
    category: str = Field(..., min_length=1, max_length=100)
    description: str = Field(..., min_length=1, max_length=500)
    amount: float = Field(..., gt=0, le=1000000)
    date: Optional[str] = Field(None, pattern=r'^\d{4}-\d{2}-\d{2}$')
```

**Validation Rules**:
- All fields except `date` are required
- `amount` must be positive and ≤ $1M
- `date` must be valid ISO date string
- FastAPI automatically returns 422 for validation failures

---

## Security & Validation

### Input Validation

All endpoints use FastAPI's `Query` parameter validation:

```python
days: int = Query(default=7, ge=1, le=365)
rating: Optional[str] = Query(default=None, pattern="^(up|down)$")
```

**Benefits**:
- ✅ Prevents DoS attacks with extreme values
- ✅ Auto-generated API documentation
- ✅ Clear 422 validation errors
- ✅ Type safety

### Security Measures

1. **Path Traversal Prevention**:
   ```python
   safe_period = (period or 'all').replace('/', '_').replace('\\', '_').replace('..', '_')
   ```

2. **SQL Injection Prevention**: Uses SQLAlchemy ORM (parameterized queries)

3. **Error Handling**: Specific exceptions with sanitized error messages

4. **Rate Limiting**: Limit parameters cap result sizes

---

## Best Practices

### Timezone Handling

**Always use UTC**:
```python
now = datetime.now(timezone.utc).replace(tzinfo=None)  # Naive UTC
```

**Why naive UTC?**
- SQLite stores timestamps as strings without timezone info
- Naive datetimes prevent timezone conversion bugs
- All comparisons consistent

### Database Sessions

**Use dependency injection**:
```python
async def my_endpoint(db = Depends(get_db)):
    # db automatically closed after request
```

**Don't manually manage sessions**:
```python
# ❌ BAD
db = SessionLocal()
try:
    # ...
finally:
    db.close()

# ✅ GOOD
async def endpoint(db = Depends(get_db)):
    # ...
```

### Error Handling

**Use specific exceptions**:
```python
try:
    start_dt = datetime.fromisoformat(start_date).date()
except ValueError as e:
    raise HTTPException(status_code=400, detail=f"Invalid date format: {e}")
```

**Don't use bare except**:
```python
# ❌ BAD
try:
    parse_date()
except:
    pass  # Silently fails, impossible to debug

# ✅ GOOD
except ValueError as e:
    raise HTTPException(status_code=400, detail=str(e))
```

---

## Common Usage Examples

### Dashboard Summary
```bash
curl https://api.example.com/admin/summary
```

### Last 7 Days Trend
```bash
curl https://api.example.com/admin/messages-trend?days=7&granularity=day
```

### Export Negative Feedback from This Month
```bash
curl "https://api.example.com/admin/feedback/export?rating=down&period=month" \
  -o feedback.csv
```

### Add Manual Expense
```bash
curl -X POST https://api.example.com/admin/expenses \
  -H "Content-Type: application/json" \
  -d '{
    "category": "Infrastructure",
    "description": "AWS costs",
    "amount": 125.50,
    "date": "2024-12-01"
  }'
```

---

## Troubleshooting

### Issue: Wrong timezone in results
**Solution**: Ensure all timestamps stored in UTC. Check `QueryLog.timestamp` values.

### Issue: Validation errors on valid input
**Solution**: Check query parameter patterns. Rating must be exactly "up" or "down", period must be "day", "week", or "month".

### Issue: CSV export filename sanitization too aggressive
**Solution**: This is intentional for security. Use alphanumeric characters in period/rating parameters.

### Issue: Division by zero in containment rate
**Solution**: Code already handles this - returns 100% if no sessions and no escalations.

---

## Performance Considerations

- **Pagination**: Always use `limit` parameter on `/feedback` endpoint
- **Date Ranges**: Narrow time ranges for faster queries
- **Granularity**: Minute-level granularity can be slow for long periods
- **Indexing**: Ensure `timestamp` columns are indexed in database

---

## Future Improvements

Potential enhancements:
1. **Caching**: Redis cache for summary stats (5-minute TTL)
2. **Aggregation Tables**: Pre-computed daily/monthly aggregates
3. **Async Queries**: Parallel database queries for spend endpoint
4. **Export Formats**: JSON, Excel support in addition to CSV
5. **Real-time Updates**: WebSocket for live dashboard updates

---

## Related Documentation

- [Database Schema](./database_schema.md)
- [Analytics Service](./analytics_service.md)
- [API Authentication](./authentication.md)
- [Deployment Guide](./deployment.md)

