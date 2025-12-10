
import logging
import os
import asyncio
import datetime
import secrets
from typing import List, Optional
from app.schemas import Message
from app.core.config import settings
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage

logger = logging.getLogger(__name__)

class EmailService:
    # Constants
    LLM_MODEL = "gpt-4o"
    MAX_SUBJECT_LENGTH = 50
    
    # Establish a safe data directory relative to the project root or user home
    BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    DATA_DIR = os.path.join(BASE_DIR, "data", "email_service")

    def __init__(self):
        # Allow override via settings, fallback to hardcoded for now if not in settings
        self.recipient = getattr(settings, "SUPPORT_EMAIL", "jhamilton831@gmail.com")
        
        # Ensure data directory exists for email storage (demo mode)
        os.makedirs(self.DATA_DIR, exist_ok=True)
        self.emails_dir = os.path.join(self.DATA_DIR, "emails")

    async def _get_next_ticket_id(self) -> str:
        """Generates a unique ticket ID based on timestamp and random suffix."""
        # Format: #YYYYMMDD-HHMM-RAND (e.g., #20231209-0130-A1B2)
        now = datetime.datetime.now().strftime("%Y%m%d-%H%M")
        suffix = secrets.token_hex(2).upper()
        return f"#{now}-{suffix}"

    async def _generate_chat_summary(self, history: List[Message]) -> str:
        """Uses LLM to generate a concise summary of the chat."""
        if not history or settings.OPENAI_API_KEY == "changeme":
            return "No conversation history available or API key missing."

        try:
            llm = ChatOpenAI(api_key=settings.OPENAI_API_KEY, model=self.LLM_MODEL, temperature=0.3)
            
            conversation_text = "\n".join([f"{msg.role}: {msg.content}" for msg in history])
            
            messages = [
                SystemMessage(content="You are a support ticket assistant. Summarize the following conversation in 2-3 sentences for a support agent. Focus on the core issue and any troubleshooting steps already attempted."),
                HumanMessage(content=f"Conversation:\n{conversation_text}")
            ]
            
            response = await llm.ainvoke(messages)
            return response.content
        except Exception as e:
            logger.error(f"Error generating summary: {e}")
            return "Error generating summary."

    async def _send_or_save(self, subject: str, body: str, ticket_id: str, prefix: str) -> Optional[str]:
        """
        Internal helper to send email or save to file (DRY).
        """
        # Try to send real email if configured
        if settings.SMTP_SERVER and settings.SMTP_USERNAME:
            try:
                import aiosmtplib
                from email.message import EmailMessage
                
                msg = EmailMessage()
                msg["From"] = settings.SMTP_FROM_EMAIL
                msg["To"] = self.recipient
                msg["Subject"] = subject
                msg.set_content(body, charset="utf-8", cte="quoted-printable")
                
                await aiosmtplib.send(
                    msg,
                    hostname=settings.SMTP_SERVER,
                    port=settings.SMTP_PORT,
                    username=settings.SMTP_USERNAME,
                    password=settings.SMTP_PASSWORD,
                    start_tls=True
                )
                logger.info(f"Successfully sent email to {self.recipient}")
                return ticket_id
            except Exception as e:
                logger.error(f"Failed to send real email: {e}")
                # Fallback to file save
        
        # DEMO MODE: Save to file
        try:
            loop = asyncio.get_running_loop()
            
            def _save_file():
                os.makedirs(self.emails_dir, exist_ok=True)
                filename = os.path.join(self.emails_dir, f"{prefix}_{ticket_id.replace('#', '')}.txt")
                
                with open(filename, "w", encoding="utf-8") as f:
                    f.write(f"To: {self.recipient}\n")
                    f.write(f"Subject: {subject}\n")
                    f.write(body)
                return filename

            filename = await loop.run_in_executor(None, _save_file)
            logger.info(f"Saved demo email to {filename}")
            return ticket_id
        except Exception as e:
            logger.error(f"Failed to save demo email: {e}")
            return None

    async def send_support_email(self, name: str, business: str, user_summary: str, history: List[Message] = None):
        """
        Simulates sending a support email with ticket ID and AI summary.
        """
        ticket_id = await self._get_next_ticket_id()
        
        # Generate AI summary of the actual chat logs
        ai_summary = await self._generate_chat_summary(history) if history else "No chat history provided."
        
        # Format Subject: #00001245 - John's Restaurant - Printer melted...
        # Use user's summary if provided, otherwise fallback to generic
        subject_summary = user_summary if user_summary else "Support Request"
        # Truncate subject summary if too long
        if len(subject_summary) > self.MAX_SUBJECT_LENGTH:
            subject_summary = subject_summary[:self.MAX_SUBJECT_LENGTH-3] + "..."
            
        subject = f"{ticket_id} - {business} - {subject_summary}"
        
        body = f"""
        ================================================================
        NEW SUPPORT TICKET: {ticket_id}
        ================================================================
        
        CLIENT INFORMATION:
        -------------------
        Name: {name}
        Business: {business}
        
        ISSUE DETAILS:
        --------------
        User Reported Summary: {user_summary}
        
        AI CONVERSATION SUMMARY:
        ------------------------
        {ai_summary}
        
        FULL TRANSCRIPT:
        ----------------
        """
        
        if history:
            for msg in history:
                role = "User" if msg.role == "user" else "Assistant"
                body += f"[{role}]: {msg.content}\n"
        else:
            body += "(No transcript available)"
            
        body += "\n================================================================"

        return await self._send_or_save(subject, body, ticket_id, "ticket")

    async def send_callback_request(self, phone: str, preferred_time: str, history: List[Message] = None):
        """
        Sends a callback request ticket.
        """
        ticket_id = await self._get_next_ticket_id()
        
        # Generate AI summary
        ai_summary = await self._generate_chat_summary(history) if history else "No chat history provided."
        
        subject = f"{ticket_id} - CALLBACK REQUEST - {phone}"
        
        body = f"""
        ================================================================
        NEW CALLBACK REQUEST: {ticket_id}
        ================================================================
        
        CONTACT DETAILS:
        ----------------
        Phone: {phone}
        Preferred Time: {preferred_time}
        
        AI CONVERSATION SUMMARY:
        ------------------------
        {ai_summary}
        
        FULL TRANSCRIPT:
        ----------------
        """
        
        if history:
            for msg in history:
                role = "User" if msg.role == "user" else "Assistant"
                body += f"[{role}]: {msg.content}\n"
        else:
            body += "(No transcript available)"
            
        body += "\n================================================================"

        return await self._send_or_save(subject, body, ticket_id, "callback")

    async def create_inbound_call_ticket(self, phone: str, history: List[Message] = None):
        """
        Generates a ticket for an inbound call and notifies support.
        """
        ticket_id = await self._get_next_ticket_id()
        
        # Generate AI summary
        ai_summary = await self._generate_chat_summary(history) if history else "No chat history provided."
        
        subject = f"{ticket_id} - INCOMING CALL - {phone}"
        
        body = f"""
        ================================================================
        INCOMING CALL ALERT: {ticket_id}
        ================================================================
        
        The user is calling NOW from: {phone}
        
        AI CONVERSATION SUMMARY:
        ------------------------
        {ai_summary}
        
        FULL TRANSCRIPT:
        ----------------
        """
        
        if history:
            for msg in history:
                role = "User" if msg.role == "user" else "Assistant"
                body += f"[{role}]: {msg.content}\n"
        else:
            body += "(No transcript available)"
            
        body += "\n================================================================"

        return await self._send_or_save(subject, body, ticket_id, "call")
