from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks
from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy import create_engine, func, desc, case, text
from sqlalchemy.orm import sessionmaker, Session
from app.core.config import settings
from app.services.analytics import QueryLog, FeedbackLog, EscalationLog, ExpenseLog
import os
import csv
import io
from datetime import datetime, timedelta
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
        EscalationLog.type == 'phone'
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
        "avg_queries_per_conversation": round(avg_qpc, 1),
        "period_start": start_utc.isoformat(),
        "period_end": end_utc.isoformat()
    }

@router.get("/trends")
def get_trends(
    range: str = Query(..., regex="^(today|week|month|year|custom)$"),
    start_date: str = None,
    end_date: str = None,
    db: Session = Depends(get_db)
):
    start_utc, end_utc, granularity = _parse_range(range, start_date, end_date)

    # Helper for date truncation in UTC -> EST conversion
    # We want buckets in EST. 
    # PostgreSQL: date_trunc(granularity, timestamp AT TIME ZONE 'UTC' AT TIME ZONE 'America/New_York')
    # But SQLAlchemy 'func.timezone' logic is DB specific. 
    # For safety with PostgreSQL:
    # timestamp is stored as TIMESTAMPTZ (UTC).
    # We convert to EST then truncate.
    
    ts_col = QueryLog.timestamp
    # Convert UTC timestamp column to EST for bucketing
    ts_est = func.timezone('America/New_York', ts_col)
    
    bucket = func.date_trunc(granularity, ts_est).label("bucket")
    
    # 1. Conversations & Queries Over Time
    # Group by EST bucket
    data_points = db.query(
        bucket,
        func.count(QueryLog.id).label("queries"),
        func.sum(case((QueryLog.is_initial == 1, 1), else_=0)).label("conversations")
    ).filter(
        QueryLog.timestamp >= start_utc,
        QueryLog.timestamp <= end_utc
    ).group_by("bucket").order_by("bucket").all()

    # Format for chart (labels, datasets)
    labels = []
    ds_queries = []
    ds_conversations = []

    for row in data_points:
        # row.bucket is naive datetime (EST)
        labels.append(row.bucket.isoformat())
        ds_queries.append(row.queries)
        ds_conversations.append(row.conversations or 0) # sum can be null

    # 2. Category Distribution
    cat_data = db.query(
        QueryLog.category,
        func.count(QueryLog.id)
    ).filter(
        QueryLog.timestamp >= start_utc,
        QueryLog.timestamp <= end_utc
    ).group_by(QueryLog.category).all()
    
    categories = {
        "hardware": 0, "software": 0, "network": 0, "outage": 0, 
        "general question": 0, "billing": 0, "product info": 0, "payments": 0
    }
    # Fill actuals
    for cat, count in cat_data:
        if cat: # handle None
            norm_cat = cat.lower()
            if norm_cat in categories:
                categories[norm_cat] = count
            else:
                # Group 'other' strategies if needed, or just add
                categories[cat] = count

    # 3. Feedback Rates Over Time
    fb_ts_est = func.timezone('America/New_York', FeedbackLog.timestamp)
    fb_bucket = func.date_trunc(granularity, fb_ts_est).label("bucket")
    
    fb_data = db.query(
        fb_bucket,
        func.sum(case((FeedbackLog.rating == 1, 1), else_=0)).label("pos"),
        func.sum(case((FeedbackLog.rating == -1, 1), else_=0)).label("neg")
    ).filter(
        FeedbackLog.timestamp >= start_utc,
        FeedbackLog.timestamp <= end_utc
    ).group_by("bucket").order_by("bucket").all()

    fb_labels = []
    ds_pos_rate = []
    ds_neg_rate = []

    for row in fb_data:
        fb_labels.append(row.bucket.isoformat())
        total = (row.pos or 0) + (row.neg or 0)
        p = ((row.pos or 0) / total * 100) if total > 0 else 0
        n = ((row.neg or 0) / total * 100) if total > 0 else 0
        ds_pos_rate.append(round(p, 1))
        ds_neg_rate.append(round(n, 1))

    return {
        "message_volume": {
            "labels": labels,
            "queries": ds_queries,
            "conversations": ds_conversations
        },
        "categories": categories,
        "feedback_trend": {
            "labels": fb_labels,
            "positive_rate": ds_pos_rate,
            "negative_rate": ds_neg_rate
        }
    }

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
            i.user_query,
            i.bot_response
        ])
    
    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=feedback_export.csv"}
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
