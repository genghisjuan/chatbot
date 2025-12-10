import os
import sys
from pathlib import Path

# Add project root to Python path
SCRIPT_DIR = Path(__file__).parent
PROJECT_ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(PROJECT_ROOT))

import time
from app.core.config import settings
from app.services.ingestor.loaders import LoaderFactory
from app.services.ingestor.processor import DocumentProcessor
from app.services.rag.vector_store import VectorStoreService

# Use absolute path for DATA_DIR to ensure consistent hash state across different working directories
DATA_DIR = str(PROJECT_ROOT / "data" / "kb_documents")

def ingest_documents():
    """
    Orchestrator for the Ingestion Pipeline.
    Supports PDF (Vision), TXT, MD, DOCX.
    """
    if not settings.OPENAI_API_KEY:
        print("❌ CRITICAL: OPENAI_API_KEY not set.")
        return

    # 1. Initialize Processor
    try:
        from app.services.ingestor.hash_manager import HashManager
        hash_manager = HashManager()
        processor = DocumentProcessor()
        vector_store = VectorStoreService()
    except Exception as e:
        print(f"FAILED initializing services: {e}")
        return

    # 2. Iterate and Load Files
    if not os.path.exists(DATA_DIR):
        print(f"Data directory not found: {DATA_DIR}")
        return

    print("-" * 50)
    print(f"STARTING INGESTION PIPELINE (Smart Integration Active)")
    print("-" * 50)
    
    total_chunks = 0
    stats = {"processed": 0, "skipped": 0, "errors": 0}
    
    for filename in os.listdir(DATA_DIR):
        file_path = os.path.join(DATA_DIR, filename)
        if not os.path.isfile(file_path):
            continue

        # --- SMART HASH CHECK (with debug) ---
        file_key = os.path.abspath(file_path)
        should_proc = hash_manager.should_process(file_path)
        print(f"[DEBUG] {filename}: should_process={should_proc}, in_state={file_key in hash_manager.state}")
        if not should_proc:
            print(f"   [SKIP] {filename} (Unchanged)")
            stats["skipped"] += 1
            continue
        # -------------------------------------
            
        try:
            # Factory determines loader (VisionPDF, Text, etc.)
            loader = LoaderFactory.get_loader(file_path)
            
            # Load (This triggers Vision API for PDFs)
            docs = loader.load()
            
            if not docs:
                print(f"   ⚠️ No content extracted from {filename}")
                stats["errors"] += 1
                continue
                
            # Chunk
            chunks = processor.chunk_documents(docs)
            print(f"   [AI] Generated {len(chunks)} chunks.")
            
            # Embed & Upload
            # We need to map chunks to vectors
            texts = [c.page_content for c in chunks]
            embeddings = processor.get_embeddings().embed_documents(texts)
            
            vectors = []
            safe_source = filename.replace(" ", "_")
            
            for i, chunk in enumerate(chunks):
                vid = f"{safe_source}_{i}"
                metadata = {
                    "text": chunk.page_content,
                    "source": filename,
                    "page": chunk.metadata.get('page', 1)
                }
                vectors.append({
                    "id": vid,
                    "values": embeddings[i],
                    "metadata": metadata
                })
            
            # Upsert batch
            if vectors:
                vector_store.upsert_vectors(vectors)
                total_chunks += len(vectors)
                stats["processed"] += 1
                print(f"   [OK] Uploaded {len(vectors)} vectors for {filename}")
                
            # --- MARK AS PROCESSED ---
            hash_manager.mark_processed(file_path)
            # -------------------------
                
        except ValueError as e:
            # Unsupported file type
            print(f"   [WARN] Unsupported: {filename} ({e})")
            # Don't count as error, just ignore
        except Exception as e:
            # Emoji can crash windows console if encoding is cp1252. Using [X] instead.
            print(f"   [X] FAILED to process {filename}: {e}")
            stats["errors"] += 1

    print("-" * 50)
    print(f"INGESTION COMPLETE. Total Vectors: {total_chunks}")
    print(f"Files Found: {len(os.listdir(DATA_DIR))}")
    print("-" * 50)
    
    # JSON Summary for Launcher
    import json
    print(f"JSON_SUMMARY: {json.dumps(stats)}")

if __name__ == "__main__":
    ingest_documents()
