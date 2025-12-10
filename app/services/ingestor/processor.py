import logging
from typing import List
from langchain_core.documents import Document
from langchain_experimental.text_splitter import SemanticChunker
from langchain_openai import OpenAIEmbeddings
from app.core.config import settings

logger = logging.getLogger(__name__)

class DocumentProcessor:
    """Handles the transformation (chunking) of documents using semantic splitting."""
    
    def __init__(self):
        """Initialize DocumentProcessor with OpenAI embeddings and semantic chunker."""
        logger.info("Initializing DocumentProcessor with semantic chunking")
        self.embeddings = OpenAIEmbeddings(api_key=settings.OPENAI_API_KEY)
        self.text_splitter = SemanticChunker(self.embeddings)
        logger.info("DocumentProcessor initialized successfully")
        
    def chunk_documents(self, documents: List[Document]) -> List[Document]:
        """Split documents into semantic chunks.
        
        Args:
            documents: List of documents to chunk
            
        Returns:
            List of chunked documents
            
        Raises:
            RuntimeError: If chunking fails due to API errors or other issues
        """
        if not documents:
            return []
        
        try:
            logger.info(f"Semantically chunking {len(documents)} pages (Agentic Splitting)")
            chunks = self.text_splitter.split_documents(documents)
            logger.info(f"Generated {len(chunks)} knowledge chunks")
            return chunks
        except Exception as e:
            logger.error(f"Semantic chunking failed: {e}", exc_info=True)
            raise RuntimeError(f"Failed to chunk documents: {e}") from e
        
    def get_embeddings(self) -> OpenAIEmbeddings:
        """Get the OpenAI embeddings instance.
        
        Returns:
            OpenAIEmbeddings instance used for semantic chunking
        """
        return self.embeddings
