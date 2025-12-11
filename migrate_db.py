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

    # 2. Define Migration SQL
    # We need to:
    # a) Convert 'up' to 1
    # b) Convert 'down' to -1
    # c) Handle NULL or others -> 0 (or leave null? prompted said "0=no feedback")
    # d) Change column type to INTEGER
    
    # PostgreSQL allows "USING" clause for type conversion
    migration_sql = """
    ALTER TABLE feedback_logs 
    ALTER COLUMN rating TYPE INTEGER 
    USING (
        CASE 
            WHEN rating = 'up' THEN 1
            WHEN rating = 'down' THEN -1
            WHEN rating IS NULL THEN 0
            ELSE 0
        END
    );
    """

    # 3. Execute
    try:
        with engine.connect() as conn:
            print("Running migration...")
            conn.execute(text(migration_sql))
            conn.commit()
            print("Migration successful! Column 'rating' is now INTEGER.")
    except Exception as e:
        print(f"Migration failed: {e}")

if __name__ == "__main__":
    migrate()
