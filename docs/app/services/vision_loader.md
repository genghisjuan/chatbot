# Vision PDF Loader Documentation

## Overview

**File**: [`app/services/ingestor/vision_loader.py`](file:///c:/Users/John/.gemini/antigravity/scratch/support_chatbot/app/services/ingestor/vision_loader.py)

The Vision PDF Loader uses OpenAI's GPT-4o Vision API to analyze PDF pages as images. Unlike traditional text extraction, this loader can "see" diagrams, screenshots, charts, and mixed content, making it ideal for complex technical documentation.

---

## Table of Contents

1. [Summary](#summary)
2. [How It Works](#how-it-works)
3. [Class: VisionPDFLoader](#class-visionpdfloader)
4. [Configuration](#configuration)
5. [Usage Examples](#usage-examples)
6. [Error Handling](#error-handling)
7. [Performance & Costs](#performance--costs)
8. [Best Practices](#best-practices)
9. [Troubleshooting](#troubleshooting)

---

## Summary

**Purpose**: Extract content from PDFs using AI vision analysis

**Key Features**:
- ✅ **Vision-based OCR** - Extracts text from scanned documents
- ✅ **Diagram description** - Describes charts, screenshots, UI elements
- ✅ **Mixed content** - Handles text + images on same page
- ✅ **High quality** - Uses GPT-4o for accurate transcription

**Best For**:
- Technical documentation with screenshots
- Scanned documents (OCR)
- PDFs with diagrams, charts, flowcharts
- Mixed text/image content

**Not Ideal For**:
- Plain text PDFs (use PyPDFLoader - faster and cheaper)
- Very large PDFs (slow and expensive)

---

## How It Works

### Process Flow

1. **Render PDF page to image** (144 DPI)
2. **Resize if too large** (to control API costs)
3. **Encode image to base64**
4. **Send to GPT-4o Vision API**
5. **Receive Markdown transcription**
6. **Create LangChain Document**

### Example

**Input**: PDF page with screenshot of settings menu

**Vision API receives**:
```
Image: [base64-encoded PNG of page]
Prompt: "Transcribe this PDF page into clean Markdown..."
```

**Vision API returns**:
```markdown
# Settings Menu

A screenshot showing the Transafe Settings interface with the following fields:
- Terminal ID: TRM-12345
- Merchant Name: ABC Store
- Enable Tips: [Checked]
```

---

## Class: VisionPDFLoader

### Constructor

```python
def __init__(self, file_path: str):
```

**Parameters**:
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `file_path` | `str` | Yes | Path to PDF file |

**Raises**:
- `ValueError`: If `file_path` is empty
- `FileNotFoundError`: If PDF doesn't exist

**Example**:
```python
from app.services.ingestor.vision_loader import VisionPDFLoader

loader = VisionPDFLoader("technical_guide.pdf")
```

---

### load()

```python
def load(self) -> List[Document]:
```

**Purpose**: Load and analyze PDF using vision

**Returns**: `List[Document]` - One document per page with vision-extracted content

**Raises**:
- `FileNotFoundError`: If PDF file not found
- `RuntimeError`: If PDF loading or vision analysis fails

**Process**:
1. Opens PDF with PyMuPDF
2. For each page:
   - Renders to image
   - Analyzes with Vision API
   - Creates Document with metadata
3. Returns list of documents

**Example**:
```python
loader = VisionPDFLoader("manual.pdf")
documents = loader.load()

for doc in documents:
    print(f"Page {doc.metadata['page']}: {doc.page_content[:100]}...")
```

---

## Configuration

### Constants

Located at module level (lines 12-18):

```python
OPENAI_API_ENDPOINT = "https://api.openai.com/v1/chat/completions"
DEFAULT_ZOOM = 2.0  # 144 DPI for good OCR quality
FALLBACK_ZOOM = 1.0  # 72 DPI for large pages (cost optimization)
MAX_IMAGE_DIMENSION = 2000  # Resize if larger to control costs
MAX_RESPONSE_TOKENS = 2000  # Sufficient for most PDF pages
REQUEST_TIMEOUT = 60  # Seconds
```

**Customization**:
```python
# Adjust zoom for higher/lower quality
DEFAULT_ZOOM = 1.5  # Lower DPI (faster, cheaper)
DEFAULT_ZOOM = 3.0  # Higher DPI (better quality, slower)

# Adjust timeout for slow networks
REQUEST_TIMEOUT = 120  # 2 minutes
```

---

## Usage Examples

### Basic Usage

```python
from app.services.ingestor.vision_loader import VisionPDFLoader

# Load PDF
loader = VisionPDFLoader("user_guide.pdf")
docs = loader.load()

print(f"Extracted {len(docs)} pages")
for doc in docs:
    print(f"Page {doc.metadata['page']}: {len(doc.page_content)} chars")
```

---

### With LoaderFactory

```python
from app.services.ingestor.loaders import LoaderFactory

# Factory automatically uses VisionPDFLoader for PDFs
loader = LoaderFactory.get_loader("document.pdf")
docs = loader.load()
```

---

### Error Handling

```python
import logging
from app.services.ingestor.vision_loader import VisionPDFLoader

logging.basicConfig(level=logging.INFO)

try:
    loader = VisionPDFLoader("manual.pdf")
    docs = loader.load()
    print(f"✓ Loaded {len(docs)} pages")
    
except FileNotFoundError as e:
    print(f"✗ PDF not found: {e}")
except RuntimeError as e:
    print(f"✗ Vision analysis failed: {e}")
```

---

### Processing Results

```python
loader = VisionPDFLoader("guide.pdf")
docs = loader.load()

for doc in docs:
    # Access content
    content = doc.page_content
    
    # Access metadata
    source = doc.metadata["source"]  # File path
    page_num = doc.metadata["page"]  # Page number (1-indexed)
    method = doc.metadata["method"]  # "gpt-4o-vision"
    
    print(f"Page {page_num} from {source}:")
    print(content[:200])
```

---

## Error Handling

### FileNotFoundError

**Cause**: PDF file doesn't exist

**Example**:
```python
try:
    loader = VisionPDFLoader("/nonexistent.pdf")
except FileNotFoundError as e:
    # "PDF file not found: /nonexistent.pdf"
```

**Solution**: Verify file path before loading

---

### RuntimeError: Corrupted PDF

**Cause**: PDF file is damaged or invalid

**Example**:
```python
try:
    loader = VisionPDFLoader("corrupted.pdf")
    docs = loader.load()
except RuntimeError as e:
    # "Corrupted or invalid PDF: corrupted.pdf"
```

**Solution**: Validate PDF with PyMuPDF before processing

---

### RuntimeError: Vision API Failed

**Common Causes**:
1. **Invalid API key**: `OPENAI_API_KEY` incorrect
2. **Network error**: Connection to OpenAI failed
3. **Rate limit**: Too many requests
4. **Service outage**: OpenAI API down

**Error Message**:
```
RuntimeError: Vision API failed for page 5: 401 Client Error: Unauthorized
```

**Logged Details**:
```
ERROR:...:Vision API HTTP error for page 5: 401
```

**Solutions**:
- **401**: Check `OPENAI_API_KEY` in `.env`
- **429**: Rate limited - add delays between requests
- **500/503**: OpenAI service issue - retry later
- **Timeout**: Network slow - increase `REQUEST_TIMEOUT`

---

### RuntimeError: API Timeout

**Cause**: Vision API didn't respond within 60 seconds

**Error**:
```
RuntimeError: Vision API timeout for page 3
```

**Solution**: Increase timeout or check network
```python
# In vision_loader.py
REQUEST_TIMEOUT = 120  # Increase to 2 minutes
```

---

## Performance & Costs

### Speed

| Metric | Typical Value |
|--------|---------------|
| **Per page** | 3-5 seconds |
| **10-page PDF** | 30-50 seconds |
| **Rate limit** | ~50 requests/minute (OpenAI) |

**Slow?**:
- Large images take longer
- Complex pages take longer
- Network latency matters

---

### API Costs

**GPT-4o Vision Pricing** (as of 2024):
- **Low detail**: $0.01275 per image
- **High detail**: $0.01275 + $0.00255 per 512px tile

**This loader uses "high" detail** for better OCR quality

**Example Cost**:
```
10-page PDF × $0.015/page = ~$0.15
100-page PDF = ~$1.50
```

**Cost Optimization**:
1. Use `FALLBACK_ZOOM` for large images (already implemented)
2. Skip pages with only text (use PyPDFLoader instead)
3. Batch process during off-peak hours

---

### Memory Usage

- **Per page**: ~5-10 MB (image rendering)
- **Peak**: Processes one page at a time (low memory footprint)

---

## Best Practices

### 1. Use for Mixed Content Only

**✅ Good** (needs vision):
```python
# PDF with screenshots, diagrams
loader = VisionPDFLoader("technical_manual.pdf")
```

**❌ Bad** (plain text):
```python
# Plain text PDF - use PyPDFLoader instead (faster, cheaper)
loader = VisionPDFLoader("text_only.pdf")
```

---

### 2. Validate Files First

**✅ Good**:
```python
import os

if os.path.isfile(pdf_path) and pdf_path.endswith('.pdf'):
    loader = VisionPDFLoader(pdf_path)
    docs = loader.load()
```

---

### 3. Monitor Costs

```python
import logging

logging.basicConfig(level=logging.INFO)

loader = VisionPDFLoader("guide.pdf")
docs = loader.load()

# Logs will show:
# "Processing 25 pages..." 
# Estimate: 25 pages × $0.015 = ~$0.375
```

---

### 4. Handle Timeouts Gracefully

```python
try:
    docs = loader.load()
except RuntimeError as e:
    if "timeout" in str(e).lower():
        logger.warning(f"Timeout on page, retrying...")
        # Retry logic or skip page
```

---

## Troubleshooting

### Issue: "Vision API failed: 401 Unauthorized"

**Cause**: Invalid `OPENAI_API_KEY`

**Solution**:
1. Check `.env` file: `OPENAI_API_KEY=sk-your-key`
2. Verify key at https://platform.openai.com/api-keys
3. Restart application to reload env vars

---

### Issue: All pages fail with same error

**Cause**: Systematic issue (API key, network, etc.)

**Debug**:
```python
# Test Vision API directly
import requests

headers = {"Authorization": f"Bearer {settings.OPENAI_API_KEY}"}
response = requests.get("https://api.openai.com/v1/models", headers=headers)
print(response.status_code)  # Should be 200
```

---

### Issue: Some pages fail, others succeed

**Cause**: Specific pages cause errors (too large, corrupted, etc.)

**Debug**:
```python
# Process pages individually
for i in range(len(doc)):
    try:
        # Process page i
    except RuntimeError as e:
        logger.error(f"Page {i+1} failed: {e}")
        continue  # Skip and continue
```

---

### Issue: Very slow processing

**Symptoms**: Taking >10s per page

**Possible Causes**:
1. **Network latency**: Slow connection to OpenAI
2. **Large images**: Pages rendering at high DPI
3. **Complex content**: AI taking longer to analyze

**Solutions**:
- Check network speed
- Reduce `DEFAULT_ZOOM` to 1.5 or 1.0
- Process in batches during off-peak hours

---

### Issue: Poor OCR quality

**Symptoms**: Text extracted incorrectly

**Causes**:
1. **Low resolution**: `DEFAULT_ZOOM` too low
2. **Image quality**: Scanned PDF low quality
3. **Complex fonts**: Unusual fonts hard to read

**Solutions**:
```python
# Increase zoom for better quality
DEFAULT_ZOOM = 2.5  # Higher DPI

# Or re-scan source document at higher DPI
```

---

## Related Documentation

- [Document Loaders](./loaders.md) - LoaderFactory uses this for PDFs
- [Document Processor](./processor.md) - Chunks vision-extracted text
- [Ingestion Pipeline](./README.md) - Full document ingestion flow
- [OpenAI Vision API](https://platform.openai.com/docs/guides/vision)

