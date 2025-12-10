import requests
import json

def test_streaming():
    url = "http://127.0.0.1:8000/api/v1/chat"
    
    print("Sending Message...")
    payload = {
        "user_message": "Tell me a joke",
        "conversation_history": []
    }
    
    # Enable streaming
    with requests.post(url, json=payload, stream=True) as r:
        print(f"Status Code: {r.status_code}")
        print("Response Chunks:")
        for chunk in r.iter_content(chunk_size=None):
            if chunk:
                print(chunk.decode('utf-8'), end='', flush=True)
    print("\n\nDone.")

if __name__ == "__main__":
    test_streaming()
