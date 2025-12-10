"""
Quick diagnostic script to check ingestion state vs actual files.
Run this to see why files might be re-ingesting.
"""
import os
import json
import hashlib
from pathlib import Path

# Project paths (script is in scripts/, so parent is project root)
PROJECT_ROOT = Path(__file__).parent.parent
STATE_FILE = PROJECT_ROOT / "data" / "ingestion_state.json"
DATA_DIR = PROJECT_ROOT / "data" / "kb_documents"

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
    # Load state
    with open(STATE_FILE, 'r') as f:
        state = json.load(f)
    
    print("=" * 70)
    print("INGESTION STATE DIAGNOSTIC")
    print("=" * 70)
    print(f"\nState file: {STATE_FILE}")
    print(f"Data directory: {DATA_DIR}")
    print(f"\nFiles in state: {len(state)}")
    
    # Check each file in directory
    files_on_disk = list(DATA_DIR.glob("*"))
    files_on_disk = [f for f in files_on_disk if f.is_file()]
    
    print(f"Files on disk: {len(files_on_disk)}")
    print("\n" + "-" * 70)
    
    mismatches = []
    
    for file_path in files_on_disk:
        filename = file_path.name
        file_key = str(file_path.absolute())
        
        # Check if in state
        in_state = file_key in state
        
        if in_state:
            # Check if hash matches
            stored_hash = state[file_key]
            current_hash = compute_hash(file_path)
            hash_match = (stored_hash == current_hash)
            
            if not hash_match:
                status = "CHANGED (will re-ingest)"
                mismatches.append((filename, "File modified since last ingest"))
                print(f"⚠️  {filename}: {status}")
                print(f"    State hash:   {stored_hash}")
                print(f"    Current hash: {current_hash}")
            else:
                print(f"✅ {filename}: OK (will skip)")
        else:
            status = "NEW (will ingest)"
            mismatches.append((filename, "Not in state file"))
            print(f"🆕 {filename}: {status}")
            print(f"    Expected key: {file_key}")
    
    print("\n" + "=" * 70)
    print(f"SUMMARY: {len(mismatches)} files will be re-ingested")
    print("=" * 70)
    
    if mismatches:
        print("\nFiles that will be processed:")
        for filename, reason in mismatches:
            print(f"  - {filename}: {reason}")
    else:
        print("\n✅ All files are up-to-date. Nothing will be re-ingested.")

if __name__ == "__main__":
    main()
