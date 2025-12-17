import sys
import os
import smtplib
from email.mime.text import MIMEText

# Add app to path to import config if needed, though we will try raw env first
sys.path.append(os.getcwd())

# We can reuse the function from admin.py or write a simplified one to isolate variables.
# Let's import the exact function to test *that* function.
from app.api.admin import _send_alert_email

def test_real_email():
    print("--- Testing Real Email Delivery ---")
    
    # 1. Check Env Vars
    smtp_server = os.getenv("SMTP_SERVER")
    smtp_user = os.getenv("SMTP_USERNAME")
    smtp_pass = os.getenv("SMTP_PASSWORD")
    
    print(f"SMTP Server: {smtp_server}")
    print(f"SMTP User: {'[SET]' if smtp_user else '[MISSING]'}")
    print(f"SMTP Pass: {'[SET]' if smtp_pass else '[MISSING]'}")
    
    if not smtp_user or not smtp_pass:
        print("❌ Error: SMTP credentials are missing in environment variables.")
        print("Please ensure .env is loaded or variables are set.")
        return

    # 2. Add explicit debug for connection
    try:
        print("Attempting to send test email...")
        _send_alert_email(
            "Test Email from JUNA Verification", 
            "This is a manual test to verify email delivery is working."
        )
        print("✅ _send_alert_email function executed without exception.")
        print("Please check your inbox (and spam folder) for 'JUNA ALERT: Test Email...'.")
        
    except Exception as e:
        print(f"❌ Failed to invoke email function: {e}")

if __name__ == "__main__":
    test_real_email()
