import requests

# Test the deal endpoint
url = "http://localhost:8000/api/v1/deal/chat"
data = {
    "user_message": "Generate all 3 guided questions. Context: {'vertical': 'restaurant', 'volume': '50k-250k'}",
    "conversation_history": "[]",
    "language": "en-US",
    "mode": "deal"
}

response = requests.post(url, data=data)
print(f"Status: {response.status_code}")
print(f"Headers: {response.headers}")
print(f"Body: {response.text[:500]}")
