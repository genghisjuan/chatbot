# File Loaders Documentation

## Overview

**File**: [`app/services/ingestor/loaders.py`](file:///c:/Users/John/.gemini/antigravity/scratch/support_chatbot/app/services/ingestor/loaders.py)

The File Loaders module provides a factory pattern for loading different document types (PDF, DOCX, TXT, MD) into LangChain Document objects. It uses specialized loaders for each file type and provides consistent error handling and logging.

---

## Table of Contents

1. [Summary](#summary)
2. [Architecture](#architecture)
3. [Classes](#classes)
4. [Usage Examples](#usage-examples)
5. [Supported Formats](#supported-formats)
6. [Error Handling](#error-handling)
7. [Best Practices](#best-practices)
8. [Troubleshooting](#troubleshooting)

---

## Summary

**Purpose**: Load various document types into LangChain Document objects for ingestion

**Key Features**:
- ✅ **Factory pattern** for automatic loader selection
- ✅ **Multiple file types** (PDF, DOCX, TXT, MD)
- ✅ **Robust error handling** with specific exceptions
- ✅ **Structured logging** with document counts
- ✅ **Input validation** and file existence checks

**Supported Formats**:
- **PDF**: Vision-enhanced parsing with VisionPDFLoader
- **DOCX**: Microsoft Word documents
- **TXT/MD**: Plain text and Markdown files

---

## Architecture

### Class Hierarchy

```
BaseLoader (ABC)
    ├── CustomDocxLoader
    ├── CustomTextLoader
    └── (VisionPDFLoader - from vision_loader.py)

LoaderFactory (static helper)
```

### Design Pattern

**Factory Pattern**: `LoaderFactory.get_loader()` returns appropriate loader based on file extension

**Benefits**:
- Single entry point for all file types
- Easy to add new file types
- Consistent interface via ABC

---

## Classes

### BaseLoader (Abstract Base Class)

```python
class BaseLoader(ABC):
    def __init__(self, file_path: str):
    
    @abstractmethod
    def load(self) -> List[Document]:
```

**Purpose**: Abstract base class defining the loader interface

**Constructor Parameters**:
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `file_path` | `str` | Yes | Path to file to load |

**Validation**:
- Checks `file_path` is not empty
- Verifies file exists using `os.path.isfile()`

**Raises**:
- `ValueError`: If `file_path` is empty
- `FileNotFoundError`: If file doesn't exist

---

### CustomDocxLoader

```python
class CustomDocxLoader(BaseLoader):
    def load(self) -> List[Document]:
```

**Purpose**: Load Microsoft Word (.docx) files

**Uses**: `Docx2txtLoader` from LangChain

**Example**:
```python
loader = CustomDocxLoader("report.docx")
docs = loader.load()
# Returns: List of Document objects
```

**Logging**:
- Start: `"Parsing DOCX: report.docx"`
- Success: `"Loaded 3 document(s) from DOCX"`

**Raises**:
- `FileNotFoundError`: If DOCX file not found
- `RuntimeError`: If loading fails (corrupted, permission denied, etc.)

---

### CustomTextLoader

```python
class CustomTextLoader(BaseLoader):
    def load(self) -> List[Document]:
```

**Purpose**: Load plain text (.txt) and Markdown (.md) files

**Uses**: `TextLoader` from LangChain with `autodetect_encoding=True`

**Example**:
```python
loader = CustomTextLoader("notes.md")
docs = loader.load()
```

**Logging**:
- Start: `"Parsing text file: notes.md"`
- Success: `"Loaded 1 document(s) from text file"`

**Raises**:
- `FileNotFoundError`: If text file not found
- `RuntimeError`: If loading fails (encoding issues, permission denied, etc.)

---

### LoaderFactory

```python
class LoaderFactory:
    SUPPORTED_FORMATS = ['.pdf', '.docx', '.txt', '.md']
    
    @staticmethod
    def get_loader(file_path: str) -> BaseLoader:
```

**Purpose**: Factory to select appropriate loader based on file extension

**Parameters**:
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `file_path` | `str` | Yes | Path to file |

**Returns**: `BaseLoader` - Appropriate loader instance

**Extension Mapping**:
| Extension | Loader Class |
|-----------|--------------|
| `.pdf` | `VisionPDFLoader` |
| `.docx` | `CustomDocxLoader` |
| `.txt` | `CustomTextLoader` |
| `.md` | `CustomTextLoader` |

**Raises**:
- `ValueError`: If `file_path` is invalid or format unsupported

---

## Usage Examples

### Basic Usage

```python
from app.services.ingestor.loaders import LoaderFactory

# Automatic loader selection
loader = LoaderFactory.get_loader("document.pdf")
documents = loader.load()

print(f"Loaded {len(documents)} pages")
```

---

### Processing Multiple Files

```python
import os
from app.services.ingestor.loaders import LoaderFactory

file_paths = ["report.pdf", "notes.docx", "readme.md"]

for file_path in file_paths:
    try:
        loader = LoaderFactory.get_loader(file_path)
        docs = loader.load()
        print(f"✓ {file_path}: {len(docs)} documents")
    except Exception as e:
        print(f"✗ {file_path}: {e}")
```

---

### With Error Handling

```python
from app.services.ingestor.loaders import LoaderFactory
import logging

logging.basicConfig(level=logging.INFO)

try:
    loader = LoaderFactory.get_loader("document.pdf")
    documents = loader.load()
    
    # Process documents
    for doc in documents:
        print(f"Content: {doc.page_content[:100]}...")
        print(f"Metadata: {doc.metadata}")
        
except FileNotFoundError as e:
    logger.error(f"File not found: {e}")
except ValueError as e:
    logger.error(f"Invalid file type: {e}")
except RuntimeError as e:
    logger.error(f"Loading failed: {e}")
```

---

## Supported Formats

### PDF Files (.pdf)

**Loader**: `VisionPDFLoader`

**Features**:
- Vision-enhanced parsing (can extract from images/scans)
- Supports multi-page documents
- Extracts text and metadata

**Limitations**:
- Large files may be slow
- Requires OpenAI API key for vision features

---

### Word Documents (.docx)

**Loader**: `CustomDocxLoader`

**Features**:
- Native Word document parsing
- Preserves formatting (to some extent)
- Fast processing

**Limitations**:
- Only supports `.docx` (not `.doc`)
- Complex formatting may not be fully preserved

---

### Text Files (.txt, .md)

**Loader**: `CustomTextLoader`

**Features**:
- Auto-detects encoding (UTF-8, ASCII, etc.)
- Supports plain text and Markdown
- Very fast

**Limitations**:
- No formatting preservation
- Large files loaded entirely into memory

---

## Error Handling

### FileNotFoundError

**Cause**: File doesn't exist at given path

**Example**:
```python
try:
    loader = LoaderFactory.get_loader("/nonexistent.pdf")
except FileNotFoundError as e:
    # "File not found: /nonexistent.pdf"
```

**Solution**: Verify file path before calling

---

### ValueError

**Cause 1**: Empty or invalid `file_path`
```python
LoaderFactory.get_loader("")  # raises ValueError
LoaderFactory.get_loader(None)  # raises ValueError
```

**Cause 2**: Unsupported file format
```python
LoaderFactory.get_loader("file.xyz")
# ValueError: Unsupported file format: '.xyz'. 
# Supported formats: .pdf, .docx, .txt, .md
```

---

### RuntimeError

**Cause**: File loading failed (corrupted, permission denied, etc.)

**Example**:
```python
try:
    loader = LoaderFactory.get_loader("corrupted.pdf")
    docs = loader.load()
except RuntimeError as e:
    # "Failed to load PDF 'corrupted.pdf': <error details>"
```

**Common Causes**:
- Corrupted file
- Permission denied
- File locked by another process
- Encoding issues (text files)

---

## Best Practices

### 1. Always Use Factory

**✅ Good**:
```python
loader = LoaderFactory.get_loader(file_path)
```

**❌ Bad**:
```python
# Don't directly instantiate loaders
loader = CustomDocxLoader(file_path)  # Harder to maintain
```

---

### 2. Handle Errors Gracefully

**✅ Good**:
```python
try:
    loader = LoaderFactory.get_loader(file_path)
    docs = loader.load()
except (FileNotFoundError, ValueError, RuntimeError) as e:
    logger.error(f"Failed to load {file_path}: {e}")
    continue  # Skip to next file
```

**❌ Bad**:
```python
docs = loader.load()  # Unhandled crash
```

---

### 3. Validate Files First

**✅ Good**:
```python
import os

if os.path.isfile(file_path):
    loader = LoaderFactory.get_loader(file_path)
    docs = loader.load()
else:
    logger.warning(f"Skipping missing file: {file_path}")
```

---

### 4. Use Logging

Enable logging to see progress:
```python
import logging
logging.basicConfig(level=logging.INFO)

# Will see:
# INFO:...:Parsing PDF: document.pdf
# INFO:...:Loaded 5 pages from PDF
```

---

## Troubleshooting

### Issue: "Unsupported file format"

**Cause**: File extension not in `SUPPORTED_FORMATS`

**Solution**: Convert file or add support for new format

**Example**:
```
Error: Unsupported file format: '.pptx'. 
Supported formats: .pdf, .docx, .txt, .md
```

**To add new format**, extend:
1. Create new loader class (inherits `BaseLoader`)
2. Add extension to `LoaderFactory.SUPPORTED_FORMATS`
3. Add `elif` clause in `get_loader()`

---

### Issue: "Failed to load PDF" (RuntimeError)

**Possible Causes**:
1. **Corrupted PDF**: File is damaged
2. **Permission denied**: No read access
3. **File locked**: Opened in another program
4. **Missing dependencies**: PIL/Pillow not installed for vision

**Debug**:
```python
import logging
logging.basicConfig(level=logging.DEBUG)

# Will show detailed error info
```

---

### Issue: Encoding errors with text files

**Symptom**:
```
RuntimeError: Failed to load text file: 'utf-8' codec can't decode...
```

**Cause**: File has non-UTF-8 encoding

**Solution**: `CustomTextLoader` uses `autodetect_encoding=True` which should handle most cases. If still failing, file may be binary or very unusual encoding.

---

### Issue: Memory issues with large files

**Symptom**: High memory usage or crash

**Cause**: Entire file loaded into memory

**Solution**:
- For PDFs: Already loads in chunks (VisionPDFLoader handles this)
- For text files: Consider streaming or chunk-based loading for files > 100MB

---

## Performance Considerations

### File Type Performance

| Format | Speed | Memory | Notes |
|--------|-------|--------|-------|
| TXT/MD | Very Fast | Low | Direct text read |
| DOCX | Fast | Medium | Native parsing |
| PDF | Slow | High | Vision processing via OpenAI API |

### Optimization Tips

1. **Batch processing**: Load multiple files in parallel (use threading/multiprocessing)
2. **Cache results**: Don't re-load unchanged files (use HashManager)
3. **Filter by extension**: Check extension before calling factory
4. **Limit file size**: Reject files > certain size threshold

---

## Related Documentation

- [VisionPDFLoader](./vision_loader.md) - Vision-enhanced PDF parsing
- [Document Ingestion](./README.md) - Full ingestion pipeline
- [HashManager](./hash_manager.md) - Prevents re-processing unchanged files

