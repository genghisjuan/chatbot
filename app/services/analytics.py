"""
Analytics Service for Query Tracking and Trending Topics.

This module provides functionality to log user queries, categorize them using LLM,
and calculate trending topics over time periods.
"""
from sqlalchemy import create_engine, Column, Integer, String, DateTime, Float, func, text
from sqlalchemy.orm import sessionmaker, declarative_base, Session
import datetime
from typing import List, Tuple, Optional
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage
from app.core.config import settings
import asyncio
import json
import logging
from app.services import logger as service_logger

logger = logging.getLogger(__name__)

Base = declarative_base()


class QueryLog(Base):
    """
    Database model for storing user query logs.
    
    Attributes:
        id: Primary key auto-increment
        timestamp: When the query was made (UTC)
        message: The actual query text
        category: LLM-assigned category
        input_tokens: Estimated input tokens (for cost tracking)
        output_tokens: Estimated output tokens (for cost tracking)
    """
    __tablename__ = 'query_logs'

    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime, default=datetime.datetime.utcnow)
    message = Column(String)
    category = Column(String)
    is_initial = Column(Integer, default=0) # 0=False, 1=True
    is_fallback = Column(Integer, default=0) # 0=False, 1=True (Low confidence/I don't know)
    input_tokens = Column(Integer, default=0)
    output_tokens = Column(Integer, default=0)
    embedding_tokens = Column(Integer, default=0)


class FeedbackLog(Base):
    """
    Database model for storing user feedback on bot responses.
    
    Attributes:
        id: Primary key auto-increment
        timestamp: When the feedback was given (UTC)
        user_query: The user's original question
        bot_response: The bot's response text
        rating: 'up' or 'down'
    """
    __tablename__ = 'feedback_logs'

    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime, default=datetime.datetime.utcnow)
    user_query = Column(String)
    bot_response = Column(String)
    rating = Column(String)  # 'up' or 'down'

class ExpenseLog(Base):
    """
    Database model for manual/miscellaneous expenses.
    """
    __tablename__ = 'expense_logs'

    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime, default=datetime.datetime.utcnow)
    category = Column(String) # 'manual', 'tts', 'embedding_ingestion'
    description = Column(String)
    amount = Column(Float) # Cost in USD



class EscalationLog(Base):
    """
    Database model for storing escalation usage (Human Handoff).

    Attributes:
        type: 'email', 'callback', 'call-inbound'
    """
    __tablename__ = 'escalation_logs'
    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime, default=datetime.datetime.utcnow)
    type = Column(String)


class AnalyticsService:
    """
    Service for logging and analyzing user queries.
    
    This service:
    1. Logs all user queries to the database
    2. Uses OpenAI LLM to categorize queries into support topics
    3. Calculates trending topics based on recent query frequency
    
    Supports both SQLite (local) and PostgreSQL (production) via SQLAlchemy.
    
    Attributes:
        engine: SQLAlchemy database engine
        SessionLocal: Session factory for database connections
    """
    
    # Valid query categories for classification
    VALID_CATEGORIES = [
        "Printer Issues",
        "Network/Connectivity",
        "Software/Application",
        "Account/Login",
        "Hardware/Device",
        "Payment/Billing",
        "General Inquiry"
    ]

    SYSTEM_PROMPT_TRENDS = """
    You are an expert support analyst for 'onePOS'.
    Analyze the following user queries (some have higher weights due to recency).
    
    Your Goal: Identify the TOP 5 most significant, specific support issues trending right now.
    
    Guidelines:
    1. Group synonyms (e.g., "printer offline", "printer not printing" -> "Printer Issues – SNBC/Epson").
    2. CRITICAL: Distinguish between ISSUES (broken, error, failed) and HOW-TO (how do I, guide, training).
       - "How to run EOD" -> "How to Run End of Day" (NOT a failure).
       - "EOD failed" -> "End of Day Failure".
    3. Be specific. "Hardware Issue" is bad. "KDS Controller Offline" is good.
    4. Ignore generic noise like "hello", "help", "test".
    5. Return EXACTLY 5 topics if possible, ranked by significance (volume * weight).
    
    GOLDEN TOPICS (Map to these if applicable, otherwise create new specific ones):
    - KDS Offline / Not Receiving Orders
    - Printer Issues – SNBC/Epson
    - Credit Card Reader Offline (Hardware Issue)
    - Credit Card Processing Down (Gateway/Network Issue)
    - Menu Item Not Showing on POS
    - Employee Login Failed / Locked Out
    - End of Day / Batch Settlement Failed
    - How to Run End of Day (Training)
    - Modifiers Not Printing in Kitchen
    
    Output JSON format ONLY:
    {
        "topics": [
            {
                "label": "Topic Label",
                "count": estimated_weighted_count,
                "prompt": "Phrase this as a natural FIRST-PERSON USER QUESTION. Examples: 'How do I run end of day?', 'My printer is offline, how do I fix it?', 'I forgot my password'. Do NOT use titles like 'Printer Fix'."
            }
        ]
    }
    """
    
    def __init__(self) -> None:
        """
        Initialize the analytics service.
        
        Creates database connection and initializes tables if they don't exist.
        """
        self.engine = create_engine(settings.DATABASE_URL)
        self.SessionLocal = sessionmaker(
            autocommit=False,
            autoflush=False,
            bind=self.engine
        )
        self._init_db()
        
        # Simple in-memory cache for trending topics
        self._trending_cache: Optional[List[dict]] = None
        self._last_cache_update: Optional[datetime.datetime] = None
        self._cache_ttl_minutes = 1 # Reduced for testing
        self._cache_lock = asyncio.Lock()
        
        self.DEFAULT_TRENDS = [
            {"label": "Printer Issues", "count": 1, "prompt": "My printer is offline, how do I fix it?"},
            {"label": "KDS Orders Missing", "count": 1, "prompt": "My KDS screen is not showing any orders."},
            {"label": "Credit Card Reader Fail", "count": 1, "prompt": "My credit card reader won't take payments."},
            {"label": "Login Failed", "count": 1, "prompt": "I cannot log in to the POS system."},
            {"label": "End of Day Failed", "count": 1, "prompt": "My end of day batch settlement failed."}
        ]

    def _init_db(self) -> None:
        """Create database tables if they don't exist."""
        Base.metadata.create_all(bind=self.engine)

    def categorize_query(self, message: str) -> str:
        """
        Categorize a user query using OpenAI LLM.
        """
        # Fallback if no API key configured
        if settings.OPENAI_API_KEY == "changeme":
            return "General Inquiry"

        try:
            llm = ChatOpenAI(
                api_key=settings.OPENAI_API_KEY,
                model="gpt-4o",
                temperature=0  # Deterministic classification
            )
            
            messages = [
                SystemMessage(content=f"""
                    You are a classification assistant. 
                    Categorize the following support query into one of these high-level topics:
                    {chr(10).join('- ' + cat for cat in self.VALID_CATEGORIES)}
                    
                    Return ONLY the category name. If it doesn't fit, return "General Inquiry".
                """),
                HumanMessage(content=message)
            ]
            
            response = llm.invoke(messages)
            category = response.content.strip()
            
            # Validate category
            if category not in self.VALID_CATEGORIES:
                return "General Inquiry"
                
            return category
            
        except Exception as e:
            logger.error(f"Error categorizing query: {e}")
            return "General Inquiry"

    def log_query(self, message: str, is_initial: bool = False, is_fallback: bool = False, 
                  input_tokens: int = 0, output_tokens: int = 0, embedding_tokens: int = 0) -> None:
        """
        Log a user query to the database with automatic categorization.
        
        Args:
            message: The user's query text
            is_initial: Whether this is the first message in a conversation
            is_fallback: Whether the response was low confidence
            input_tokens: Estimated input tokens for cost tracking
            output_tokens: Estimated output tokens for cost tracking
            embedding_tokens: Estimated embedding tokens (RAG)
        """
        # Define the process to run in the background
        def _process_and_save():
            category = "General Inquiry"
            try:
                category = self.categorize_query(message)
            except Exception:
                 # categorize_query handles its own errors, but extra safety
                pass
                
            db: Session = self.SessionLocal()
            try:
                log_entry = QueryLog(
                    message=message, 
                    category=category, 
                    is_initial=1 if is_initial else 0,
                    is_fallback=1 if is_fallback else 0,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    embedding_tokens=embedding_tokens
                )
                db.add(log_entry)
                db.commit()
            except Exception as e:
                logger.error(f"Failed to save query log: {e}")
            finally:
                db.close()
                
        # Fire and forget on the loop to avoid blocking main thread with sync operations (LLM + DB)
        try:
            loop = asyncio.get_running_loop()
            if loop.is_running():
                loop.run_in_executor(None, _process_and_save)
            else:
                _process_and_save()
        except RuntimeError:
            _process_and_save()

    def log_expense(self, category: str, description: str, amount: float, timestamp: datetime.datetime = None) -> None:
        """
        Log a manual/miscellaneous expense.
        """
        db: Session = self.SessionLocal()
        try:
            log_entry = ExpenseLog(
                category=category,
                description=description,
                amount=amount,
                timestamp=timestamp or datetime.datetime.utcnow()
            )
            db.add(log_entry)
            db.commit()
        finally:
            db.close()

    def log_escalation(self, type: str) -> None:
        """
        Log an escalation event (e.g., call, email).
        """
        # Define internal sync save function
        def _save_escalation():
            db: Session = self.SessionLocal()
            try:
                log_entry = EscalationLog(type=type)
                db.add(log_entry)
                db.commit()
            except Exception as e:
                logger.error(f"Failed to save escalation log: {e}")
            finally:
                db.close()

        # Fire and forget
        try:
            loop = asyncio.get_running_loop()
            if loop.is_running():
                loop.run_in_executor(None, _save_escalation)
            else:
                _save_escalation()
        except RuntimeError:
            _save_escalation()

    def get_category_distribution(self, days: int = 30) -> List[dict]:
        """
        Get the distribution of query categories for a time period.
        """
        db: Session = self.SessionLocal()
        try:
            cutoff = datetime.datetime.utcnow() - datetime.timedelta(days=days)
            results = db.query(QueryLog.category, func.count(QueryLog.category))\
                .filter(QueryLog.timestamp >= cutoff)\
                .group_by(QueryLog.category).all()
            
            return [{"category": r[0], "count": r[1]} for r in results]
        finally:
            db.close()

    def log_feedback(self, user_query: str, bot_response: str, rating: str) -> None:
        """
        Log user feedback on a bot response to the database.
        
        Args:
            user_query: The user's original question
            bot_response: The bot's response text
            rating: 'up' or 'down'
        """
        # Define internal sync save function
        def _save_feedback():
            db: Session = self.SessionLocal()
            try:
                log_entry = FeedbackLog(
                    user_query=user_query,
                    bot_response=bot_response,
                    rating=rating
                )
                db.add(log_entry)
                db.commit()
            except Exception as e:
                logger.error(f"Failed to save feedback log: {e}")
            finally:
                db.close()

        # Fire and forget
        try:
            loop = asyncio.get_running_loop()
            if loop.is_running():
                loop.run_in_executor(None, _save_feedback)
            else:
                _save_feedback()
        except RuntimeError:
            _save_feedback()

    async def _generate_smart_trends(self, queries: List[Tuple[str, float]]) -> List[dict]:
        """
        Use LLM to cluster raw queries into specific, actionable trending topics.
        """
        logger.debug(f"Generating smart trends for {len(queries)} queries...")
        if not queries or settings.OPENAI_API_KEY == "changeme":
            logger.debug("No queries or API key missing. Returning DEFAULT trends.")
            # Basic defaults if no data
            return self.DEFAULT_TRENDS

        try:
            llm = ChatOpenAI(
                api_key=settings.OPENAI_API_KEY,
                model="gpt-4o",
                temperature=0
            )

            # Prepare query list for prompt
            query_text = "\n".join([f"- {q[0]} (Weight: {q[1]:.1f})" for q in queries])

            messages = [
                SystemMessage(content=self.SYSTEM_PROMPT_TRENDS),
                HumanMessage(content=f"Here are the recent queries:\n{query_text}")
            ]

            response = await llm.ainvoke(messages)
            
            # Parse JSON
            content = response.content.replace('```json', '').replace('```', '').strip()
            logger.debug(f"LLM Response: {content[:100]}...")
            data = json.loads(content)
            topics = data.get("topics", [])
            
            # --- PADDING: Ensure we always have 5 topics ---
            # If LLM returns fewer than 5 (because of low traffic), pad with defaults
            defaults = self.DEFAULT_TRENDS
            
            # Add defaults if they don't duplicate existing labels
            existing_labels = {t['label'].lower() for t in topics}
            
            for d in defaults:
                if len(topics) >= 5:
                    break
                # Simple fuzzy check (if "Printer" is already there, skip "Printer Issues")
                is_duplicate = False
                for existing in existing_labels:
                    if d['label'].split(' ')[0].lower() in existing: 
                        is_duplicate = True
                        break
                
                if not is_duplicate:
                    topics.append(d)
                    
            return topics

        except Exception as e:
            logger.error(f"Error generating smart trends: {e}", exc_info=True)
            return []

    async def get_trending_topics(self, hours: int = 720) -> List[dict]:
        """
        Get smart trending topics using weighted scoring and LLM clustering.
        Defaults to last 30 days (720 hours) to capture full history during testing.
        Returns a list of dicts: {label, count, prompt}
        """
        # Check cache (1 minute TTL for near real-time)
        # Use async lock to prevent race condition on cache regeneration
        async with self._cache_lock:
            if self._trending_cache and self._last_cache_update:
                if datetime.datetime.utcnow() - self._last_cache_update < datetime.timedelta(minutes=self._cache_ttl_minutes):
                    return self._trending_cache

            # If cache miss, generate new trends (still under lock to prevent thundering herd)
            # Note: This holds the lock during DB query and LLM call. 
            # Ideally we'd optimize to allow reading old cache while updating, 
            # but simple lock is safer for now.
            
            db: Session = self.SessionLocal()
        try:
            cutoff = datetime.datetime.utcnow() - datetime.timedelta(hours=hours)
            
            # Fetch raw queries - ONLY INITIAL queries
            raw_logs = db.query(QueryLog.message, QueryLog.timestamp).filter(
                QueryLog.timestamp >= cutoff,
                QueryLog.is_initial == 1
            ).order_by(QueryLog.timestamp.desc()).limit(200).all()

            if not raw_logs:
                logger.debug("No raw logs found.")
                # Return empty or defaults? Using empty to signify no data.
                # Logic below handles generation, if no raw logs, we used to return [].
                return []

            # Apply Weighted Scoring
            weighted_queries = []
            now = datetime.datetime.utcnow()
            
            for log in raw_logs:
                age = (now - log.timestamp).total_seconds() / 3600
                weight = 1.0
                if age < 4:
                    weight = 3.0
                elif age < 12:
                    weight = 2.0
                
                weighted_queries.append((log.message, weight))

            # Generate smart trends
            smart_trends = await self._generate_smart_trends(weighted_queries)
            
            if smart_trends:
                self._trending_cache = smart_trends
                self._last_cache_update = datetime.datetime.utcnow()
                return smart_trends
            
            return []
        finally:
            db.close()
