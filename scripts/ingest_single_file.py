import os
import sys
from pathlib import Path
import shutil

# Add project root to Python path
SCRIPT_DIR = Path(__file__).parent
PROJECT_ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(PROJECT_ROOT))

from app.services.ingestor.loaders import LoaderFactory
from app.services.ingestor.processor import DocumentProcessor
from app.services.rag.vector_store import VectorStoreService
from app.services.ingestor.hash_manager import HashManager

DATA_DIR = PROJECT_ROOT / "data" / "kb_documents"

def ingest_single_file(file_path: str):
    """
    Ingest a single file into the knowledge base.
    
    Args:
        file_path: Path to the file to ingest
    """
    file_path = Path(file_path).absolute()
    
    if not file_path.exists():
        print(f"[ERROR] File not found: {file_path}")
        return
    
    # Ensure data directory exists
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    
    # Copy file to kb_documents if it's not already there
    target_path = DATA_DIR / file_path.name
    if file_path != target_path:
        print(f"[System] Copying {file_path.name} to knowledge base directory...")
        shutil.copy2(file_path, target_path)
        file_to_ingest = target_path
    else:
        file_to_ingest = file_path
    
    print("-" * 50)
    print(f"INGESTING SINGLE FILE")
    print("-" * 50)
    
    try:
        # Initialize services
        hash_manager = HashManager()
        processor = DocumentProcessor()
        vector_store = VectorStoreService()
        
        filename = file_to_ingest.name
        
        # Check if file should be processed
        should_proc = hash_manager.should_process(str(file_to_ingest))
        print(f"[DEBUG] {filename}: should_process={should_proc}")
        
        if not should_proc:
            print(f"[SKIP] {filename} (Unchanged)")
            print("-" * 50)
            return
        
        # Load file
        print(f"[System] Loading {filename}...")
        loader = LoaderFactory.get_loader(str(file_to_ingest))
        docs = loader.load()
        
        if not docs:
            print(f"[WARN] No content extracted from {filename}")
            return
        
        # Chunk
        print(f"[AI] Semantically chunking {len(docs)} pages...")
        chunks = processor.chunk_documents(docs)
        print(f"[AI] Generated {len(chunks)} knowledge chunks")
        
        # Embed & Upload
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
        
        # Upsert to Pinecone
        if vectors:
            print(f"[System] Uploading {len(vectors)} vectors to Pinecone...")
            vector_store.upsert_vectors(vectors)
            print(f"[OK] Uploaded {len(vectors)} vectors for {filename}")
            
        # Mark as processed
        hash_manager.mark_processed(str(file_to_ingest))
        
        print("-" * 50)
        print(f"[OK] SUCCESS: {filename} added to knowledge base")
        print(f"[OK] Total chunks: {len(vectors)}")
        print("-" * 50)
        
    except ValueError as e:
        print(f"[WARN] Unsupported file type: {filename} ({e})")
    except Exception as e:
        print(f"❌ ERROR: Failed to process {filename}: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python ingest_single_file.py <path_to_file>")
        sys.exit(1)
    
    file_path = sys.argv[1]
    ingest_single_file(file_path)
