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

    # 3. Execute
    try:
        with engine.connect() as conn:
            # 4. Check/Fix 'rating' column type (Robust - Fail Fast)
            print("Attempting to convert 'rating' to INTEGER...")
            migration_sql = """
            ALTER TABLE feedback_logs 
            ALTER COLUMN rating TYPE INTEGER 
            USING (
                CASE 
                    WHEN rating::text = 'up' THEN 1
                    WHEN rating::text = 'down' THEN -1
                    WHEN rating::text ~ '^[0-9\-]+$' THEN rating::integer
                    ELSE 0
                END
            );
            """
            conn.execute(text(migration_sql))
            conn.commit()
            print("Migration successful: 'rating' is INTEGER.") 
            
            # 5. Check/Add message_id column (Robust)
            try:
                print("Attempting to ensure 'message_id' column exists...")
                conn.execute(text("ALTER TABLE feedback_logs ADD COLUMN IF NOT EXISTS message_id TEXT"))
                conn.execute(text("CREATE INDEX IF NOT EXISTS ix_feedback_logs_message_id ON feedback_logs (message_id)"))
                conn.commit()
                print("Verified 'message_id' column.")
            except Exception as e:
                print(f"Warning adding message_id: {e}")
                # Don't fail hard here if it's just a duplicate issue that IF NOT EXISTS missed (unlikely)
                raise e

    except Exception as e:
        print(f"Migration failed dict: {e}")
        import sys
        sys.exit(1)

if __name__ == "__main__":
    migrate()
