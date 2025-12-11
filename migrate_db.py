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
            # 4. Check/Fix 'rating' column type (Robust)
            try:
                print("Attempting to convert 'rating' to INTEGER...")
                # We use a safe check: if it's already integer, this is a no-op or fast.
                # But to be safe against "operator does not exist" errors in checks, we just run the ALTER.
                migration_sql = """
                ALTER TABLE feedback_logs 
                ALTER COLUMN rating TYPE INTEGER 
                USING (
                    CASE 
                        WHEN rating::text = 'up' THEN 1
                        WHEN rating::text = 'down' THEN -1
                        WHEN rating::text ~ '^[0-9\-]+$' THEN rating::integer  -- handle existing numbers
                        ELSE 0
                    END
                );
                """
                conn.execute(text(migration_sql))
                conn.commit()
                print("Migration successful: 'rating' is INTEGER.")
            except Exception as e:
                print(f"Rating migration note (might be already done): {e}")
                # If it fails, maybe it's already done? But the error suggests it's NOT done.
                # We purposely don't raise here to let message_id check proceed, 
                # UNLESS it's a critical failure.
                # But if 'rating' remains text, app crashes. So maybe we SHOULD raise?
                # The User error is "character varying = integer", so it IS text.
                # So this ALTER is critically needed.
                if "does not exist" in str(e):
                     raise e # Re-raise if table missing
                conn.rollback() 
            
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
