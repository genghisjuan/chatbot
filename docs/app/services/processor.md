# Document Processor Documentation

## Overview

**File**: [`app/services/ingestor/processor.py`](file:///c:/Users/John/.gemini/antigravity/scratch/support_chatbot/app/services/ingestor/processor.py)

The Document Processor module handles semantic chunking of documents using OpenAI embeddings. It splits large documents into semantically meaningful chunks for efficient vector storage and retrieval in the RAG pipeline.

---

## Table of Contents

1. [Summary](#summary)
2. [Class: DocumentProcessor](#class-documentprocessor)
3. [Methods](#methods)
4. [Semantic Chunking](#semantic-chunking)
5. [Usage Examples](#usage-examples)
6. [Error Handling](#error-handling)
7. [Best Practices](#best-practices)
8. [Troubleshooting](#troubleshooting)

---

## Summary

**Purpose**: Transform documents into semantically meaningful chunks for vector search

**Key Features**:
- ✅ **Semantic chunking** using OpenAI embeddings
- ✅ **Agentic splitting** - AI-powered chunk boundaries
- ✅ **Robust error handling** for API failures
- ✅ **Structured logging** with chunk counts

**Technology**:
- **Embeddings**: OpenAI text-embedding-ada-002 (via LangChain)
- **Chunker**: SemanticChunker from LangChain Experimental
- **Intelligence**: AI determines optimal chunk boundaries based on semantic meaning

---

## Class: DocumentProcessor

### Constructor

```python
def __init__(self):
```

**Purpose**: Initialize processor with OpenAI embeddings and semantic chunker

**Initialization**:
1. Creates `OpenAIEmbeddings` instance
2. Initializes `SemanticChunker` with embeddings
3. Logs successful initialization

**Raises**:
- `ValueError`: If OPENAI_API_KEY is not configured (handled by config.py)

**Example**:
```python
from app.services.ingestor.processor import DocumentProcessor

processor = DocumentProcessor()
# Logs: "Initializing DocumentProcessor with semantic chunking"
# Logs: "DocumentProcessor initialized successfully"
```

---

## Methods

### chunk_documents()

```python
def chunk_documents(self, documents: List[Document]) -> List[Document]:
```

**Purpose**: Split documents into semantic chunks using AI

**Parameters**:
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `documents` | `List[Document]` | Yes | List of LangChain Document objects to chunk |

**Returns**: `List[Document]` - List of chunked documents with preserved metadata

**Raises**:
- `RuntimeError`: If chunking fails (network error, API rate limit, etc.)

**Behavior**:
- Returns empty list if input is empty
- Uses AI to determine optimal chunk boundaries
- Preserves all document metadata in chunks
- Logs progress (start and completion)

**Example**:
```python
from langchain_core.documents import Document

# Load documents
docs = [
    Document(page_content="Long text...", metadata={"page": 1}),
    Document(page_content="More text...", metadata={"page": 2})
]

# Chunk semantically
processor = DocumentProcessor()
chunks = processor.chunk_documents(docs)

print(f"Input: {len(docs)} pages")
print(f"Output: {len(chunks)} chunks")
# Logs: "Semantically chunking 2 pages (Agentic Splitting)"
# Logs: "Generated 8 knowledge chunks"
```

---

### get_embeddings()

```python
def get_embeddings(self) -> OpenAIEmbeddings:
```

**Purpose**: Get the OpenAI embeddings instance

**Returns**: `OpenAIEmbeddings` - The embeddings instance used for chunking

**Use Case**: Access embeddings for vector storage or additional processing

**Example**:
```python
processor = DocumentProcessor()
embeddings = processor.get_embeddings()

# Use for embedding queries
query_vector = embeddings.embed_query("What is RAG?")
```

---

## Semantic Chunking

### What is Semantic Chunking?

**Traditional Chunking**:
```
Split by: Fixed size (500 chars) or delimiter (paragraphs)
Problem: Can split mid-sentence or mid-thought
```

**Semantic Chunking**:
```
Split by: Semantic meaning using AI embeddings
Benefit: Chunks are coherent, self-contained units of meaning
```

### How It Works

1. **Embed sentences**: Convert each sentence to vector embedding
2. **Calculate similarity**: Measure semantic similarity between adjacent sentences
3. **Find boundaries**: Split where similarity drops (topic change detected)
4. **Create chunks**: Group semantically related sentences

### Example

**Input Document**:
```
RAG stands for Retrieval Augmented Generation. It combines retrieval and generation.
[LOW SIMILARITY - TOPIC CHANGE]
Python is a programming language. It's used for AI development.
```

**Output Chunks**:
```
Chunk 1: "RAG stands for Retrieval Augmented Generation. It combines retrieval and generation."
Chunk 2: "Python is a programming language. It's used for AI development."
```

---

## Usage Examples

### Basic Usage

```python
from app.services.ingestor.processor import DocumentProcessor
from langchain_core.documents import Document

# Initialize
processor = DocumentProcessor()

# Prepare documents
docs = [Document(page_content="Long article text...", metadata={"source": "article.pdf"})]

# Chunk
chunks = processor.chunk_documents(docs)

# Review chunks
for i, chunk in enumerate(chunks):
    print(f"Chunk {i+1}: {chunk.page_content[:50]}...")
    print(f"Metadata: {chunk.metadata}")
```

---

### Full Pipeline Integration

```python
from app.services.ingestor.loaders import LoaderFactory
from app.services.ingestor.processor import DocumentProcessor

# 1. Load document
loader = LoaderFactory.get_loader("report.pdf")
documents = loader.load()
print(f"Loaded {len(documents)} pages")

# 2. Chunk semantically
processor = DocumentProcessor()
chunks = processor.chunk_documents(documents)
print(f"Created {len(chunks)} semantic chunks")

# 3. Store in vector DB (next step)
# store_in_pinecone(chunks)
```

---

### Error Handling

```python
import logging
from app.services.ingestor.processor import DocumentProcessor

logging.basicConfig(level=logging.INFO)

try:
    processor = DocumentProcessor()
    chunks = processor.chunk_documents(documents)
    print(f"✓ Chunked into {len(chunks)} pieces")
    
except RuntimeError as e:
    logger.error(f"✗ Chunking failed: {e}")
    # Fallback: Use simple text splitter
    from langchain.text_splitter import RecursiveCharacterTextSplitter
    splitter = RecursiveCharacterTextSplitter(chunk_size=500)
    chunks = splitter.split_documents(documents)
```

---

## Error Handling

### RuntimeError: API Failures

**Common Causes**:
1. **Network error**: Connection to OpenAI failed
2. **Rate limit**: Too many API requests
3. **Invalid API key**: Key expired or revoked
4. **Service outage**: OpenAI API down

**Error Message**:
```
RuntimeError: Failed to chunk documents: <original error>
```

**Logged Details**:
```
ERROR:...:Semantic chunking failed: Connection error
Traceback (most recent call last):
  ...
```

**Solution**:
```python
try:
    chunks = processor.chunk_documents(docs)
except RuntimeError as e:
    # Log the error
    logger.error(f"Chunking failed, using fallback: {e}")
    
    # Fallback to non-semantic chunking
    from langchain.text_splitter import CharacterTextSplitter
    splitter = CharacterTextSplitter(chunk_size=500, chunk_overlap=50)
    chunks = splitter.split_documents(docs)
```

---

### ValueError: Missing API Key

**Cause**: OPENAI_API_KEY not set in `.env` file

**Error**:
```
ValueError: OPENAI_API_KEY is required. Set it in .env file.
```

**Solution**: Set key in `.env` (handled by config.py validation):
```bash
OPENAI_API_KEY=sk-your-key-here
```

---

## Best Practices

### 1. Reuse Processor Instance

**✅ Good** (reuse):
```python
processor = DocumentProcessor()

for doc_batch in batches:
    chunks = processor.chunk_documents(doc_batch)
```

**❌ Bad** (recreate):
```python
for doc_batch in batches:
    processor = DocumentProcessor()  # Wasteful!
    chunks = processor.chunk_documents(doc_batch)
```

---

### 2. Handle Empty Documents

**✅ Good**:
```python
if documents:
    chunks = processor.chunk_documents(documents)
else:
    logger.warning("No documents to chunk")
    chunks = []
```

---

### 3. Monitor Chunk Counts

```python
chunks = processor.chunk_documents(docs)

# Sanity check
if len(chunks) == 0:
    logger.error("Chunking produced 0 chunks!")
elif len(chunks) > len(docs) * 100:
    logger.warning(f"Chunking produced {len(chunks)} chunks from {len(docs)} pages (unusually high)")
```

---

### 4. Preserve Metadata

Semantic chunking automatically preserves metadata:
```python
doc = Document(
    page_content="Text...",
    metadata={"source": "file.pdf", "page": 1}
)

chunks = processor.chunk_documents([doc])

# Each chunk retains original metadata
for chunk in chunks:
    print(chunk.metadata)  # {'source': 'file.pdf', 'page': 1}
```

---

## Troubleshooting

### Issue: Chunking is slow

**Symptom**: Taking minutes to chunk a few pages

**Cause**: SemanticChunker makes embeddings API call for each sentence

**Performance**:
- ~1-2 seconds per page (depends on length)
- Batch processing helps but still API-bound

**Optimization**:
```python
# For very large documents, consider:
# 1. Pre-split into pages/sections
# 2. Chunk each section in parallel
from concurrent.futures import ThreadPoolExecutor

def chunk_section(section):
    return processor.chunk_documents([section])

with ThreadPoolExecutor(max_workers=5) as executor:
    chunk_results = list(executor.map(chunk_section, page_list))
```

---

### Issue: Chunks are too large/small

**Problem**: Semantic chunker doesn't respect size limits

**Current**: Purely semantic (ignores token count)

**Workaround**: Post-process to split large chunks
```python
from langchain.text_splitter import RecursiveCharacterTextSplitter

chunks = processor.chunk_documents(docs)

# Split any chunk > 1000 tokens
final_chunks = []
splitter = RecursiveCharacterTextSplitter(chunk_size=1000)

for chunk in chunks:
    if len(chunk.page_content) > 4000:  # ~1000 tokens
        sub_chunks = splitter.split_documents([chunk])
        final_chunks.extend(sub_chunks)
    else:
        final_chunks.append(chunk)
```

---

### Issue: "Failed to chunk documents"

**Debug Steps**:
1. **Check API key**: Verify `.env` has valid key
2. **Test embeddings directly**:
   ```python
   embeddings = processor.get_embeddings()
   test = embeddings.embed_query("test")
   print(f"Embedding dimension: {len(test)}")
   ```
3. **Check network**: Ensure internet connectivity
4. **Review logs**: Look for specific error in `exc_info=True` output

---

## Performance Characteristics

### Time Complexity

| Operation | Complexity | Notes |
|-----------|------------|-------|
| Initialization | O(1) | Creates clients |
| Chunking | O(n * s) | n = pages, s = sentences per page (API calls) |

### API Calls

**Per chunk_documents() call**:
- ~1 API call per sentence
- Example: 10 pages × 20 sentences/page = ~200 API calls
- Cost: ~$0.001 per 1000 sentences (embedding model cost)

### Memory Usage

- **Low**: Processes documents one at a time
- **Peak**: ~2x document size (original + chunks)

---

## Related Documentation

- [Document Loaders](./loaders.md) - Load documents before chunking
- [Ingestion Pipeline](./README.md) - Full document ingestion flow
- [RAG Core](../../core/bot.md) - How chunks are used for retrieval
- [LangChain SemanticChunker](https://python.langchain.com/docs/modules/data_connection/document_transformers/semantic-chunker)

