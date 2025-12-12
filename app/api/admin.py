from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks
from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy import create_engine, func, desc, case, text
from sqlalchemy.orm import sessionmaker, Session
from app.core.config import settings
from app.services.analytics import QueryLog, FeedbackLog, EscalationLog, ExpenseLog
import os
import csv
import io
from datetime import datetime, timedelta, timezone
# Use zoneinfo for timezone handling
try:
    from zoneinfo import ZoneInfo
except ImportError:
    from backports.zoneinfo import ZoneInfo # Fallback

# 1. Database Setup
# ------------------------------------------------------------------------------
DATABASE_URL = settings.DATABASE_URL
if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

router = APIRouter()

# 2. Timezone & Helper Functions
# ------------------------------------------------------------------------------
EST = ZoneInfo("America/New_York")

def _get_est_now():
    return datetime.now(EST)

def _parse_range(range_type: str, start_date: str = None, end_date: str = None):
    """
    Returns (start_utc, end_utc, granularity) for the given range filter.
    Input ranges (start_date, end_date) are interpreted as EST.
    Returns UTC datetimes for DB querying.
    """
    now_est = _get_est_now()
    today_est = now_est.replace(hour=0, minute=0, second=0, microsecond=0)
    
    start_est = today_est
    end_est = now_est
    granularity = "day"

    if range_type == "today":
        start_est = today_est
        end_est = today_est.replace(hour=23, minute=59, second=59, microsecond=999999)
        granularity = "hour"
    
    elif range_type == "week":
        # Monday of this week
        start_est = today_est - timedelta(days=today_est.weekday())
        end_est = now_est
        granularity = "day"

    elif range_type == "month":
        # 1st of this month
        start_est = today_est.replace(day=1)
        end_est = now_est
        granularity = "day"

    elif range_type == "year":
        # Jan 1st of this year
        start_est = today_est.replace(month=1, day=1)
        end_est = now_est
        granularity = "month"

    elif range_type == "custom":
        if not start_date or not end_date:
            raise HTTPException(400, "start_date and end_date required for custom range")
        try:
            # Parse YYYY-MM-DD (assume midnight EST start, 23:59 EST end)
            s = datetime.strptime(start_date, "%Y-%m-%d")
            e = datetime.strptime(end_date, "%Y-%m-%d")
            
            start_est = s.replace(tzinfo=EST)
            end_est = e.replace(hour=23, minute=59, second=59, microsecond=999999, tzinfo=EST)
            
            # Intelligent granularity
            diff = (end_est - start_est).days
            if diff <= 3: granularity = "hour"
            elif diff <= 31: granularity = "day"
            elif diff <= 365: granularity = "week"
            else: granularity = "month"

        except ValueError:
            raise HTTPException(400, "Invalid date format. Use YYYY-MM-DD")
    
    # Validation: Max 365 days range
    if (end_est - start_est).days > 366:
         raise HTTPException(400, "Date range cannot exceed 365 days")

    # Convert to UTC for DB queries
    start_utc = start_est.astimezone(timezone.utc)
    end_utc = end_est.astimezone(timezone.utc)
    
    return start_utc, end_utc, granularity

# 3. API Endpoints
# ------------------------------------------------------------------------------

@router.get("/summary")
def get_summary(
    range: str = Query(..., regex="^(today|week|month|year|custom)$"),
    start_date: str = None,
    end_date: str = None,
    db: Session = Depends(get_db)
):
    try:
        start_utc, end_utc, _ = _parse_range(range, start_date, end_date)
        
        # 1. Counts
        # Conversations = count of is_initial=True
        conversations = db.query(QueryLog).filter(
            QueryLog.timestamp >= start_utc,
            QueryLog.timestamp <= end_utc,
            QueryLog.is_initial == 1
        ).count()

        queries = db.query(QueryLog).filter(
            QueryLog.timestamp >= start_utc,
            QueryLog.timestamp <= end_utc
        ).count()

        # 2. Feedback
        # Positive (1), Negative (-1). Exclude 0.
        pos_count = db.query(FeedbackLog).filter(
            FeedbackLog.timestamp >= start_utc,
            FeedbackLog.timestamp <= end_utc,
            FeedbackLog.rating == 1
        ).count()

        neg_count = db.query(FeedbackLog).filter(
            FeedbackLog.timestamp >= start_utc,
            FeedbackLog.timestamp <= end_utc,
            FeedbackLog.rating == -1
        ).count()

        # Rates
        total_rated = pos_count + neg_count
        pos_rate = (pos_count / total_rated * 100) if total_rated > 0 else 0
        neg_rate = (neg_count / total_rated * 100) if total_rated > 0 else 0

        # 3. Escalations
        phone_esc = db.query(EscalationLog).filter(
            EscalationLog.timestamp >= start_utc,
            EscalationLog.timestamp <= end_utc,
            EscalationLog.type.in_(['phone', 'callback', 'call-inbound'])
        ).count()

        email_esc = db.query(EscalationLog).filter(
            EscalationLog.timestamp >= start_utc,
            EscalationLog.timestamp <= end_utc,
            EscalationLog.type == 'email'
        ).count()

        # 4. Avg Queries per Conversation
        avg_qpc = (queries / conversations) if conversations > 0 else 0

        return {
            "total_conversations": conversations,
            "total_queries": queries,
            "positive_feedback_count": pos_count,
            "negative_feedback_count": neg_count,
            "positive_feedback_rate": round(pos_rate, 1),
            "negative_feedback_rate": round(neg_rate, 1),
            "phone_escalations": phone_esc,
            "email_escalations": email_esc,
            "period_start": start_utc.isoformat(),
            "period_end": end_utc.isoformat()
        }
    except Exception as e:
        import traceback
        print(traceback.format_exc()) # Log to server console
        raise HTTPException(status_code=500, detail=f"Summary Error: {str(e)}")

@router.get("/trends")
def get_trends(
    range: str = Query(..., regex="^(today|week|month|year|custom)$"),
    start_date: str = None,
    end_date: str = None,
    db: Session = Depends(get_db)
):
    start_utc, end_utc, granularity = _parse_range(range, start_date, end_date)

    # Dictionary to hold aggregated data
    # Key: bucket_string (ISO format), Value: {queries: 0, conversations: 0}
    timeline = {}

    # Helper to generate buckets within the range
    # This ensures we have entries even for empty periods (optional but good for charts)
    current = start_utc
    # We'll rely on the data loop to create buckets to keep it simple, 
    # but a gaps-filling logic is better for charts.
    # For now, let's just aggregate actual data.
    
    # 1. Fetch RAW data
    query_logs = db.query(QueryLog.timestamp, QueryLog.is_initial).filter(
        QueryLog.timestamp >= start_utc,
        QueryLog.timestamp <= end_utc
    ).all()

    # 2. Aggregate in Python
    # --------------------------------------------------------------------------
    
    # Pre-fill timeline to ensure 0s
    timeline = {}
    fb_timeline = {}

    step = timedelta(days=1)
    if granularity == "hour":
        step = timedelta(hours=1)
    elif granularity == "week":
        step = timedelta(weeks=1)
    
    curr = start_utc
    while curr <= end_utc:
        curr_est = curr.astimezone(EST)
        b_key = _truncate_date(curr_est, granularity)
        
        if b_key not in timeline:
            timeline[b_key] = {"queries": 0, "conversations": 0}
        
        if b_key not in fb_timeline:
            fb_timeline[b_key] = {"pos": 0, "neg": 0}
            
        curr += step

    for q_ts, is_init in query_logs:
        if not q_ts: continue
        
        # FIX: SQLite may return naive strings/datetimes. Assume UTC if naive.
        if q_ts.tzinfo is None:
            q_ts = q_ts.replace(tzinfo=timezone.utc)
            
        # Convert to EST for display
        ts_est = q_ts.astimezone(EST)
        
        # Truncate based on granularity
        bucket_key = _truncate_date(ts_est, granularity)
        
        if bucket_key not in timeline:
            timeline[bucket_key] = {"queries": 0, "conversations": 0}
        
        timeline[bucket_key]["queries"] += 1
        if is_init:
            timeline[bucket_key]["conversations"] += 1

    # Sort by date
    sorted_keys = sorted(timeline.keys())
    labels = [k for k in sorted_keys]
    ds_queries = [timeline[k]["queries"] for k in sorted_keys]
    ds_conversations = [timeline[k]["conversations"] for k in sorted_keys]

    # 3. Category Distribution
    # --------------------------------------------------------------------------
    cat_data = db.query(
        QueryLog.category,
        func.count(QueryLog.id)
    ).filter(
        QueryLog.timestamp >= start_utc,
        QueryLog.timestamp <= end_utc
    ).group_by(QueryLog.category).all()
    
    # Normalization Map
    CAT_MAP = {
        "hardware": "Hardware/Device",
        "hardware/device": "Hardware/Device",
        "software": "Software/Application", 
        "software/application": "Software/Application",
        "network": "Network/Connectivity",
        "network/connectivity": "Network/Connectivity",
        "general question": "General Inquiry",
        "general inquiry": "General Inquiry",
        "billing": "Payment/Billing",
        "payment/billing": "Payment/Billing"
    }

    # Pre-fill ALL categories for legend (User Request)
    categories = {
        "Hardware/Device": 0,
        "Software/Application": 0,
        "Network/Connectivity": 0,
        "General Inquiry": 0,
        "Payment/Billing": 0,
        "Outage": 0,
        "Product Info": 0,
        "Payments": 0 # Legacy?
    }
    
    for cat, count in cat_data:
        if cat:
            norm_cat_key = cat.lower()
            final_cat = CAT_MAP.get(norm_cat_key, cat.title())
            categories[final_cat] = categories.get(final_cat, 0) + count

    # 4. Feedback Trends
    # --------------------------------------------------------------------------

    feedback_logs = db.query(FeedbackLog.timestamp, FeedbackLog.rating).filter(
        FeedbackLog.timestamp >= start_utc,
        FeedbackLog.timestamp <= end_utc
    ).all()
    
    # fb_timeline already pre-filled above

    for f_ts, rating in feedback_logs:
        if not f_ts: continue
        
        # FIX: SQLite Naive handling
        if f_ts.tzinfo is None:
            f_ts = f_ts.replace(tzinfo=timezone.utc)
            
        ts_est = f_ts.astimezone(EST)
        bucket_key = _truncate_date(ts_est, granularity)
        
        if bucket_key not in fb_timeline:
            fb_timeline[bucket_key] = {"pos": 0, "neg": 0}
        
        # FIX: Normalize rating value (SQLite may return strings even when stored as int)
        # Also handle legacy 'up'/'down' values that may exist in database
        normalized_rating = None
        if rating in [1, '1', 'up']:
            normalized_rating = 1
        elif rating in [-1, '-1', 'down']:
            normalized_rating = -1
        # 0 or any other value is ignored
        
        if normalized_rating == 1:
            fb_timeline[bucket_key]["pos"] += 1
        elif normalized_rating == -1:
            fb_timeline[bucket_key]["neg"] += 1

    # Align Feedback labels with main timeline or use its own?
    # Usually easier to use its own sparse keys or align.
    # Let's just sort its own keys.
    fb_sorted_keys = sorted(fb_timeline.keys())
    fb_labels = fb_sorted_keys
    ds_pos_count = []
    ds_neg_count = []

    # Return raw counts per hour (not percentages)
    for k in fb_sorted_keys:
        d = fb_timeline[k]
        ds_pos_count.append(d["pos"])
        ds_neg_count.append(d["neg"])

    return {
        "message_volume": {
            "labels": labels,
            "queries": ds_queries,
            "conversations": ds_conversations
        },
        "categories": categories,
        "feedback_trend": {
            "labels": fb_labels,
            "positive_count": ds_pos_count,
            "negative_count": ds_neg_count
        }
    }

def _truncate_date(dt, granularity):
    """Helper to truncate datetime to string bucket key."""
    if granularity == "hour":
        return dt.strftime("%Y-%m-%d %H:00")
    elif granularity == "day":
        return dt.strftime("%Y-%m-%d")
    elif granularity == "week":
        # Start of week (Monday)
        start = dt - timedelta(days=dt.weekday())
        return start.strftime("%Y-%m-%d")
    elif granularity == "month":
        return dt.strftime("%Y-%m")
    return dt.strftime("%Y-%m-%d")

@router.get("/spend")
def get_spend(
    range: str = Query(..., regex="^(today|week|month|year|custom)$"),
    start_date: str = None,
    end_date: str = None,
    db: Session = Depends(get_db)
):
    start_utc, end_utc, _ = _parse_range(range, start_date, end_date)

    # Token Stats
    token_stats = db.query(
        func.sum(QueryLog.input_tokens).label("input"),
        func.sum(QueryLog.output_tokens).label("output"),
        func.sum(QueryLog.embedding_tokens).label("embedding"),
        func.count(QueryLog.id).label("count")
    ).filter(
        QueryLog.timestamp >= start_utc,
        QueryLog.timestamp <= end_utc
    ).first()

    total_input = token_stats.input or 0
    total_output = token_stats.output or 0
    total_embed = token_stats.embedding or 0
    query_count = token_stats.count or 0

    # Costs
    cost_input = total_input * 0.00000015
    cost_output = total_output * 0.00000060
    token_cost = cost_input + cost_output

    # Other Expenses
    expense_stats = db.query(func.sum(ExpenseLog.amount)).filter(
        ExpenseLog.timestamp >= start_utc,
        ExpenseLog.timestamp <= end_utc
    ).scalar()
    
    other_cost = expense_stats or 0
    total_spend = token_cost + other_cost
    avg_per_query = (total_spend / query_count) if query_count > 0 else 0

    return {
        "total_spend": round(total_spend, 2),
        "avg_per_query": round(avg_per_query, 4),
        "token_cost": round(token_cost, 2),
        "other_expenses": round(other_cost, 2),
        "breakdown": {
            "queries": query_count,
            "input_tokens": total_input,
            "output_tokens": total_output,
            "embedding_tokens": total_embed
        }
    }

@router.get("/feedback")
def get_feedback(
    range: str = Query("today"),
    rating: int = Query(None, description="1 for positive, -1 for negative"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    search: str = None,
    start_date: str = None,
    end_date: str = None,
    db: Session = Depends(get_db)
):
    start_utc, end_utc, _ = _parse_range(range, start_date, end_date)
    
    query = db.query(FeedbackLog).filter(
        FeedbackLog.timestamp >= start_utc,
        FeedbackLog.timestamp <= end_utc
    )

    if rating is not None:
        query = query.filter(FeedbackLog.rating == rating)
    else:
        # Exclude 0 (none) by default if just listing?
        # Prompt says "Positive/Negative Count" separates them.
        # "Feedback Review Tabs" -> Positive (1), Negative (-1).
        # We'll allow filtering.
        pass

    if search:
        query = query.filter(FeedbackLog.user_query.ilike(f"%{search}%"))

    # Sorting
    query = query.order_by(desc(FeedbackLog.timestamp))

    total = query.count()
    items = query.offset((page - 1) * page_size).limit(page_size).all()

    return {
        "items": [
            {
                "id": i.id,
                "timestamp": i.timestamp.isoformat() if i.timestamp else None,
                "user_query": i.user_query,
                "bot_response": i.bot_response,
                "rating": i.rating
            } for i in items
        ],
        "total": total,
        "page": page,
        "pages": (total + page_size - 1) // page_size
    }

@router.get("/feedback/export")
def export_feedback(
    range: str = Query("today"),
    rating: int = None,
    start_date: str = None,
    end_date: str = None,
    db: Session = Depends(get_db)
):
    start_utc, end_utc, _ = _parse_range(range, start_date, end_date)
    
    query = db.query(FeedbackLog).filter(
        FeedbackLog.timestamp >= start_utc,
        FeedbackLog.timestamp <= end_utc
    ).order_by(desc(FeedbackLog.timestamp))

    if rating is not None:
        query = query.filter(FeedbackLog.rating == rating)
    
    # Limit max rows
    items = query.limit(10000).all()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["ID", "Timestamp (UTC)", "Rating", "User Query", "Bot Response"])

    for i in items:
        r_label = "Positive" if i.rating == 1 else "Negative" if i.rating == -1 else "None"
        writer.writerow([
            i.id,
            i.timestamp.isoformat() if i.timestamp else "",
            r_label,
            i.user_query or "",
            i.bot_response or ""
        ])
    
    output.seek(0)
    
    # Dynamic filename based on selected range (feedback logs only)
    filename = f"feedback_logs_{range}.csv"
    
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'}
    )

# 4. Alerts (Background Task)
# ------------------------------------------------------------------------------

def _send_alert_email(subject: str, body: str):
    sender = os.getenv("ADMIN_EMAIL", "jhamilton831@gmail.com")
    recipient = sender # Alert to admin
    
    # SMTP Config - Expected in Env
    smtp_server = os.getenv("SMTP_SERVER", "email-smtp.us-east-1.amazonaws.com")
    smtp_port = int(os.getenv("SMTP_PORT", "587"))
    smtp_user = os.getenv("SMTP_USERNAME", "")
    smtp_pass = os.getenv("SMTP_PASSWORD", "")

    if not smtp_user or not smtp_pass:
        print(f"Skipping email alert (no credentials): {subject}")
        return

    msg = MIMEText(body)
    msg["Subject"] = f"[JUNA ALERT] {subject}"
    msg["From"] = sender
    msg["To"] = recipient

    try:
        with smtplib.SMTP(smtp_server, smtp_port) as server:
            server.starttls()
            server.login(smtp_user, smtp_pass)
            server.sendmail(sender, [recipient], msg.as_string())
    except Exception as e:
        print(f"Failed to send email alert: {e}")

@router.post("/run-alert-check")
def run_alert_check(background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    """
    Checks for:
    1. > 20 queries in last 5 minutes
    2. > 20% negative feedback in last hour
    """
    now = datetime.now(timezone.utc)
    
    # 1. Query Spike
    five_min_ago = now - timedelta(minutes=5)
    query_count = db.query(QueryLog).filter(QueryLog.timestamp >= five_min_ago).count()
    
    if query_count > 20:
        background_tasks.add_task(
            _send_alert_email, 
            "High Query Volume Detected", 
            f"Alert: {query_count} queries detected in the last 5 minutes (Threshold: 20)."
        )

    # 2. Negative Feedback Spike
    one_hour_ago = now - timedelta(hours=1)
    # Get recent feedback
    recent_fb = db.query(FeedbackLog).filter(
        FeedbackLog.timestamp >= one_hour_ago,
        FeedbackLog.rating.in_([1, -1]) # Ignore 0
    ).all()
    
    total = len(recent_fb)
    if total > 5: # Minimum sample size to avoid noise
        neg = sum(1 for f in recent_fb if f.rating == -1)
        rate = (neg / total) * 100
        if rate > 20:
             background_tasks.add_task(
                _send_alert_email, 
                "Negative Feedback Spike", 
                f"Alert: Negative feedback rate is {rate:.1f}% in the last hour (Threshold: 20%). Total feedback: {total}."
            )

    return {"status": "checked", "query_count_5min": query_count, "feedback_count_1hr": total}
