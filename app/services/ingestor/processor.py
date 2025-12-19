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
        """Split documents into semantic chunks with hierarchical metadata.
        
        Args:
            documents: List of documents to chunk
            
        Returns:
            List of chunked documents with metadata:
            - chunk_id: Unique identifier for the chunk
            - chunk_index: Position in document (0-indexed)
            - total_chunks: Total chunks from source document
            - has_siblings: Whether chunk has siblings
            
        Raises:
            RuntimeError: If chunking fails due to API errors or other issues
        """
        if not documents:
            return []
        
        try:
            logger.info(f"Semantically chunking {len(documents)} pages (Agentic Splitting)")
            chunks = self.text_splitter.split_documents(documents)
            
            # Add hierarchical metadata for context assembly
            chunks = self._add_chunk_metadata(chunks)
            
            logger.info(f"Generated {len(chunks)} knowledge chunks with metadata")
            return chunks
        except Exception as e:
            logger.error(f"Semantic chunking failed: {e}", exc_info=True)
            raise RuntimeError(f"Failed to chunk documents: {e}") from e
    
    def _add_chunk_metadata(self, chunks: List[Document]) -> List[Document]:
        """Add hierarchical metadata to chunks for dynamic context assembly.
        
        Groups chunks by source document and adds:
        - chunk_id: Unique identifier
        - chunk_index: Position in source group
        - total_chunks: Total chunks from same source
        - has_siblings: Whether other chunks exist from same source
        """
        # Group chunks by source
        source_groups = {}
        for chunk in chunks:
            source = chunk.metadata.get('source', 'unknown')
            if source not in source_groups:
                source_groups[source] = []
            source_groups[source].append(chunk)
        
        # Add metadata
        for source, group in source_groups.items():
            total = len(group)
            safe_source = source.replace(" ", "_").replace("/", "_")
            
            for i, chunk in enumerate(group):
                chunk.metadata['chunk_id'] = f"{safe_source}_{i}"
                chunk.metadata['chunk_index'] = i
                chunk.metadata['total_chunks'] = total
                chunk.metadata['has_siblings'] = total > 1
        
        return chunks
        
    def get_embeddings(self) -> OpenAIEmbeddings:
        """Get the OpenAI embeddings instance.
        
        Returns:
            OpenAIEmbeddings instance used for semantic chunking
        """
        return self.embeddings
