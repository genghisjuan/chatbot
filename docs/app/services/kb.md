# Knowledge Base Service Documentation

## Overview

**File**: [`app/services/rag/kb.py`](file:///c:/Users/John/.gemini/antigravity/scratch/support_chatbot/app/services/rag/kb.py)

The Knowledge Base Service provides semantic search over uploaded PDF documents using Pinecone vector similarity search. It converts user queries to embeddings and finds the most relevant document chunks from the knowledge base.

---

## Table of Contents

1. [Summary](#summary)
2. [How It Works](#how-it-works)
3. [Class: KnowledgeBase](#class-knowledgebase)
4. [Search Process](#search-process)
5. [Configuration](#configuration)
6. [Usage Examples](#usage-examples)
7. [Caching](#caching)
8. [Error Handling](#error-handling)
9. [Best Practices](#best-practices)
10. [Troubleshooting](#troubleshooting)

---

## Summary

**Purpose**: Semantic search over PDF documents using vector similarity

**Key Features**:
- ✅ **Semantic search** using OpenAI embeddings + Pinecone
- ✅ **Confidence filtering** - only returns high-quality matches
- ✅ **LRU caching** - speeds up repeated queries
- ✅ **Ranked results** - sorted by relevance score

**Technology Stack**:
- **Embeddings**: OpenAI text-embedding-ada-002
- **Vector Store**: Pinecone (cloud-based)
- **Cache**: In-memory LRU (100 queries)

---

## How It Works

### High-Level Process

```
User Query → Embedding → Pinecone Search → Filtering → Ranked Results
```

### Detailed Flow

1. **Convert query to embedding** using OpenAI
2. **Search Pinecone** for similar vectors
3. **Filter by confidence threshold** (≥ 0.50)
4. **Return top k results** with metadata

### Example

**Input**:
```
Query: "How do I process a refund?"
k: 3
```

**Process**:
```
1. Embedding: [0.12, -0.45, 0.89, ...] (1536 dimensions)
2. Pinecone Search: Returns 6 results (k * OVERSEARCH_MULTIPLIER)
3. Filter: Keep only scores ≥ 0.50
4. Return: Top 3 documents
```

**Output**:
```python
[
    Document(
        page_content="To process a refund...",
        metadata={"source": "refunds.pdf", "page": 5, "score": 0.92}
    ),
    Document(...),
    Document(...)
]
```

---

## Class: KnowledgeBase

### Constructor

```python
def __init__(self) -> None:
```

**Purpose**: Initialize knowledge base with embeddings and vector store

**Parameters**: None (uses config)

**Initializes**:
- OpenAI embeddings client
- Pinecone vector store connection
- LRU cache (100 entries)

**Example**:
```python
from app.services.rag.kb import KnowledgeBase

kb = KnowledgeBase()
# Logs: "Initializing KnowledgeBase with Pinecone vector store"
# Logs: "KnowledgeBase initialized successfully"
```

---

### search()

```python
async def search(self, query: str, k: int = 3) -> List[Document]:
```

**Purpose**: Search for relevant documents using semantic similarity

**Parameters**:
| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `query` | `str` | Yes | - | User's search query |
| `k` | `int` | No | 3 | Number of results to return |

**Returns**: `List[Document]` - Ranked list of relevant documents

**Document Structure**:
```python
Document(
    page_content="text content...",
    metadata={
        "source": "filename.pdf",  # Source file
        "page": 5,                  # Page number (1-indexed)
        "score": 0.85               # Relevance score (0-1)
    }
)
```

**Raises**:
- `ValueError`: If query is empty or k is invalid
- `RuntimeError`: If search fails (Pinecone error, embedding error, etc.)

**Example**:
```python
kb = KnowledgeBase()
results = await kb.search("printer setup", k=5)

for doc in results:
    print(f"[{doc.metadata['score']:.2f}] {doc.metadata['source']}")
    print(f"  {doc.page_content[:100]}...\n")
```

---

## Search Process

### 1. Input Validation

```python
if not query or not query.strip():
    raise ValueError("query cannot be empty")
if k <= 0:
    raise ValueError("k must be positive")
```

---

### 2. Cache Check

**LRU Cache** (Least Recently Used):
- Stores last 100 search results
- Key format: `"{query}::{k}"`
- Cache hit → returns immediately

**Benefits**:
- Faster response for repeated queries
- Reduces OpenAI API calls
- Reduces Pinecone queries

---

### 3. Query Embedding

```python
query_embedding = await embeddings.aembed_query(query)
# Returns: [0.12, -0.45, ...] (1536 dimensions)
```

**Async Operation**: Uses `aembed_query` for non-blocking IO

---

### 4. Vector Search

```python
results = vector_store.query(
    query_embedding,
    top_k=k * OVERSEARCH_MULTIPLIER  # Get 2x to filter
)
```

**Oversearch Strategy**:
- Retrieves `k * 2` results
- Filters by confidence threshold
- Returns best `k` matches

**Why oversearch?**: Ensures we get `k` high-quality results even after filtering

---

### 5. Confidence Filtering

```python
if result.score >= CONFIDENCE_THRESHOLD:  # 0.50
    documents.append(result)
```

**Threshold**: 0.50 (50% similarity)

**Quality Assurance**: Only returns confident matches

---

### 6. Cache Update

```python
# LRU eviction
if len(cache) > max_size:
    oldest = cache_order.pop(0)
    del cache[oldest]
```

**Cache Management**:
- Adds new results to cache
- Evicts oldest entry if full
- Moves accessed entries to end (recently used)

---

## Configuration

### Constants

```python
# Module-level
OVERSEARCH_MULTIPLIER = 2  # Retrieve 2x results for filtering

# Class-level
CONFIDENCE_THRESHOLD = 0.50  # Minimum similarity score
```

**Customization**:
```python
# Adjust threshold for stricter matching
KnowledgeBase.CONFIDENCE_THRESHOLD = 0.70  # 70% similarity

# Adjust oversearch multiplier
OVERSEARCH_MULTIPLIER = 3  # Get 3x results
```

---

### Cache Configuration

```python
self._max_cache_size = 100  # Store 100 queries
```

**Customization**:
```python
kb = KnowledgeBase()
kb._max_cache_size = 200  # Larger cache
```

---

## Usage Examples

### Basic Search

```python
from app.services.rag.kb import KnowledgeBase

async def main():
    kb = KnowledgeBase()
    
    results = await kb.search("terminal configuration")
    
    for doc in results:
        print(f"Score: {doc.metadata['score']:.2f}")
        print(f"Source: {doc.metadata['source']}")
        print(f"Content: {doc.page_content[:200]}...\n")
```

---

### Search with Custom k

```python
# Get more results
results = await kb.search("refund policy", k=10)
print(f"Found {len(results)} results")

# Get fewer results  
results = await kb.search("setup", k=1)
```

---

### Error Handling

```python
from app.services.rag.kb import KnowledgeBase

async def safe_search(query: str) -> List[Document]:
    try:
        kb = KnowledgeBase()
        results = await kb.search(query, k=5)
        return results
        
    except ValueError as e:
        logger.error(f"Invalid input: {e}")
        return []
        
    except RuntimeError as e:
        logger.error(f"Search failed: {e}")
        return []
```

---

### In RAG Pipeline

```python
async def rag_query(user_question: str) -> str:
    # 1. Search knowledge base
    kb = KnowledgeBase()
    docs = await kb.search(user_question, k=3)
    
    if not docs:
        return "I couldn't find relevant information."
    
    # 2. Build context from results
    context = "\n\n".join([
        f"[{doc.metadata['source']}] {doc.page_content}"
        for doc in docs
    ])
    
    # 3. Generate answer with LLM
    answer = await llm.generate(question=user_question, context=context)
    return answer
```

---

## Caching

### How Cache Works

**LRU (Least Recently Used)**:
- Stores most recent 100 queries
- Evicts oldest when full
- Fast in-memory lookup

**Cache Key**:
```python
key = f"{query}::{k}"
# Example: "printer setup::3"
```

**Cache Hit**:
```python
# Query already searched
results = await kb.search("printer setup", k=3)
# Logs: "Cache hit for query: printer setup"
# Returns: Cached results (no API call)
```

---

### Cache Benefits

| Metric | No Cache | With Cache |
|--------|----------|------------|
| **Response Time** | ~500ms | ~1ms |
| **OpenAI Calls** | Every query | First time only |
| **Pinecone Queries** | Every query | First time only |
| **Cost** | ~$0.001/query | $0 (cached) |

---

### Cache Limitations

**Not persisted**: Cache clears on restart

**Size limited**: Only 100 queries

**No TTL**: Cached results never expire (until evicted)

---

## Error Handling

### ValueError: Empty Query

**Cause**: Query is empty or whitespace

**Example**:
```python
await kb.search("", k=3)
# ValueError: query cannot be empty
```

**Solution**: Validate query before searching

---

### ValueError: Invalid k

**Cause**: k is zero or negative

**Example**:
```python
await kb.search("query", k=0)
# ValueError: k must be positive
```

**Solution**: Use k ≥ 1

---

### RuntimeError: Search Failed

**Common Causes**:
1. **Pinecone connection error**: Network issue, invalid API key
2. **OpenAI embedding error**: Rate limit, invalid API key
3. **Vector store error**: Index not found

**Error Message**:
```python
RuntimeError: Knowledge base search failed: <original error>
```

**Logged**:
```
ERROR: Pinecone search failed for query 'printer setup': Connection timeout
```

**Solutions**:
- Check API keys in `.env`
- Verify Pinecone index exists
- Check network connectivity
- Review rate limits

---

## Best Practices

### 1. Reuse KnowledgeBase Instance

**✅ Good** (reuse):
```python
kb = KnowledgeBase()

for query in queries:
    results = await kb.search(query)
```

**❌ Bad** (recreate):
```python
for query in queries:
    kb = KnowledgeBase()  # Wasteful!
    results = await kb.search(query)
```

---

### 2. Use Appropriate k

```python
# For chatbot responses (quality over quantity)
results = await kb.search(query, k=3)

# For comprehensive search (more options)
results = await kb.search(query, k=10)
```

---

### 3. Check Result Count

```python
results = await kb.search(query, k=5)

if len(results) == 0:
    logger.warning(f"No results for query: {query}")
    # Fallback: web search or default response
elif len(results) < k:
    logger.info(f"Only {len(results)} results (threshold filtered)")
```

---

### 4. Monitor Scores

```python
for doc in results:
    score = doc.metadata['score']
    
    if score >= 0.80:
        logger.info(f"High confidence: {score:.2f}")
    elif score >= 0.60:
        logger.info(f"Medium confidence: {score:.2f}")
    else:
        logger.warning(f"Low confidence: {score:.2f}")
```

---

## Troubleshooting

### Issue: No results returned

**Symptom**: `search()` returns empty list

**Possible Causes**:
1. **No matching documents**: Query doesn't match indexed content
2. **Threshold too high**: All results below 0.50 score
3. **Empty index**: No documents ingested yet

**Debug**:
```python
# Temporarily lower threshold to see all results
KnowledgeBase.CONFIDENCE_THRESHOLD = 0.30
results = await kb.search(query)
```

---

### Issue: Low relevance scores

**Symptom**: Results have scores < 0.60

**Causes**:
- Query too vague
- Indexed documents don't cover topic
- Embedding mismatch (different terminology)

**Solutions**:
- Rephrase query with specific keywords
- Ingest more relevant documents
- Use domain-specific terminology

---

### Issue: Slow search performance

**Symptom**: Takes > 1 second per query

**Causes**:
- Cache miss (first-time query)
- Slow OpenAI embedding API
- Slow Pinecone query

**Performance**:
- **Cache hit**: ~1ms
- **Cache miss**: ~300-500ms (embedding + search)

**Optimization**:
- Pre-warm cache with common queries
- Use faster embedding model (if available)
- Reduce `OVERSEARCH_MULTIPLIER`

---

### Issue: Cache not working

**Symptom**: Every query shows as cache miss

**Debug**:
```python
kb = KnowledgeBase()
await kb.search("test", k=3)  # First call
await kb.search("test", k=3)  # Should hit cache
# Check logs for "Cache hit for query: test"
```

**Common Issues**:
- Different k values (cache key includes k)
- Different query strings (case-sensitive)
- Server restarts (cache is in-memory)

---

## Performance Characteristics

### Time Complexity

| Operation | Complexity | Notes |
|-----------|------------|-------|
| Initialization | O(1) | Creates clients |
| `search()` (cache hit) | O(1) | Dictionary lookup |
| `search()` (cache miss) | O(n) | n = vector dimension (1536) |

### API Calls

**Per search() call (cache miss)**:
- 1 OpenAI embedding call
- 1 Pinecone query

**Cost per query** (approximate):
- OpenAI embedding: ~$0.0001
- Pinecone query: ~$0.0001
- **Total**: ~$0.0002/query

---

## Related Documentation

- [Vector Store](./vector_store.md) - Pinecone integration
- [Document Grader](./grader.md) - Filters search results by relevance
- [RAG Core](../core/bot.md) - Uses KB for retrieval
- [Ingestion Pipeline](../services/ingestor/README.md) - How documents are indexed

