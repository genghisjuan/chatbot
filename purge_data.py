import os
import sys
from sqlalchemy import create_engine, text
from app.core.config import settings

def purge_data():
    """
    Purges all data from analytics tables to provide a blank slate.
    """
    print("WARNING: This will DELETE ALL DATA from the following tables:")
    print(" - query_logs")
    print(" - feedback_logs")
    print(" - expense_logs")
    print(" - escalation_logs")
    
    confirm = input("Are you sure you want to proceed? (type 'yes' to confirm): ")
    if confirm.lower() != 'yes':
        print("Operation cancelled.")
        return

    db_url = settings.DATABASE_URL
    if not db_url:
        print("Error: DATABASE_URL environment variable is not set.")
        return

    # Fix postgres protocol if needed
    if db_url.startswith("postgres://"):
        db_url = db_url.replace("postgres://", "postgresql://", 1)

    try:
        engine = create_engine(db_url)
        print(f"Connecting to database: {engine.dialect.name}...")

        with engine.connect() as connection:
            if engine.dialect.name == 'sqlite':
                print("Detected SQLite. Using DELETE instead of TRUNCATE...")
                with connection.begin():
                    # SQLite doesn't support TRUNCATE
                    connection.execute(text("DELETE FROM query_logs;"))
                    connection.execute(text("DELETE FROM feedback_logs;"))
                    connection.execute(text("DELETE FROM expense_logs;"))
                    connection.execute(text("DELETE FROM escalation_logs;"))
                    
                    # Reset auto-increment counters (safe ignore if table doesn't exist yet)
                    try:
                        connection.execute(text("DELETE FROM sqlite_sequence WHERE name IN ('query_logs', 'feedback_logs', 'expense_logs', 'escalation_logs');"))
                    except Exception as e:
                        print(f"Note: Could not reset sequences (sqlite_sequence might not exist). This is harmless. Error: {e}")
            else:
                # PostgreSQL
                print("Detected PostgreSQL. Using TRUNCATE...")
                with connection.begin():
                    # TRUNCATE tables
                    # RESTART IDENTITY resets auto-increment IDs to 1
                    # CASCADE handles any foreign key constraints
                    sql = text("""
                        TRUNCATE TABLE query_logs, feedback_logs, expense_logs, escalation_logs 
                        RESTART IDENTITY CASCADE;
                    """)
                    connection.execute(sql)
            
            print("✅ Data purge successful. Tables are empty.")
            
    except Exception as e:
        print(f"❌ Error during purge: {e}")
        sys.exit(1)

if __name__ == "__main__":
    purge_data()
