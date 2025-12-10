# Vector Store Service Documentation

## Overview
The **Vector Store Service** (`vector_store.py`) provides a robust interface for interacting with the Pinecone vector database. It handles connection management, index initialization, and core vector operations (upsert, query, delete) with built-in reliability features like batching, input validation, and error handling.

This service is a critical component of the RAG (Retrieval-Augmented Generation) pipeline, enabling semantic search capabilities by storing and retrieving embedding vectors.

## Key Features
- **Automatic Index Initialization**: Checks for index existence and creates it if missing (using serverless spec).
- **Batch Processing**: Automatically batches large upsert and delete operations to respect API limits.
- **Robustness**: Handles network errors and invalid inputs gracefully without crashing the application.
- **Namespace Support**: Supports multi-tenant or segmented data architectures via Pinecone namespaces.
- **Defensive Validation**: Validates vector dimensions and structure before sending to API.

## Configuration
The service requires the following environment variables (accessed via `settings`):

| Variable | Description | Default |
|----------|-------------|---------|
| `PINECONE_API_KEY` | API Key for Pinecone authentication | `None` (set to "changeme" to disable) |
| `PINECONE_INDEX_NAME` | Name of the index to use/create | - |
| `AWS_REGION` | AWS Region for serverless index creation | - |
| `PINECONE_CLOUD` | Cloud provider for serverless index | `aws` |

## API Reference

### `VectorStoreService` Class

#### `__init__()`
Initializes the Pinecone client. If the API key is invalid or set to "changeme", the service initializes in a disabled state (safe to use but operations will return failure/empty).

#### `upsert_vectors(vectors, batch_size=100, namespace="") -> bool`
Inserts or updates vector embeddings.
- **vectors**: List of dicts with `{'id': str, 'values': List[float], 'metadata': Dict}`.
- **batch_size**: Max vectors per API request (default 100).
- **namespace**: Partition to store vectors in.

#### `query(vector, top_k=5, filter=None, namespace="") -> List[Match]`
Searches for similar vectors.
- **vector**: Query embedding list/tuple (must match dimension 1536).
- **top_k**: Number of results.
- **filter**: Metadata filter dict.
- **namespace**: Partition to search.

#### `delete_vectors(ids, namespace="", batch_size=1000) -> bool`
Deletes specific vectors by ID.
- **ids**: List of vector IDs.
- **batch_size**: Max IDs per API request (default 1000).

#### `delete_all(namespace="") -> bool`
Deletes all vectors in a specific namespace.
- **namespace**: The namespace to clear. If empty, behavior depends on Pinecone (typically clears default namespace).

## Usage Examples

### Initializing the Service
```python
from app.services.rag.vector_store import VectorStoreService

# Service initializes and connects automatically
vector_store = VectorStoreService()

if not vector_store.is_configured():
    print("Warning: Vector store not available")
```

### Upserting Documents
```python
vectors = [
    {
        "id": "doc_1_chunk_0",
        "values": [0.1, 0.2, ...], # 1536 dims
        "metadata": {"source": "manual.pdf", "page": 1}
    },
    # ... more vectors
]

# Large lists are automatically batched
success = vector_store.upsert_vectors(vectors, namespace="user_docs")
```

### Semantic Search
```python
query_embedding = embedding_model.embed_query("how to reset printer")

matches = vector_store.query(
    vector=query_embedding,
    top_k=3,
    namespace="user_docs",
    filter={"source": "manual.pdf"}
)

for match in matches:
    print(f"Score: {match.score}, ID: {match.id}")
```

## Troubleshooting

### "Pinecone index not configured"
- **Cause**: Missing API key or initialization failure.
- **Fix**: Check `PINECONE_API_KEY` in environment and ensure logs don't show initialization errors.

### "Index dimension mismatch"
- **Cause**: The existing Pinecone index has a different dimension (e.g., 768) than the application expects (1536).
- **Fix**: Delete the index in Pinecone console and restart the app to let it recreate with correct settings, or update application configuration if using a different embedding model.

### Upsert Partial Failure
- **Cause**: Network interruption during batch processing.
- **Fix**: Check logs for "Partial upsert" warnings. The operation is idempotent, so you can retry the entire list.

## Best Practices
1. **Always use namespaces**: Keeps data organized and allows easy deletion of specific datasets.
2. **Handle empty results**: Query might return empty list if index is empty or service is disabled.
3. **Monitor logs**: The service logs detailed errors and warnings that are essential for debugging API issues.

