"""
Migrate old state file keys from mixed paths to consistent absolute paths.
Run this once to fix the state file after the DATA_DIR path fix.
"""
import json
from pathlib import Path

# Paths
PROJECT_ROOT = Path(__file__).parent.parent
STATE_FILE = PROJECT_ROOT / "data" / "ingestion_state.json"
DATA_DIR = PROJECT_ROOT / "data" / "kb_documents"

def main():
    print("=" * 70)
    print("STATE FILE MIGRATION - Fixing Path Keys")
    print("=" * 70)
    
    # Load current state
    with open(STATE_FILE, 'r') as f:
        old_state = json.load(f)
    
    print(f"\nCurrent state file: {STATE_FILE}")
    print(f"Current entries: {len(old_state)}")
    
    # Create new state with corrected keys
    new_state = {}
    migrated = 0
    already_correct = 0
    
    for old_key, hash_value in old_state.items():
        # Extract filename from old key
        filename = Path(old_key).name
        
        # Build correct absolute path
        correct_key = str((DATA_DIR / filename).absolute())
        
        if old_key == correct_key:
            already_correct += 1
        else:
            migrated += 1
            print(f"  Migrating: {filename}")
            print(f"    OLD: {old_key}")
            print(f"    NEW: {correct_key}")
        
        new_state[correct_key] = hash_value
    
    # Save migrated state
    with open(STATE_FILE, 'w') as f:
        json.dump(new_state, f, indent=2)
    
    print("\n" + "=" * 70)
    print("MIGRATION COMPLETE")
    print("=" * 70)
    print(f"Total entries: {len(new_state)}")
    print(f"Already correct: {already_correct}")
    print(f"Migrated: {migrated}")
    print(f"\n✅ State file updated successfully!")

if __name__ == "__main__":
    main()
