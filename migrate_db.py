import os
import sys
from sqlalchemy import create_engine, text

# Add parent dir to path to import settings if needed, 
# but we prefer direct env var for scripts to limit dependencies
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def migrate():
    # 1. Get DB URL
    url = os.getenv("DATABASE_URL")
    if not url:
        print("Error: DATABASE_URL environment variable not set.")
        return

    # Fix schema if needed (postgres:// -> postgresql://)
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)

    print(f"Connecting to database...")
    engine = create_engine(url)

    # 2. Check current state
    check_sql = text("SELECT data_type FROM information_schema.columns WHERE table_name = 'feedback_logs' AND column_name = 'rating'")

    # 3. Execute
    try:
        with engine.connect() as conn:
            result = conn.execute(check_sql)
            row = result.fetchone()
            
            if row and row[0].lower() == 'integer':
                print("Column 'rating' is already INTEGER. Migration skipped.")
                return

            print("Column type is " + (str(row[0]) if row else "unknown") + ". Running migration...")
            
            # 4. Define Migration SQL
            migration_sql = """
            ALTER TABLE feedback_logs 
            ALTER COLUMN rating TYPE INTEGER 
            USING (
                CASE 
                    WHEN rating = 'up' THEN 1
                    WHEN rating = 'down' THEN -1
                    ELSE 0
                END
            );
            """
            
            conn.execute(text(migration_sql))
            conn.commit()
            print("Migration successful! Column 'rating' is now INTEGER.")
            
            # 5. Check/Add message_id column
            check_msg_id = text("SELECT 1 FROM information_schema.columns WHERE table_name = 'feedback_logs' AND column_name = 'message_id'")
            result_col = conn.execute(check_msg_id)
            if not result_col.fetchone():
                print("Column 'message_id' missing. Adding it...")
                conn.execute(text("ALTER TABLE feedback_logs ADD COLUMN message_id TEXT"))
                conn.execute(text("CREATE INDEX IF NOT EXISTS ix_feedback_logs_message_id ON feedback_logs (message_id)"))
                conn.commit()
                print("Added 'message_id' column.")
            else:
                print("Column 'message_id' already exists.")

    except Exception as e:
        print(f"Migration failed dict: {e}")

if __name__ == "__main__":
    migrate()
