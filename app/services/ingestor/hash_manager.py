import hashlib
import json
import os
import logging
from typing import Dict, Optional
from pathlib import Path

logger = logging.getLogger(__name__)

# Project root for absolute paths
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
DEFAULT_STATE_FILE = str(PROJECT_ROOT / "data" / "ingestion_state.json")

class HashManager:
    """
    Manages file fingerprints (MD5 hashes) to prevent re-ingesting unchanged files.
    Stores state in a JSON file.
    
    Note: Uses absolute file paths as keys to prevent collisions between files
    with the same name in different directories.
    """
    def __init__(self, state_file: Optional[str] = None) -> None:
        self.state_file: str = state_file or DEFAULT_STATE_FILE
        self.state: Dict[str, str] = self._load_state()
        # Initialization logging
        logger.info(f"HashManager initialized - State file: {self.state_file}")
        logger.info(f"HashManager loaded {len(self.state)} entries from state file")


    def _load_state(self) -> Dict[str, str]:
        """Load hash state from JSON file."""
        if os.path.exists(self.state_file):
            try:
                with open(self.state_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except json.JSONDecodeError as e:
                logger.error(f"Corrupt state file at {self.state_file}, resetting: {e}", exc_info=True)
                return {}
            except Exception as e:
                logger.error(f"Failed to load state from {self.state_file}: {e}", exc_info=True)
                return {}
        return {}

    def _save_state(self) -> None:
        """
        Save hash state to JSON file using atomic write.
        
        Uses temporary file + rename to prevent corruption if write fails mid-way.
        """
        try:
            # Create parent directory if needed
            os.makedirs(os.path.dirname(self.state_file), exist_ok=True)
            
            # Atomic write: write to temp file, then rename
            temp_file = self.state_file + ".tmp"
            with open(temp_file, 'w', encoding='utf-8') as f:
                json.dump(self.state, f, indent=2)
            os.replace(temp_file, self.state_file)  # Atomic on both POSIX and Windows
            
            logger.info(f"Successfully saved state file with {len(self.state)} entries")
        except Exception as e:
            # Clean up temp file on failure
            temp_file = self.state_file + ".tmp"
            if os.path.exists(temp_file):
                try:
                    os.remove(temp_file)
                except OSError:
                    pass  # Best effort cleanup
            logger.error(f"CRITICAL: Failed to save ingestion state to {self.state_file}: {e}", exc_info=True)
            print(f"❌ ERROR: Could not save state file: {e}")  # Also print to console


    def compute_hash(self, file_path: str) -> Optional[str]:
        """
        Computes MD5 hash of a file.
        
        Args:
            file_path: Path to file
            
        Returns:
            Hash string, or None if file not found
        """
        hasher = hashlib.md5()
        try:
            with open(file_path, 'rb') as f:
                while True:
                    buf = f.read(65536)
                    if not buf:
                        break
                    hasher.update(buf)
            return hasher.hexdigest()
        except FileNotFoundError:
            return None
        except (IOError, OSError) as e:
            logger.warning(f"Failed to hash file {file_path}: {e}")
            return None

    def should_process(self, file_path: str) -> bool:
        """
        Returns True if file is new or changed.
        Returns False if file matches known hash or is missing.
        
        Args:
            file_path: Path to file to check
            
        Returns:
            True if file should be processed, False otherwise
        """
        if not file_path or not file_path.strip():
            raise ValueError("file_path cannot be empty or whitespace")
        
        current_hash = self.compute_hash(file_path)
        if current_hash is None:
            return False  # File missing, cannot process

        # Use absolute path as key to prevent basename collisions
        file_key = os.path.abspath(file_path)
        stored_hash = self.state.get(file_key)

        if current_hash == stored_hash:
            return False  # SKIP - unchanged
        
        return True  # PROCESS - new or changed

    def mark_processed(self, file_path: str, file_hash: Optional[str] = None) -> None:
        """
        Updates the state with the new hash after successful processing.
        
        Args:
            file_path: Path to processed file
            file_hash: Optional pre-computed hash (avoids recomputation)
        """
        if not file_path or not file_path.strip():
            raise ValueError("file_path cannot be empty or whitespace")
        
        # Use absolute path as key to prevent basename collisions
        file_key = os.path.abspath(file_path)
        
        if file_hash is None:
            file_hash = self.compute_hash(file_path)
            if file_hash is None:
                logger.warning(f"Cannot mark processed: file not found: {file_path}")
                return
        
        self.state[file_key] = file_hash
        self._save_state()
