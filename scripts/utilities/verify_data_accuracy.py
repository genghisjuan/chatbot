from sqlalchemy import create_engine, Column, Integer, String, DateTime
from sqlalchemy.orm import sessionmaker, declarative_base
from datetime import datetime, timedelta
import sys

# Database Setup
DATABASE_URL = "sqlite:///./analytics.db"
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()

class QueryLog(Base):
    __tablename__ = 'query_logs'
    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime, default=datetime.utcnow)
    message = Column(String)
    category = Column(String)
    is_initial = Column(Integer, default=0)
    is_fallback = Column(Integer, default=0)

def inject_data():
    session = SessionLocal()
    try:
        now = datetime.utcnow()
        print(f"Injecting test data at UTC: {now}")
        
        # 5 queries at CURRENT HOUR (UTC)
        for _ in range(5):
            log = QueryLog(
                timestamp=now,
                message="Test Query Verification Current",
                category="Billing",
                is_initial=1
            )
            session.add(log)
            
        # 3 queries at PREVIOUS HOUR (UTC)
        prev_hour = now - timedelta(hours=1)
        for _ in range(3):
            log = QueryLog(
                timestamp=prev_hour,
                message="Test Query Verification Previous",
                category="Technical",
                is_initial=1
            )
            session.add(log)
            
        session.commit()
        print("Injection Complete.")
    except Exception as e:
        print(f"Error: {e}")
        session.rollback()
    finally:
        session.close()

def cleanup_data():
    session = SessionLocal()
    try:
        count = session.query(QueryLog).filter(QueryLog.message.like("Test Query Verification%")).delete(synchronize_session=False)
        session.commit()
        print(f"Cleanup Complete. Deleted {count} rows.")
    except Exception as e:
        print(f"Error: {e}")
        session.rollback()
    finally:
        session.close()

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "clean":
        cleanup_data()
    else:
        inject_data()
