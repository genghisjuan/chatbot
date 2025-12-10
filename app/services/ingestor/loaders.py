import os
import logging
from typing import List
from abc import ABC, abstractmethod
from langchain_core.documents import Document
from langchain_community.document_loaders import Docx2txtLoader, TextLoader
from app.services.ingestor.vision_loader import VisionPDFLoader

logger = logging.getLogger(__name__)

class BaseLoader(ABC):
    """Base class for all file loaders."""
    def __init__(self, file_path: str):
        if not file_path:
            raise ValueError("file_path cannot be empty")
        if not os.path.isfile(file_path):
            raise FileNotFoundError(f"File not found: {file_path}")
        self.file_path = file_path
    
    @abstractmethod
    def load(self) -> List[Document]:
        """Load and return documents from file."""
        pass

class CustomDocxLoader(BaseLoader):
    """Handles Word (.docx) files."""
    def load(self) -> List[Document]:
        try:
            logger.info(f"Parsing DOCX: {os.path.basename(self.file_path)}")
            loader = Docx2txtLoader(self.file_path)
            docs = loader.load()
            logger.info(f"Loaded {len(docs)} document(s) from DOCX")
            return docs
        except FileNotFoundError:
            raise FileNotFoundError(f"DOCX file not found: {self.file_path}")
        except Exception as e:
            raise RuntimeError(f"Failed to load DOCX '{self.file_path}': {e}") from e

class CustomTextLoader(BaseLoader):
    """Handles Text (.txt, .md) files."""
    def load(self) -> List[Document]:
        try:
            logger.info(f"Parsing text file: {os.path.basename(self.file_path)}")
            loader = TextLoader(self.file_path, autodetect_encoding=True)
            docs = loader.load()
            logger.info(f"Loaded {len(docs)} document(s) from text file")
            return docs
        except FileNotFoundError:
            raise FileNotFoundError(f"Text file not found: {self.file_path}")
        except Exception as e:
            raise RuntimeError(f"Failed to load text file '{self.file_path}': {e}") from e

class LoaderFactory:
    """Factory to get the right loader for a file extension."""
    
    SUPPORTED_FORMATS = ['.pdf', '.docx', '.txt', '.md']
    
    @staticmethod
    def get_loader(file_path: str) -> BaseLoader:
        """
        Get appropriate loader for file based on extension.
        
        Args:
            file_path: Path to file to load
            
        Returns:
            BaseLoader instance for the file type
            
        Raises:
            ValueError: If file_path is invalid or format unsupported
        """
        if not file_path or not isinstance(file_path, str):
            raise ValueError("file_path must be a non-empty string")
        
        ext = os.path.splitext(file_path)[1].lower()
        
        if ext == '.pdf':
            return VisionPDFLoader(file_path)
        elif ext == '.docx':
            return CustomDocxLoader(file_path)
        elif ext in ['.txt', '.md']:
            return CustomTextLoader(file_path)
        else:
            raise ValueError(
                f"Unsupported file format: '{ext}'. "
                f"Supported formats: {', '.join(LoaderFactory.SUPPORTED_FORMATS)}"
            )
