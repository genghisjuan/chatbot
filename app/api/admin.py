"""
Admin Analytics API Endpoints.

Provides data for the analytics dashboard including:
- Summary statistics
- Time-series data
- Feedback analysis
- Token usage and cost tracking
"""
from datetime import datetime, timedelta, timezone, date
from typing import Optional, Generator
import logging
import csv
import io

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy import create_engine, func, desc, case, Integer
from sqlalchemy.orm import Session, sessionmaker
from pydantic import BaseModel, Field

from app.core.config import settings
from app.services.analytics import (
    QueryLog,
    FeedbackLog,
    Base,
    EscalationLog,
    ExpenseLog,
    AnalyticsService
)

router = APIRouter()
logger = logging.getLogger(__name__)

# Database connection
engine = create_engine(settings.DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# OpenAI Pricing (GPT-4o-mini as of Dec 2024)
# Consider moving to settings.PRICING_CONFIG for easier updates
INPUT_COST_PER_TOKEN = 0.00000015  # $0.15 per 1M tokens
OUTPUT_COST_PER_TOKEN = 0.0000006   # $0.60 per 1M tokens
EMBEDDING_COST_PER_TOKEN = 0.00000002  # $0.02 per 1M tokens

# Constants
MAX_EXPORT_ROWS = 10000
MAX_DATE_RANGE_DAYS = 365


def get_db() -> Generator[Session, None, None]:
    """
    Database session dependency.
    
    Yields:
        Session: SQLAlchemy database session
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _calculate_period_start(period: str) -> Optional[datetime]:
    """
    Calculate start datetime for common periods (day/week/month).
    
    Args:
        period: Time period ('day', 'week', or 'month')
        
    Returns:
        Start datetime for the period, or None if invalid
    """
    if not period:
        return None
    
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    
    if period == 'day':
        return now.replace(hour=0, minute=0, second=0, microsecond=0)
    elif period == 'week':
        days_since_monday = now.weekday()
        return (now - timedelta(days=days_since_monday)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
    elif period == 'month':
        return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    
    logger.warning(f"Unknown period requested: {period}")
    return None


# Helper for strict date parsing
def _parse_date_range(period: str, start_date: str, end_date: str, timezone_offset: int) -> tuple[datetime, datetime]:
    """
    Parses date range based on explicit user rules.
    Returns inclusive start and end datetimes in UTC.
    """
    # Base "now" in user's timezone (approximated by removing offset from UTC)
    # Actually, easiest is to calculate local times then convert back to UTC bounds.
    now_utc = datetime.now(timezone.utc).replace(tzinfo=None)
    
    # User's "now"
    offset_delta = timedelta(minutes=-timezone_offset)
    now_user = now_utc - offset_delta
    today_user_start = now_user.replace(hour=0, minute=0, second=0, microsecond=0)
    today_user_end = now_user.replace(hour=23, minute=59, second=59, microsecond=999999)

    if period == 'custom' and start_date and end_date:
        try:
            # User inputs are YYYY-MM-DD
            s = datetime.strptime(start_date, '%Y-%m-%d')
            e = datetime.strptime(end_date, '%Y-%m-%d')
            # Full inclusive range in user time
            start_local = s.replace(hour=0, minute=0, second=0, microsecond=0)
            end_local = e.replace(hour=23, minute=59, second=59, microsecond=999999)
            return start_local + offset_delta, end_local + offset_delta
        except ValueError:
            pass # Fallback to today

    if period == 'last_7_days':
        # Start: 6 days before today 00:00 (Total 7 days inclusive of today)
        start_local = today_user_start - timedelta(days=6)
        return start_local + offset_delta, today_user_end + offset_delta

    if period == 'last_30_days':
        # Start: 29 days before today 00:00
        start_local = today_user_start - timedelta(days=29)
        return start_local + offset_delta, today_user_end + offset_delta

    if period == 'month':
        # Start: 1st of current month
        start_local = today_user_start.replace(day=1)
        return start_local + offset_delta, today_user_end + offset_delta
    
    if period == 'year':
        # Start: Jan 1st of current year
        start_local = today_user_start.replace(month=1, day=1)
        return start_local + offset_delta, today_user_end + offset_delta

    # Default to 'day' / 'today'
    return today_user_start + offset_delta, today_user_end + offset_delta


@router.get("/summary")
async def get_summary_stats(
    period: str = Query(default="today"),
    start_date: Optional[str] = None, 
    end_date: Optional[str] = None,
    timezone_offset: int = Query(default=0),
    db: Session = Depends(get_db)
):
    """
    Get summary statistics with strict time filtering for KPIs.
    """
    logger.debug(f"Fetching summary stats: period={period}, tz={timezone_offset}")
    
    # 1. Calculate Filter Range
    start_dt, end_dt = _parse_date_range(period, start_date, end_date, timezone_offset)
    
    # 2. Activity Stats (Keep these static for the Overview cards which explicitly say Today/Week/Month)
    # We could filter these too, but the UI labels are static. Let's keep them as "Pulse" metrics.
    # Refetching logic to be safe/clean
    now_utc = datetime.now(timezone.utc).replace(tzinfo=None)
    today_utc = now_utc.date()
    
    # Today
    messages_today = db.query(func.count(QueryLog.id)).filter(
        func.date(QueryLog.timestamp) == today_utc.isoformat()
    ).scalar() or 0
    
    # Week
    days_since_monday = now_utc.weekday()
    week_start = (now_utc - timedelta(days=days_since_monday)).replace(hour=0, minute=0, second=0, microsecond=0)
    messages_week = db.query(func.count(QueryLog.id)).filter(
        QueryLog.timestamp >= week_start
    ).scalar() or 0
    
    # Month
    month_start = now_utc.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    messages_month = db.query(func.count(QueryLog.id)).filter(
        QueryLog.timestamp >= month_start
    ).scalar() or 0
    
    # Total Escalations (All time? Or filtered? Let's filter escalations by the active range too for consistency)
    total_escalations = db.query(func.count(EscalationLog.id)).filter(
        EscalationLog.timestamp >= start_dt,
        EscalationLog.timestamp <= end_dt
    ).scalar() or 0

    # 3. Filtered Feedback KPIs (The Core Requirement)
    # Denominator: Responses with a rating (up or down) in the range
    positive_feedback = db.query(func.count(FeedbackLog.id)).filter(
        FeedbackLog.rating == 'up',
        FeedbackLog.timestamp >= start_dt,
        FeedbackLog.timestamp <= end_dt
    ).scalar() or 0
    
    negative_feedback = db.query(func.count(FeedbackLog.id)).filter(
        FeedbackLog.rating == 'down',
        FeedbackLog.timestamp >= start_dt,
        FeedbackLog.timestamp <= end_dt
    ).scalar() or 0
    
    total_feedback_in_range = positive_feedback + negative_feedback
    
    if total_feedback_in_range > 0:
        positive_rate = (positive_feedback / total_feedback_in_range) * 100
        negative_rate = (negative_feedback / total_feedback_in_range) * 100
    else:
        positive_rate = 0
        negative_rate = 0
    
    # Other filtered metrics
    # Total sessions in range
    total_sessions_range = db.query(func.count(QueryLog.id)).filter(
        QueryLog.timestamp >= start_dt,
        QueryLog.timestamp <= end_dt,
        QueryLog.is_initial == 1
    ).scalar() or 0
    
    # Containment Rate
    if total_sessions_range > 0:
        containment_rate = max(0, (total_sessions_range - total_escalations) / total_sessions_range * 100)
    else:
        containment_rate = 100 if total_escalations == 0 else 0

    # Fallback Rate
    total_queries_range = db.query(func.count(QueryLog.id)).filter(
        QueryLog.timestamp >= start_dt,
        QueryLog.timestamp <= end_dt
    ).scalar() or 0
    
    fallback_queries_range = db.query(func.count(QueryLog.id)).filter(
        QueryLog.timestamp >= start_dt,
        QueryLog.timestamp <= end_dt,
        QueryLog.is_fallback == 1
    ).scalar() or 0
    
    fallback_rate = (fallback_queries_range / total_queries_range * 100) if total_queries_range > 0 else 0
    
    return {
        "messages_today": messages_today,
        "messages_week": messages_week,
        "messages_month": messages_month,
        "positive_feedback_score": round(positive_rate, 1),
        "negative_feedback_score": round(negative_rate, 1),
        "total_feedback": total_feedback_in_range,
        "positive_count": positive_feedback,
        "negative_count": negative_feedback,
        "containment_rate": round(containment_rate, 1),
        "fallback_rate": round(fallback_rate, 1),
        "total_escalations": total_escalations
    }


@router.get("/messages-trend")
async def get_messages_trend(
    days: int = Query(default=7, ge=0, le=MAX_DATE_RANGE_DAYS), 
    start_date: Optional[str] = None, 
    end_date: Optional[str] = None,
    granularity: str = Query(
        default="day",
        pattern="^(15min|minute|hour|day|month)$"
    ),
    timezone_offset: int = Query(
        default=0,
        ge=-720,
        le=840,
        description="User's timezone offset from UTC in minutes (e.g., -300 for EST)"
    ),
    db: Session = Depends(get_db)
) -> dict:
    """
    Get message counts for trend chart with configurable granularity.
    
    Args:
        days: Number of days to query (default 7)
        start_date: Optional custom start date (YYYY-MM-DD)
        end_date: Optional custom end date (YYYY-MM-DD)
        granularity: Time bucket size (15min, minute, hour, day, month)
        timezone_offset: User timezone offset in minutes
        db: Database session
        
    Returns:
        dict: Trend data with date/count pairs
    """
    logger.debug(
        f"Fetching message trend: days={days}, start={start_date}, "
        f"end={end_date}, granularity={granularity}"
    )
    
    results = []
    
    # Custom Date Range (Priority)
    if start_date and end_date:
        try:
            # Parse as dates in user's local timezone
            start_date_local = datetime.strptime(start_date, '%Y-%m-%d').date()
            end_date_local = datetime.strptime(end_date, '%Y-%m-%d').date()
            
            # Validate date range
            if start_date_local > end_date_local:
                raise HTTPException(
                    status_code=400,
                    detail="start_date must be before or equal to end_date"
                )
            
            # Prevent unreasonably large ranges
            if (end_date_local - start_date_local).days > MAX_DATE_RANGE_DAYS:
                raise HTTPException(
                    status_code=400,
                    detail=f"Date range too large. Maximum {MAX_DATE_RANGE_DAYS} days allowed."
                )
            
            # Convert to UTC
            offset_hours = -timezone_offset // 60
            offset_minutes = -timezone_offset % 60
            
            start_dt_naive = datetime.combine(start_date_local, datetime.min.time())
            end_dt_naive = datetime.combine(end_date_local, datetime.min.time())
            
            start_dt = start_dt_naive + timedelta(hours=offset_hours, minutes=offset_minutes)
            end_dt = end_dt_naive + timedelta(hours=offset_hours, minutes=offset_minutes)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=f"Invalid date format: {e}")
    else:
        # Last N Days (UTC) - inclusive of current day
        now_utc = datetime.now(timezone.utc).replace(tzinfo=None)
        end_dt = now_utc.date()
        start_dt = end_dt - timedelta(days=days - 1)

    # Generate Data by Granularity
    if granularity == "15min":
        # 15-minute buckets
        if not isinstance(start_dt, datetime):
            start_dt = datetime.combine(start_dt, datetime.min.time())
        if not isinstance(end_dt, datetime):
            end_dt = datetime.combine(end_dt, datetime.min.time())
        
        end_full = end_dt + timedelta(hours=23, minutes=59, seconds=59, microseconds=999999)

        # SQLite-compatible integer division for 15-min buckets
        bucket = func.printf(
            '%s%02d',
            func.strftime('%Y-%m-%d %H:', QueryLog.timestamp),
            func.cast(
                func.cast(func.strftime('%M', QueryLog.timestamp), Integer) / 15,
                Integer
            ) * 15
        )
        
        logs = db.query(
            bucket.label('minute'),
            func.count(QueryLog.id).label('count')
        ).filter(
            QueryLog.timestamp >= start_dt,
            QueryLog.timestamp <= end_full
        ).group_by('minute').all()
        
        results = [{"date": log.minute, "count": log.count} for log in logs]
        return {"trend": results}

    if granularity == "minute":
        # Minute-by-minute (last 6 hours)
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        start_dt_full = now - timedelta(hours=6)
        end_full = now

        logs = db.query(
            func.strftime('%Y-%m-%d %H:%M', QueryLog.timestamp).label('minute'),
            func.count(QueryLog.id).label('count')
        ).filter(
            QueryLog.timestamp >= start_dt_full,
            QueryLog.timestamp <= end_full
        ).group_by('minute').all()
        
        results = [{"date": log.minute, "count": log.count} for log in logs]
        return {"trend": results}

    if granularity == "hour":
        # Hourly buckets
        if isinstance(start_dt, date) and not isinstance(start_dt, datetime):
            current = datetime.combine(start_dt, datetime.min.time())
            end_full = datetime.combine(end_dt, datetime.max.time())
        else:
            current = start_dt
            end_full = end_dt + timedelta(hours=23, minutes=59, seconds=59)
        
        while current <= end_full:
            next_hour = current + timedelta(hours=1)
            
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
        # Monthly buckets
        current = start_dt.replace(day=1) if isinstance(start_dt, datetime) else datetime.combine(start_dt, datetime.min.time()).replace(day=1)
        end_curr = end_dt.replace(day=1) if isinstance(end_dt, datetime) else datetime.combine(end_dt, datetime.min.time()).replace(day=1)
        
        while current <= end_curr:
            if current.month == 12:
                next_month = current.replace(year=current.year + 1, month=1, day=1)
            else:
                next_month = current.replace(month=current.month + 1, day=1)
            
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
        # Daily buckets (default)
        current = start_dt if isinstance(start_dt, date) else start_dt.date()
        end = end_dt if isinstance(end_dt, date) else end_dt.date()
        
        while current <= end:
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
    period: str = Query(default="today"),
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    timezone_offset: int = 0,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=12, ge=1, le=100),
    db: Session = Depends(get_db)
) -> dict:
    """
    Get recent feedback with unified time filtering and pagination.
    
    Pagination behavior:
    - page: 1-based page number
    - page_size: items per page (default 12)
    - Returns totalCount for the current filters (used by frontend to show/hide pagination)
    """
    logger.debug(f"Fetching feedback list: rating={rating}, period={period}, page={page}")
    
    # 1. Unified Date Parsing
    start_dt, end_dt = _parse_date_range(period, start_date, end_date, timezone_offset)
    
    # 2. Build base query with filters
    query = db.query(FeedbackLog).filter(
        FeedbackLog.timestamp >= start_dt,
        FeedbackLog.timestamp <= end_dt
    ).order_by(desc(FeedbackLog.timestamp))
    
    if rating:
        query = query.filter(FeedbackLog.rating == rating)
    
    # 3. Get total count for pagination (before applying limit/offset)
    total_count = query.count()
    
    # 4. Apply pagination
    offset = (page - 1) * page_size
    results = query.offset(offset).limit(page_size).all()
    
    # 5. Return paginated response
    return {
        "items": [
            {
                "id": f.id,
                "timestamp": f.timestamp.replace(tzinfo=timezone.utc).isoformat() if f.timestamp else None,
                "user_query": f.user_query,
                "bot_response": f.bot_response,
                "rating": f.rating
            }
            for f in results
        ],
        "totalCount": total_count,
        "page": page,
        "pageSize": page_size
    }



@router.get("/feedback-trend")
async def get_feedback_trend(
    period: str = Query(default="last_7_days"),
    start_date: Optional[str] = None, 
    end_date: Optional[str] = None,
    granularity: Optional[str] = Query(
        default=None, # If None, determine automatically based on period
        pattern="^(15min|minute|hour|day|month)$"
    ),
    timezone_offset: int = Query(default=0),
    db: Session = Depends(get_db)
) -> dict:
    """
    Get feedback trend statistics with unified filtering.
    """
    logger.debug(f"Fetching feedback trend: period={period}")
    
    # 1. Unified Date Parsing
    start_dt, end_dt = _parse_date_range(period, start_date, end_date, timezone_offset)
    
    # Auto-granularity if not provided (per Master Prompt rules)
    if not granularity:
        if period == 'today':
            granularity = 'hour'
        elif period in ['last_7_days', 'last_30_days', 'month']:
            granularity = 'day'
        elif period == 'year':
            granularity = 'month'
        elif period == 'custom':
            # Range <= 3 days -> hourly
            # 3-90 days -> daily
            # >90 days -> month (simplified from prompt "weekly or monthly")
            delta = end_dt - start_dt
            if delta.days <= 3:
                granularity = 'hour'
            elif delta.days <= 90:
                granularity = 'day'
            else:
                granularity = 'month'
        else:
            granularity = 'day' # Fallback
            
    results = []
    
    # Calculate baseline (Strict per-bucket means we might NOT want cumulative baseline?)
    # Prompt says: "Trendline buckets must reflect the percentage at that time, not cumulative counts."
    # So baseline_up/down are irrelevant for the chart, BUT might be useful if we wanted to show total-to-date.
    # The frontend chart logic I fixed earlier ignores these for the dataset, so I'll leave them as 0 or calculate them if needed. 
    # For minimalism, I'll calculate them (respecting the filter? no, baseline is pre-filter).
    baseline_up = 0
    baseline_down = 0
    
    # Generate trend data by granularity
    # Note: re-using the existing query logic but swapping the date definitions
    
    if granularity == "15min":
        end_full = end_dt # _parse returns inclusive end with time
        
        bucket = func.printf(
            '%s%02d',
            func.strftime('%Y-%m-%d %H:', FeedbackLog.timestamp),
            func.cast(
                func.cast(func.strftime('%M', FeedbackLog.timestamp), Integer) / 15,
                Integer
            ) * 15
        )

        logs = db.query(
            bucket.label('minute'),
            func.sum(case((FeedbackLog.rating == 'up', 1), else_=0)).label('up'),
            func.sum(case((FeedbackLog.rating == 'down', 1), else_=0)).label('down')
        ).filter(
            FeedbackLog.timestamp >= start_dt,
            FeedbackLog.timestamp <= end_full
        ).group_by('minute').all()
        
        trend_data = [{"date": log.minute, "up": log.up, "down": log.down} for log in logs]
        return {"trend": trend_data, "baseline_up": baseline_up, "baseline_down": baseline_down}

    if granularity == "minute":
        end_full = end_dt
        
        logs = db.query(
            func.strftime('%Y-%m-%d %H:%M', FeedbackLog.timestamp).label('minute'),
            func.sum(case((FeedbackLog.rating == 'up', 1), else_=0)).label('up'),
            func.sum(case((FeedbackLog.rating == 'down', 1), else_=0)).label('down')
        ).filter(
            FeedbackLog.timestamp >= start_dt,
            FeedbackLog.timestamp <= end_full
        ).group_by('minute').all()
        
        trend_data = [{"date": log.minute, "up": log.up, "down": log.down} for log in logs]
        return {"trend": trend_data, "baseline_up": baseline_up, "baseline_down": baseline_down}

    if granularity == "hour":
        # Use simple iterative query for robustness with gaps, similar to original code
        # But ensure we respect the exact start/end
        current = start_dt.replace(minute=0, second=0, microsecond=0)
        
        while current <= end_dt:
            next_hour = current + timedelta(hours=1)
            
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
        # Start at the first day of the start month
        current = start_dt.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        
        while current <= end_dt:
            if current.month == 12:
                next_month = current.replace(year=current.year + 1, month=1, day=1)
            else:
                next_month = current.replace(month=current.month + 1, day=1)
            
            # Intersection of [current, next_month) AND [start_dt, end_dt]
            # Actually, standard month buckets are fine
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
        # Daily buckets (default)
        current = start_dt.replace(hour=0, minute=0, second=0, microsecond=0)
        
        while current <= end_dt:
            next_day = current + timedelta(days=1)
            
            up_count = db.query(func.count(FeedbackLog.id)).filter(
                FeedbackLog.timestamp >= current,
                FeedbackLog.timestamp < next_day,
                FeedbackLog.rating == 'up'
            ).scalar() or 0
            
            down_count = db.query(func.count(FeedbackLog.id)).filter(
                func.date(FeedbackLog.timestamp) == current,
                FeedbackLog.rating == 'down'
            ).scalar() or 0
            
            results.append({
                "date": current.date().isoformat(),
                "up": up_count,
                "down": down_count
            })
            current = next_day

    return {"trend": results, "baseline_up": baseline_up, "baseline_down": baseline_down}


@router.get("/feedback/export")
async def export_feedback_csv(
    rating: Optional[str] = Query(default=None, pattern="^(up|down)$"), 
    period: Optional[str] = Query(default=None, pattern="^(day|week|month)$"),
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    db: Session = Depends(get_db)
) -> Response:
    """
    Export feedback as CSV file.
    
    Includes audit logging for compliance (GDPR/SOC2).
    """
    logger.info(f"Feedback export requested: rating={rating}, period={period}")
    
    query = db.query(FeedbackLog).order_by(desc(FeedbackLog.timestamp))
    
    if rating:
        query = query.filter(FeedbackLog.rating == rating)
    
    # Date filters
    if start_date and end_date:
        try:
            start = datetime.fromisoformat(start_date)
            end = datetime.fromisoformat(end_date).replace(hour=23, minute=59, second=59)
            query = query.filter(
                FeedbackLog.timestamp >= start,
                FeedbackLog.timestamp <= end
            )
        except ValueError as e:
            raise HTTPException(status_code=400, detail=f"Invalid date format: {e}")
    elif period:
        start = _calculate_period_start(period)
        if start:
            query = query.filter(FeedbackLog.timestamp >= start)
    
    # Limit for DoS protection
    results = query.limit(MAX_EXPORT_ROWS).all()
    
    # Audit log
    logger.info(
        f"Feedback export: rating={rating or 'all'}, period={period or 'all'}, "
        f"start={start_date or 'N/A'}, end={end_date or 'N/A'}, "
        f"rows_exported={len(results)}, limit={MAX_EXPORT_ROWS}"
    )
    
    # Generate CSV
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
    
    # Sanitize filename
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
    days: int = Query(default=7, ge=1, le=MAX_DATE_RANGE_DAYS), 
    limit: int = Query(default=10, ge=1, le=100), 
    db: Session = Depends(get_db)
) -> dict:
    """
    Get most common query categories.
    
    Args:
        days: Number of days to analyze
        limit: Maximum number of categories to return
        db: Database session
        
    Returns:
        dict: List of categories with count
    """
    logger.debug(f"Fetching top categories: days={days}, limit={limit}")
    
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


@router.get("/spend")
async def get_spend_stats(db: Session = Depends(get_db)) -> dict:
    """
    Get spend statistics for the Spend analytics page.
    
    Returns:
        dict: Token usage and cost breakdown by time period
    """
    logger.debug("Fetching spend statistics")
    
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    week_start = today_start - timedelta(days=now.weekday())
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    
    # SQLite-compatible date format
    fmt = "%Y-%m-%d %H:%M:%S"
    
    def get_spend_for_period(start_date: datetime) -> dict:
        """Calculate tokens and cost for a given period."""
        start_str = start_date.strftime(fmt)
        
        # Query token usage
        result = db.query(
            func.coalesce(func.sum(QueryLog.input_tokens), 0).label('input_tokens'),
            func.coalesce(func.sum(QueryLog.output_tokens), 0).label('output_tokens'),
            func.coalesce(func.sum(QueryLog.embedding_tokens), 0).label('embedding_tokens'),
            func.count(QueryLog.id).label('query_count')
        ).filter(
            QueryLog.timestamp >= start_str
        ).first()
        
        # Manual expenses
        expense_sum = db.query(
            func.coalesce(func.sum(ExpenseLog.amount), 0)
        ).filter(
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
            "misc_cost": round(misc_cost, 6),
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
    
    all_time_expense = db.query(
        func.coalesce(func.sum(ExpenseLog.amount), 0)
    ).scalar()
    
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
        "misc_cost": round(all_misc, 6),
        "cost": round(all_total_cost, 6),
        "query_count": all_count
    }
    
    # Average cost per query
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
    """Request model for creating manual expenses."""
    category: str = Field(..., min_length=1, max_length=100)
    description: str = Field(..., min_length=1, max_length=500)
    amount: float = Field(..., gt=0, le=1000000)  # Positive, capped at 1M
    date: Optional[str] = Field(None, pattern=r'^\d{4}-\d{2}-\d{2}$')  # YYYY-MM-DD


@router.post("/expenses")
async def add_expense(
    expense: ExpenseCreate,
    db: Session = Depends(get_db)
) -> dict:
    """
    Add a manual expense entry.
    
    Args:
        expense: Expense details
        db: Database session
        
    Returns:
        dict: Success status
    """
    logger.info(f"Adding expense: category={expense.category}, amount={expense.amount}")
    
    # Use existing DB session passed from dependency
    service = AnalyticsService(db=db)
    
    timestamp = None
    if expense.date:
        try:
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
