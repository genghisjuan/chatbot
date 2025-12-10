import requests
import json
import sys
from datetime import datetime

BASE_URL = "http://localhost:8000/api/v1/admin"

def color_print(msg, color="green"):
    colors = {
        "green": "\033[92m",
        "red": "\033[91m",
        "yellow": "\033[93m",
        "reset": "\033[0m"
    }
    print(f"{colors.get(color, '')}{msg}{colors['reset']}")

def get_spend():
    try:
        response = requests.get(f"{BASE_URL}/spend")
        response.raise_for_status()
        return response.json()
    except Exception as e:
        color_print(f"Error fetching spend: {e}", "red")
        return None

def add_expense(category, description, amount, date=None):
    payload = {
        "category": category,
        "description": description,
        "amount": amount,
        "date": date
    }
    try:
        response = requests.post(f"{BASE_URL}/expenses", json=payload)
        response.raise_for_status()
        return True
    except Exception as e:
        color_print(f"Error adding expense: {e}", "red")
        print(response.text)
        return False

def main():
    print("--- Verifying Spend Analytics ---")

    # 1. Initial Spend
    print("\n1. Fetching Initial Spend...")
    initial_spend = get_spend()
    if not initial_spend:
        sys.exit(1)
    
    initial_total = initial_spend['month']['cost'] # Use month as it should capture today too
    initial_misc = initial_spend['month']['misc_cost']
    print(f"Initial Month Total: ${initial_total}")
    print(f"Initial Misc Cost: ${initial_misc}")

    # 2. Add Manual Expense
    print("\n2. Adding Manual Expense ($5.50)...")
    if add_expense("Testing", "Verification Script Expense", 5.50, datetime.now().strftime("%Y-%m-%d")):
        color_print("Expense added successfully.")
    else:
        sys.exit(1)

    # 3. Verify Update
    print("\n3. Verifying Spend Update...")
    new_spend = get_spend()
    if not new_spend:
        sys.exit(1)
    
    new_total = new_spend['month']['cost']
    new_misc = new_spend['month']['misc_cost']
    print(f"New Month Total: ${new_total}")
    print(f"New Misc Cost: ${new_misc}")

    diff = new_misc - initial_misc
    if abs(diff - 5.50) < 0.01:
        color_print("SUCCESS: Misc cost increased by exactly $5.50", "green")
    else:
        color_print(f"FAILURE: Misc cost increased by ${diff}, expected $5.50", "red")

    # 4. Check Embedding Tokens (Read-only check)
    print("\n4. Checking Embedding Tokens...")
    embed_tokens = new_spend['all_time']['embedding_tokens']
    print(f"Total Embedding Tokens: {embed_tokens}")
    if 'embedding_cost' in new_spend['all_time']:
         print(f"Embedding Cost: ${new_spend['all_time']['embedding_cost']}")
         color_print("Embedding cost field is present.", "green")
    else:
         color_print("Embedding cost field is MISSING.", "red")

if __name__ == "__main__":
    main()
