"""
Admin Analytics API Endpoints.

Provides data for the analytics dashboard including:
- Summary statistics
- Time-series data
- Feedback analysis
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import create_engine, func, desc, case, Integer
from sqlalchemy.orm import sessionmaker
from datetime import datetime, timedelta, timezone, date
from typing import Optional
from app.core.config import settings
from app.services.analytics import QueryLog, FeedbackLog, Base, EscalationLog, ExpenseLog
import logging
from pydantic import BaseModel, Field

router = APIRouter()
logger = logging.getLogger(__name__)

# ... (database connection code remains same) ...

@router.get("/messages-trend")
async def get_messages_trend(
    days: int = Query(default=7, ge=0, le=365), 
    start_date: Optional[str] = None, 
    end_date: Optional[str] = None,
    granularity: str = Query(default="day", pattern="^(15min|minute|hour|day|month)$"),
    timezone_offset: int = Query(default=0, description="User's timezone offset from UTC in minutes (e.g., -300 for EST)"),
    db = Depends(get_db)
):
    """Get daily or hourly message counts for trend chart."""
    results = []
    
    # helper to convert local date to UTC datetime range
    def get_utc_range_from_local_date(d_start: date, d_end: date, tz_offset: int):
        # Offset calculation:
        # Frontend sends NEGATIVE for timezones behind UTC (e.g., EST = -300)
        # We need to SUBTRACT this negative offset (add positive) to go Local -> UTC
        offset_hours = -tz_offset // 60
        offset_minutes = -tz_offset % 60
        
        start_naive = datetime.combine(d_start, datetime.min.time())
        end_naive = datetime.combine(d_end, datetime.min.time())
        
        utc_start = start_naive + timedelta(hours=offset_hours, minutes=offset_minutes)
        utc_end = end_naive + timedelta(hours=offset_hours, minutes=offset_minutes)
        return utc_start, utc_end

    # 1. Determine local date range
    start_dt_utc = None
    end_dt_utc = None

    if start_date and end_date:
        # Custom range
        try:
            s_local = datetime.strptime(start_date, '%Y-%m-%d').date()
            e_local = datetime.strptime(end_date, '%Y-%m-%d').date()
            start_dt_utc, end_dt_utc = get_utc_range_from_local_date(s_local, e_local, timezone_offset)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=f"Invalid date format: {e}")
    else:
        # Last N Days
        # Treat "now" as user's current local time, then back N days
        # We approximate by taking UTC now, applying offset to get User Local Now
        # Then rounding to date, then converting back to UTC range
        # Actually simplest: "Last N Days" usually means "last N 24-hour periods" or "N calendar days ending today"
        
        # We'll stick to "N calendar days relative to user's local time"
        now_utc = datetime.now(timezone.utc).replace(tzinfo=None)
        
        # Convert UTC now -> User Local Now
        # User Local = UTC + offset (Wait, offset is minutes BEHIND UTC, so + (-300) = -300)
        # Actually frontend sends -300 for EST. 
        # So User Local = UTC + (offset_minutes)
        # Let's use the same offset logic as above but reversed
        
        # Actually, let's keep it simple:
        # We want the User's "End Date" (Today).
        # We can just iterate backwards from "User Today".
        # But we don't know User Today exactly without full datetime.
        # However, we can approximate by shifting UTC now by offset.
        
        user_offset_delta = timedelta(minutes=timezone_offset)
        now_user_local = now_utc + user_offset_delta
        today_user_local = now_user_local.date()
        
        start_date_local = today_user_local - timedelta(days=days-1)
        end_date_local = today_user_local
        
        start_dt_utc, end_dt_utc = get_utc_range_from_local_date(start_date_local, end_date_local, timezone_offset)

    # Note: end_dt_utc here represents the START of the last day (00:00).
    # For filtering, we need to cover the full end day.
    # But wait, get_messages_trend logic typically treats end_dt as inclusive for date filters,
    # but for hourly it needs explicit range.
    
    start_dt = start_dt_utc
    # Ensure end_dt covers the whole day (23:59:59)
    end_dt = end_dt_utc # This is 00:00 of the end day
    
    # Generate Data
    if granularity == "15min":
        end_full = end_dt + timedelta(hours=23, minutes=59, seconds=59)
        # Use printf for safe concatenation in SQLite; Force integer division
        bucket = func.printf('%s%02d', func.strftime('%Y-%m-%d %H:', QueryLog.timestamp), func.cast(func.cast(func.strftime('%M', QueryLog.timestamp), Integer) / 15, Integer) * 15)
        
        logs = db.query(
            bucket.label('minute'),
            func.count(QueryLog.id).label('count')
        ).filter(QueryLog.timestamp >= start_dt, QueryLog.timestamp <= end_full).group_by('minute').all()
        
        results = [{"date": log.minute, "count": log.count} for log in logs]
        return {"trend": results}

    if granularity == "minute":
        # Minute-by-minute in last 6 hours (Special Override) - keeps original logic?
        # The original logic used hardcoded "Last 6 hours".
        # If user asked for granularity=minute, we probably should respect that override.
        # usage: loadTrend(1) -> granularity=hour.
        # when is minute used? Maybe specific drill down.
        # Let's keep original logic for consistency but import date fixed it.
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        start_dt_full = now - timedelta(hours=6)
        end_full = now

        logs = db.query(
            func.strftime('%Y-%m-%d %H:%M', QueryLog.timestamp).label('minute'),
            func.count(QueryLog.id).label('count')
        ).filter(QueryLog.timestamp >= start_dt_full, QueryLog.timestamp <= end_full).group_by('minute').all()
        
        results = [{"date": log.minute, "count": log.count} for log in logs]
        return {"trend": results}

    if granularity == "hour":
        # Hourly Buckets
        # start_dt and end_dt are already UTC datetimes starting at 00:00 user local time
        current = start_dt
        end_full = end_dt + timedelta(hours=23, minutes=59, seconds=59)
        
        while current <= end_full:
            # Get next hour boundary
            next_hour = current + timedelta(hours=1)
            
            # Count messages in this hour using timestamp range (works on both SQLite and PostgreSQL)
            count = db.query(func.count(QueryLog.id)).filter(
                QueryLog.timestamp >= current,
                QueryLog.timestamp < next_hour
            ).scalar() or 0
            
            results.append({
                "date": current.strftime('%Y-%m-%dT%H:%M:%S'),
                "count": count
            })
            current = next_hour
    
    elif granularity == "month":
        # Monthly Buckets - PostgreSQL compatible
        current = start_dt.replace(day=1)
        end_curr = end_dt.replace(day=1)
        
        while current <= end_curr:
            # Calculate start and end of this month
            if current.month == 12:
                next_month = current.replace(year=current.year + 1, month=1, day=1)
            else:
                next_month = current.replace(month=current.month + 1, day=1)
            
            # Count using timestamp range (PostgreSQL compatible)
            count = db.query(func.count(QueryLog.id)).filter(
                QueryLog.timestamp >= current,
                QueryLog.timestamp < next_month
            ).scalar() or 0
            
            results.append({
                "date": current.strftime('%Y-%m'),
                "count": count
            })
            current = next_month
    else:
        # Daily Buckets
        current = start_dt
        while current <= end_dt:
            # Count (UTC timestamps)
            count = db.query(func.count(QueryLog.id)).filter(
                func.date(QueryLog.timestamp) == current
            ).scalar() or 0
            
            results.append({
                "date": current.isoformat(),
                "count": count
            })
            current += timedelta(days=1)
    
    return {"trend": results}


@router.get("/feedback")
async def get_feedback_list(
    rating: Optional[str] = Query(default=None, pattern="^(up|down)$"), 
    period: Optional[str] = Query(default=None, pattern="^(day|week|month)$"), 
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    limit: int = Query(default=100, ge=1, le=1000),
    db = Depends(get_db)
):
    """Get recent feedback with optional filter by rating and time period."""
    query = db.query(FeedbackLog).order_by(desc(FeedbackLog.timestamp))
    
    if rating:
        query = query.filter(FeedbackLog.rating == rating)
        
    # Custom date range filter
    if start_date and end_date:
        try:
            start = datetime.fromisoformat(start_date)
            end = datetime.fromisoformat(end_date).replace(hour=23, minute=59, second=59)
            query = query.filter(FeedbackLog.timestamp >= start, FeedbackLog.timestamp <= end)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=f"Invalid date format: {e}")
    # Preset period filter
    elif period:
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        if period == 'day':
            start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        elif period == 'week':
            days_since_monday = now.weekday()
            start = (now - timedelta(days=days_since_monday)).replace(hour=0, minute=0, second=0, microsecond=0)
        elif period == 'month':
            start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        else:
            start = None
        
        if start:
            query = query.filter(FeedbackLog.timestamp >= start)
    
    results = query.limit(limit).all()
    
    return {
        "feedback": [
            {
                "id": f.id,
                "timestamp": f.timestamp.replace(tzinfo=timezone.utc).isoformat() if f.timestamp else None,
                "user_query": f.user_query,
                "bot_response": f.bot_response,
                "rating": f.rating
            }
            for f in results
        ]
    }


@router.get("/feedback-trend")
async def get_feedback_trend(
    days: int = Query(default=7, ge=0, le=365), 
    start_date: Optional[str] = None, 
    end_date: Optional[str] = None,
    granularity: str = Query(default="day", pattern="^(15min|minute|hour|day|month)$"),
    timezone_offset: int = Query(default=0, description="User's timezone offset from UTC in minutes (e.g., -300 for EST)"),
    db = Depends(get_db)
):
    """Get daily or hourly feedback stats (up/down)."""
    results = []
    
    # Custom Date Range (Priority)
    if start_date and end_date:
        try:
            # Parse as naive dates, then adjust for user's timezone
            start_dt_naive = datetime.strptime(start_date, '%Y-%m-%d')
            end_dt_naive = datetime.strptime(end_date, '%Y-%m-%d')
            
            # Apply timezone offset: user's midnight in their TZ = offset minutes later in UTC
            offset_delta = timedelta(minutes=-timezone_offset)
            start_dt = start_dt_naive - offset_delta
            end_dt = end_dt_naive - offset_delta
        except ValueError as e:
            raise HTTPException(status_code=400, detail=f"Invalid date format: {e}")
    else:
        now_utc = datetime.now(timezone.utc).replace(tzinfo=None)
        end_dt = now_utc.date()
        start_dt = end_dt - timedelta(days=days-1)

    # Calculate baseline satisfaction before start_dt (to prevent 0% drop at midnight)
    baseline_up = db.query(func.count(FeedbackLog.id)).filter(
        FeedbackLog.timestamp < start_dt,
        FeedbackLog.rating == 'up'
    ).scalar() or 0
    
    baseline_down = db.query(func.count(FeedbackLog.id)).filter(
        FeedbackLog.timestamp < start_dt,
        FeedbackLog.rating == 'down'
    ).scalar() or 0
    
    # Generate Data
    if granularity == "15min":
        end_full = datetime.combine(end_dt, datetime.max.time())
        # Use printf for safe concatenation in SQLite; Force integer division
        bucket = func.printf('%s%02d', func.strftime('%Y-%m-%d %H:', FeedbackLog.timestamp), func.cast(func.cast(func.strftime('%M', FeedbackLog.timestamp), Integer) / 15, Integer) * 15)

        logs = db.query(
            bucket.label('minute'),
            func.sum(case((FeedbackLog.rating == 'up', 1), else_=0)).label('up'),
            func.sum(case((FeedbackLog.rating == 'down', 1), else_=0)).label('down')
        ).filter(FeedbackLog.timestamp >= start_dt, FeedbackLog.timestamp <= end_full).group_by('minute').all()
        
        trend_data = [{"date": log.minute, "up": log.up, "down": log.down} for log in logs]
        return {"trend": trend_data, "baseline_up": baseline_up, "baseline_down": baseline_down}

    if granularity == "minute":
        end_full = datetime.combine(end_dt, datetime.max.time())
        logs = db.query(
            func.strftime('%Y-%m-%d %H:%M', FeedbackLog.timestamp).label('minute'),
            func.sum(case((FeedbackLog.rating == 'up', 1), else_=0)).label('up'),
            func.sum(case((FeedbackLog.rating == 'down', 1), else_=0)).label('down')
        ).filter(FeedbackLog.timestamp >= start_dt, FeedbackLog.timestamp <= end_full).group_by('minute').all()
        
        trend_data = [{"date": log.minute, "up": log.up, "down": log.down} for log in logs]
        return {"trend": trend_data, "baseline_up": baseline_up, "baseline_down": baseline_down}

    if granularity == "hour":
        current = datetime.combine(start_dt, datetime.min.time())
        end_full = datetime.combine(end_dt, datetime.max.time())
        
        while current <= end_full:
            next_hour = current + timedelta(hours=1)
            
            # Count up/down using timestamp range (PostgreSQL compatible)
            up_count = db.query(func.count(FeedbackLog.id)).filter(
                FeedbackLog.timestamp >= current,
                FeedbackLog.timestamp < next_hour,
                FeedbackLog.rating == 'up'
            ).scalar() or 0
            
            down_count = db.query(func.count(FeedbackLog.id)).filter(
                FeedbackLog.timestamp >= current,
                FeedbackLog.timestamp < next_hour,
                FeedbackLog.rating == 'down'
            ).scalar() or 0
            
            results.append({
                "date": current.isoformat(),
                "up": up_count,
                "down": down_count
            })
            current += timedelta(hours=1)
            
    elif granularity == "month":
        current = start_dt.replace(day=1)
        end_curr = end_dt.replace(day=1)
        
        while current <= end_curr:
            # Calculate next month
            if current.month == 12:
                next_month = current.replace(year=current.year + 1, month=1, day=1)
            else:
                next_month = current.replace(month=current.month + 1, day=1)
            
            # Count up/down using timestamp range (PostgreSQL compatible)
            up_count = db.query(func.count(FeedbackLog.id)).filter(
                FeedbackLog.timestamp >= current,
                FeedbackLog.timestamp < next_month,
                FeedbackLog.rating == 'up'
            ).scalar() or 0
            
            down_count = db.query(func.count(FeedbackLog.id)).filter(
                FeedbackLog.timestamp >= current,
                FeedbackLog.timestamp < next_month,
                FeedbackLog.rating == 'down'
            ).scalar() or 0
            
            results.append({
                "date": current.strftime('%Y-%m'),
                "up": up_count,
                "down": down_count
            })
            current = next_month
    else:
        current = start_dt
        while current <= end_dt:
            up_count = db.query(func.count(FeedbackLog.id)).filter(
                func.date(FeedbackLog.timestamp) == current,
                FeedbackLog.rating == 'up'
            ).scalar() or 0
            
            down_count = db.query(func.count(FeedbackLog.id)).filter(
                func.date(FeedbackLog.timestamp) == current,
                FeedbackLog.rating == 'down'
            ).scalar() or 0
            
            results.append({
                "date": current.isoformat(),
                "up": up_count,
                "down": down_count
            })
            current += timedelta(days=1)
            
    return {"trend": results, "baseline_up": baseline_up, "baseline_down": baseline_down}



@router.get("/feedback/export")
async def export_feedback_csv(
    rating: Optional[str] = Query(default=None, pattern="^(up|down)$"), 
    period: Optional[str] = Query(default=None, pattern="^(day|week|month)$"),
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    db = Depends(get_db)
):
    """Export feedback as CSV."""
    from fastapi.responses import Response
    import csv
    import io
    
    query = db.query(FeedbackLog).order_by(desc(FeedbackLog.timestamp))
    
    if rating:
        query = query.filter(FeedbackLog.rating == rating)
    
    # Custom date range
    if start_date and end_date:
        try:
            start = datetime.fromisoformat(start_date)
            end = datetime.fromisoformat(end_date).replace(hour=23, minute=59, second=59)
            query = query.filter(FeedbackLog.timestamp >= start, FeedbackLog.timestamp <= end)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=f"Invalid date format: {e}")
    elif period:
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        if period == 'day':
            start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        elif period == 'week':
            days_since_monday = now.weekday()
            start = (now - timedelta(days=days_since_monday)).replace(hour=0, minute=0, second=0, microsecond=0)
        elif period == 'month':
            start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        else:
            start = None
        
        if start:
            query = query.filter(FeedbackLog.timestamp >= start)
    
    results = query.all()
    
    # Create CSV
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['Timestamp', 'User Query', 'Bot Response', 'Rating'])
    
    for f in results:
        writer.writerow([
            f.timestamp.replace(tzinfo=timezone.utc).isoformat() if f.timestamp else '',
            f.user_query or '',
            f.bot_response or '',
            f.rating
        ])
    
    csv_content = output.getvalue()
    
    # Sanitize filename to prevent injection
    safe_period = (period or 'all').replace('/', '_').replace('\\', '_').replace('..', '_')
    safe_rating = (rating or 'all').replace('/', '_').replace('\\', '_').replace('..', '_')
    filename = f"feedback_{safe_period}_{safe_rating}.csv"
    
    return Response(
        content=csv_content,
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


@router.get("/top-categories")
async def get_top_categories(
    days: int = Query(default=7, ge=1, le=365), 
    limit: int = Query(default=10, ge=1, le=100), 
    db = Depends(get_db)
):
    """Get most common query categories."""
    since = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=days)
    
    results = db.query(
        QueryLog.category,
        func.count(QueryLog.id).label('count')
    ).filter(
        QueryLog.timestamp >= since
    ).group_by(
        QueryLog.category
    ).order_by(
        desc('count')
    ).limit(limit).all()
    
    return {
        "categories": [
            {"category": r[0], "count": r[1]}
            for r in results
        ]
    }

# OpenAI Pricing (GPT-4o-mini as of Dec 2024)
INPUT_COST_PER_TOKEN = 0.00000015  # $0.15 per 1M tokens
OUTPUT_COST_PER_TOKEN = 0.0000006  # $0.60 per 1M tokens
EMBEDDING_COST_PER_TOKEN = 0.00000002 # $0.02 per 1M tokens (text-embedding-3-small)

@router.get("/spend")
async def get_spend_stats(db = Depends(get_db)):
    """Get spend statistics for the Spend analytics page."""
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    week_start = today_start - timedelta(days=now.weekday())
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    
    # Use simple format for SQLite comparison
    fmt = "%Y-%m-%d %H:%M:%S"
    
    def get_spend_for_period(start_date):
        """Calculate tokens and cost for a given period."""
        # Convert start_date to string format for SQLite comparison
        start_str = start_date.strftime(fmt)
        
        # Query Logs (UTC timestamps)
        result = db.query(
            func.coalesce(func.sum(QueryLog.input_tokens), 0).label('input_tokens'),
            func.coalesce(func.sum(QueryLog.output_tokens), 0).label('output_tokens'),
            func.coalesce(func.sum(QueryLog.embedding_tokens), 0).label('embedding_tokens'),
            func.count(QueryLog.id).label('query_count')
        ).filter(
            QueryLog.timestamp >= start_str
        ).first()
        
        # Manual Expenses (UTC timestamps)
        expense_sum = db.query(func.coalesce(func.sum(ExpenseLog.amount), 0)).filter(
            ExpenseLog.timestamp >= start_str
        ).scalar()
        
        input_tokens = int(result.input_tokens or 0)
        output_tokens = int(result.output_tokens or 0)
        embedding_tokens = int(result.embedding_tokens or 0)
        query_count = int(result.query_count or 0)
        misc_cost = float(expense_sum or 0)
        
        current_input_cost = input_tokens * INPUT_COST_PER_TOKEN
        current_output_cost = output_tokens * OUTPUT_COST_PER_TOKEN
        current_embedding_cost = embedding_tokens * EMBEDDING_COST_PER_TOKEN
        
        total_cost = current_input_cost + current_output_cost + current_embedding_cost + misc_cost
        
        return {
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "embedding_tokens": embedding_tokens,
            "total_tokens": input_tokens + output_tokens + embedding_tokens,
            "chat_cost": round(current_input_cost + current_output_cost, 6),
            "embedding_cost": round(current_embedding_cost, 6),
            "misc_cost": round(misc_cost, 6),  # Consistent 6 decimals
            "cost": round(total_cost, 6),
            "query_count": query_count
        }
    
    # Get spend for each period
    today = get_spend_for_period(today_start)
    week = get_spend_for_period(week_start)
    month = get_spend_for_period(month_start)
    
    # All time
    all_time_result = db.query(
        func.coalesce(func.sum(QueryLog.input_tokens), 0).label('input_tokens'),
        func.coalesce(func.sum(QueryLog.output_tokens), 0).label('output_tokens'),
        func.coalesce(func.sum(QueryLog.embedding_tokens), 0).label('embedding_tokens'),
        func.count(QueryLog.id).label('query_count')
    ).first()
    
    all_time_expense = db.query(func.coalesce(func.sum(ExpenseLog.amount), 0)).scalar()
    
    all_input = int(all_time_result.input_tokens or 0)
    all_output = int(all_time_result.output_tokens or 0)
    all_embed = int(all_time_result.embedding_tokens or 0)
    all_count = int(all_time_result.query_count or 0)
    all_misc = float(all_time_expense or 0)
    
    all_chat_cost = (all_input * INPUT_COST_PER_TOKEN) + (all_output * OUTPUT_COST_PER_TOKEN)
    all_embed_cost = all_embed * EMBEDDING_COST_PER_TOKEN
    all_total_cost = all_chat_cost + all_embed_cost + all_misc
    
    all_time = {
        "input_tokens": all_input,
        "output_tokens": all_output,
        "embedding_tokens": all_embed,
        "total_tokens": all_input + all_output + all_embed,
        "chat_cost": round(all_chat_cost, 6),
        "embedding_cost": round(all_embed_cost, 6),
        "misc_cost": round(all_misc, 6),  # Consistent 6 decimals
        "cost": round(all_total_cost, 6),
        "query_count": all_count
    }
    
    # Average cost per query (Total Cost / Total Queries)
    avg_cost = round(all_total_cost / all_count, 6) if all_count > 0 else 0
    
    return {
        "today": today,
        "week": week,
        "month": month,
        "all_time": all_time,
        "avg_cost_per_query": avg_cost,
        "pricing": {
            "input_per_1m": 0.15,
            "output_per_1m": 0.60,
            "embedding_per_1m": 0.02,
            "model": "gpt-4o-mini + text-embedding-3-small"
        }
    }

class ExpenseCreate(BaseModel):
    category: str = Field(..., min_length=1, max_length=100)
    description: str = Field(..., min_length=1, max_length=500)
    amount: float = Field(..., gt=0, le=1000000)  # Positive, capped at 1M
    date: Optional[str] = Field(None, pattern=r'^\d{4}-\d{2}-\d{2}$')  # YYYY-MM-DD format

@router.post("/expenses")
async def add_expense(expense: ExpenseCreate):
    """Add a manual expense."""
    from app.services.analytics import AnalyticsService
    service = AnalyticsService()
    
    timestamp = None
    if expense.date:
        try:
            # Parse date and set to start of day UTC
            dt = datetime.strptime(expense.date, "%Y-%m-%d")
            timestamp = dt
        except ValueError as e:
            raise HTTPException(status_code=400, detail=f"Invalid date format: {e}")

    service.log_expense(
        category=expense.category,
        description=expense.description,
        amount=expense.amount,
        timestamp=timestamp
    )
    return {"status": "success"}
