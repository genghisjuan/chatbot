import fitz  # PyMuPDF
import base64
import requests
import logging
from typing import List
from langchain_core.documents import Document
from app.core.config import settings
import os

logger = logging.getLogger(__name__)

# Vision API Configuration
OPENAI_API_ENDPOINT = "https://api.openai.com/v1/chat/completions"
DEFAULT_ZOOM = 2.0  # 144 DPI for good OCR quality
FALLBACK_ZOOM = 1.0  # 72 DPI for large pages (cost optimization)
MAX_IMAGE_DIMENSION = 2000  # Resize if larger to control costs
MAX_RESPONSE_TOKENS = 2000  # Sufficient for most PDF pages
REQUEST_TIMEOUT = 60  # Seconds

class VisionPDFLoader:
    """
    Advanced PDF loader using GPT-4o Vision to analyze page images.
    
    Extracts text, charts, diagrams, and screenshots from PDF pages by:
    1. Rendering each page to a high-quality image
    2. Sending to GPT-4o Vision API for analysis
    3. Receiving detailed Markdown transcription
    
    This loader can extract content from:
    - Text-based PDFs
    - Scanned documents (OCR via Vision)
    - Pages with diagrams, charts, screenshots
    - Mixed content pages
    
    Args:
        file_path: Path to PDF file to load
    """
    def __init__(self, file_path: str):
        """Initialize VisionPDFLoader.
        
        Args:
            file_path: Path to PDF file
            
        Raises:
            ValueError: If file_path is empty
            FileNotFoundError: If PDF file doesn't exist
        """
        if not file_path:
            raise ValueError("file_path cannot be empty")
        if not os.path.isfile(file_path):
            raise FileNotFoundError(f"PDF file not found: {file_path}")
        
        self.file_path = file_path
        self.api_key = settings.OPENAI_API_KEY

    def _encode_image(self, pix_bytes: bytes) -> str:
        """Encode image bytes to base64 string.
        
        Args:
            pix_bytes: Raw image bytes from PyMuPDF pixmap
            
        Returns:
            Base64-encoded string
        """
        return base64.b64encode(pix_bytes).decode('utf-8')

    def load(self) -> List[Document]:
        """Load and analyze PDF using vision.
        
        Returns:
            List of Document objects with vision-extracted content
            
        Raises:
            FileNotFoundError: If PDF file not found
            RuntimeError: If PDF loading or vision analysis fails
        """
        try:
            doc = fitz.open(self.file_path)
            documents = []
            
            logger.info(f"Processing {len(doc)} pages in {os.path.basename(self.file_path)} with vision analysis")

            for i, page in enumerate(doc):
                # Render page to image
                zoom = DEFAULT_ZOOM
                mat = fitz.Matrix(zoom, zoom)
                pix = page.get_pixmap(matrix=mat)
                
                # Smart resize: if too large, scale down to avoid high costs
                if pix.width > MAX_IMAGE_DIMENSION or pix.height > MAX_IMAGE_DIMENSION:
                    logger.info(f"Page {i+1}: Resizing large image ({pix.width}x{pix.height})")
                    zoom = FALLBACK_ZOOM
                    mat = fitz.Matrix(zoom, zoom)
                    pix = page.get_pixmap(matrix=mat)
                
                img_data = pix.tobytes("png")
                base64_image = self._encode_image(img_data)
                
                # Analyze page with Vision API
                description = self._analyze_page(base64_image, page_num=i+1)
                
                # Create document
                documents.append(Document(
                    page_content=description,
                    metadata={"source": self.file_path, "page": i+1, "method": "gpt-4o-vision"}
                ))
                logger.info(f"Page {i+1}: Analyzed ({len(description)} chars)")

            doc.close()
            return documents
            
        except FileNotFoundError:
            raise
        except fitz.FileDataError as e:
            raise RuntimeError(f"Corrupted or invalid PDF: {self.file_path}") from e
        except Exception as e:
            logger.error(f"Failed to load PDF with vision: {e}", exc_info=True)
            raise RuntimeError(f"Failed to load PDF '{self.file_path}': {e}") from e

    def _analyze_page(self, base64_image: str, page_num: int) -> str:
        """Analyze page image using GPT-4o Vision.
        
        Args:
            base64_image: Base64-encoded page image
            page_num: Page number for logging
            
        Returns:
            Markdown-formatted page content
            
        Raises:
            RuntimeError: If API call fails
        """
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}"
        }

        payload = {
            "model": "gpt-4o",
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": "Transcribe this PDF page into clean Markdown text.\n"
                                    "1. Extract ALL text exactly as written.\n"
                                    "2. If there are screenshots, diagrams, or UI elements, DESCRIBE them in detail (e.g. 'A screenshot of the Transafe Settings menu showing the Terminal ID field').\n"
                                    "3. Do not include 'This page contains...' intro text. Just the content."
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/png;base64,{base64_image}",
                                "detail": "high"  # 1080p mode
                            }
                        }
                    ]
                }
            ],
            "max_tokens": MAX_RESPONSE_TOKENS
        }

        try:
            response = requests.post(
                OPENAI_API_ENDPOINT,
                headers=headers,
                json=payload,
                timeout=REQUEST_TIMEOUT
            )
            response.raise_for_status()
            result = response.json()
            return result['choices'][0]['message']['content']
            
        except requests.HTTPError as e:
            logger.error(f"Vision API HTTP error for page {page_num}: {e.response.status_code}")
            raise RuntimeError(f"Vision API failed for page {page_num}: {e}") from e
        except requests.Timeout as e:
            logger.error(f"Vision API timeout for page {page_num}")
            raise RuntimeError(f"Vision API timeout for page {page_num}") from e
        except Exception as e:
            logger.error(f"Unexpected error analyzing page {page_num}: {e}", exc_info=True)
            raise RuntimeError(f"Failed to analyze page {page_num}: {e}") from e
