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
    check_sql = text("SELECT data_type FROM information_schema.columns WHERE table_name = 'feedback_logs' AND column_name = 'rating' AND table_schema = 'public'")

    # 3. Execute
    try:
        with engine.connect() as conn:
            result = conn.execute(check_sql)
            row = result.fetchone()
            
            if row and row[0].lower() == 'integer':
                print("Column 'rating' is already INTEGER. Migration skipped.")
                # Proceed to next check (don't return yet)
            else:
                print("Column type is " + (str(row[0]) if row else "unknown") + ". Running rating migration...")
                
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
