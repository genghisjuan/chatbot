"""
Add missing files to state file to prevent re-ingestion.
This adds the 6 files that are in Pinecone but not in the state file.
"""
import json
import hashlib
from pathlib import Path

# Paths
PROJECT_ROOT = Path(__file__).parent.parent
STATE_FILE = PROJECT_ROOT / "data" / "ingestion_state.json"
DATA_DIR = PROJECT_ROOT / "data" / "kb_documents"

# The 6 files that are in Pinecone but not in state
MISSING_FILES = [
    "PRINTER COMMAND CODES AND HOW THEY WORK.pdf",
    "Printer_Thermal - R180.pdf",
    "REDIRECT PRINTERS (CONTROL PRINTERS MENU).pdf",
    "REFUND AND ADD TIPS THROUGH TRANSAFE.pdf",
    "TERMINAL HARD DRIVE SWAPS.pdf",
    "WTI 4200 Router.pdf"
]

def compute_hash(file_path):
    """Compute MD5 hash of a file."""
    hasher = hashlib.md5()
    with open(file_path, 'rb') as f:
        buf = f.read(65536)
        while len(buf) > 0:
            hasher.update(buf)
            buf = f.read(65536)
    return hasher.hexdigest()

def main():
    print("=" * 70)
    print("ADDING MISSING FILES TO STATE")
    print("=" * 70)
    
    # Load current state
    with open(STATE_FILE, 'r') as f:
        state = json.load(f)
    
    print(f"\nCurrent entries in state: {len(state)}")
    print(f"Files to add: {len(MISSING_FILES)}\n")
    
    # Add missing files
    added = 0
    for filename in MISSING_FILES:
        file_path = DATA_DIR / filename
        
        if not file_path.exists():
            print(f"❌ {filename}: File not found, skipping")
            continue
        
        file_key = str(file_path.absolute())
        file_hash = compute_hash(file_path)
        
        if file_key in state:
            print(f"⚠️  {filename}: Already in state, skipping")
        else:
            state[file_key] = file_hash
            added += 1
            print(f"✅ {filename}: Added to state")
    
    # Save updated state
    with open(STATE_FILE, 'w') as f:
        json.dump(state, f, indent=2)
    
    print("\n" + "=" * 70)
    print("COMPLETE")
    print("=" * 70)
    print(f"Total entries now: {len(state)}")
    print(f"Files added: {added}")
    print(f"\n✅ State file updated! Next ingestion will skip these {added} files.")

if __name__ == "__main__":
    main()
