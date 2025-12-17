import sys
import os
import datetime
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Add app to path
sys.path.append(os.getcwd())

from app.services.analytics import QueryLog, FeedbackLog, Base
from app.core.config import settings
from app.api.admin import run_alert_check

# Mock BackgroundTasks
class MockBackgroundTasks:
    def add_task(self, func, *args, **kwargs):
        print(f"\n[TEST] ALERT TRIGGERED!")
        print(f"[TEST] Function: {func.__name__}")
        print(f"[TEST] Subject: {args[0]}")
        print(f"[TEST] Body: {args[1]}")
        print("-" * 50)
        # We don't actually need to send email for this test, just knowing it triggered is enough.

def test_alerts():
    print("Initializing DB connection...")
    engine = create_engine(settings.DATABASE_URL)
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()

    try:
        now = datetime.datetime.now(datetime.timezone.utc)
        print(f"Current UTC time: {now}")

        # 1. Test High Query Volume (>20 in 5 min)
        print("\n--- Testing High Query Volume ---")
        print("Injecting 25 queries in the last 2 minutes...")
        
        queries = []
        for i in range(25):
            q = QueryLog(
                message=f"Test query {i}",
                input_tokens=10,
                output_tokens=10,
                timestamp=now - datetime.timedelta(minutes=1)
            )
            queries.append(q)
        
        db.add_all(queries)
        db.commit()
        print("Data injected.")

        # Run Check
        print("Running alert check...")
        bg_tasks = MockBackgroundTasks()
        run_alert_check(bg_tasks, db)


        # 2. Test Negative Feedback Spike (>20% in 1 hour)
        print("\n--- Testing Negative Feedback Spike ---")
        print("Injecting feedback entries (3 negative, 3 positive)...")
        
        feedbacks = []
        # 3 Negative
        for i in range(3):
            f = FeedbackLog(
                user_query="bad query",
                bot_response="bad response",
                rating=-1,
                timestamp=now - datetime.timedelta(minutes=30)
            )
            feedbacks.append(f)
        # 3 Positive
        for i in range(3):
            f = FeedbackLog(
                user_query="good query",
                bot_response="good response",
                rating=1,
                timestamp=now - datetime.timedelta(minutes=30)
            )
            feedbacks.append(f)
            
        db.add_all(feedbacks)
        db.commit()
        print("Data injected (50% negative rate).")

        # Run Check
        print("Running alert check...")
        run_alert_check(bg_tasks, db)

    except Exception as e:
        print(f"Test failed: {e}")
    finally:
        # Cleanup (Optional: remove the test data)
        # db.query(QueryLog).filter(QueryLog.message.like("Test query%")).delete(synchronize_session=False)
        # db.query(FeedbackLog).filter(FeedbackLog.user_query.in_(["bad query", "good query"])).delete(synchronize_session=False)
        # db.commit()
        db.close()
        print("\nTest completed.")

if __name__ == "__main__":
    test_alerts()
