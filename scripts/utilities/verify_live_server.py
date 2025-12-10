import requests
import json
import uuid

def test_live_server():
    url = "http://localhost:8000/api/v1/chat"
    
    # Needs FormData, not JSON
    data = {
        "user_message": "how do i fix negative cash balance on daily sales report",
        "conversation_history": "[]", 
        "language": "english"
    }
    
    # ... setup ...
    try:
        # ... request ...
        print(f"Status Code: {response.status_code}")
        # ... logic ...
        
        # SUCCESS CRITERIA
        # 1. Must cite the EOD document.
        # 2. Must not contain external URLs (unless whitelisted/safe, but we banned them mostly).
        # 3. Must explain the solution (tips > sales).
        
        has_citation = "NEGATIVE CASH BALANCE" in full_text.upper() or ".PDF" in full_text.upper()
        has_explanation = "tips" in full_text.lower() or "starting balance" in full_text.lower()
        has_external_url = "http" in full_text and "zohodesk" not in full_text # Allow internal wiki link if bot quotes it, but verify strictness.
        
        if has_citation and has_explanation:
            print("✅ PASS: Correct Explanation + Document Cited.")
        else:
            print("❌ FAIL: Missing explanation or citation.")
            
        if "google.com" in full_text or "wikipedia.org" in full_text:
             print("❌ FAIL: Detected Hallucinated External Link.")
        else:
             print("✅ PASS: No hallucinated links detected.")
             
    except Exception as e:
        print(f"❌ Connection Failed: {e}")
    
    # No file upload for this test
    files = {} 
    
    print(f"📡 Pinging Live Server at {url}...")
    try:
        # requests.post with 'data' param sends form-encoded (multipart if files present, or urlencoded)
        # FastAPI Form(...) handles both.
        
        response = requests.post(url, data=data, stream=True)
        
        print(f"Status Code: {response.status_code}")
        
        full_text = ""
        for line in response.iter_lines():
            if line:
                decoded = line.decode('utf-8')
                if decoded.startswith("data: "):
                    content = decoded[6:] 
                    if content == "[DONE]": break
                    try:
                        full_text += content
                    except:
                        pass
                else:
                    full_text += decoded
                    
        print("\n🤖 SERVER RESPONSE:")
        print("-" * 50)
        print(full_text)
        print("-" * 50)
        
        if "Transafe" in full_text and ("isn't" not in full_text and "not" not in full_text):
             # Be careful with negative matching
             pass
             
        has_citation = ".pdf" in full_text or "Source:" in full_text or "document" in full_text
             
        if "live.transafe.com" in full_text or "Primary Host" in full_text:
             if has_citation:
                 print("✅ PASS: Server returned technical details AND cited source.")
             else:
                 print("⚠️ PASS (Partial): Answers correctly but MISSING CITATION.")
        elif "Configuration Guide" in full_text:
             print("✅ PASS: Server returned document citation.")
        elif "isn't in my provided resources" in full_text:
             print("❌ FAIL: Server returned REFUSAL. (Stale Code?)")
        else:
             print("⚠️ INDETERMINATE: Check response content manually.")

    except Exception as e:
        print(f"❌ Connection Failed: {e}")

if __name__ == "__main__":
    test_live_server()
