"""
Knowledge Base Service using Pinecone.

This module provides the interface for searching the knowledge base using
cloud-based vector similarity search via Pinecone.
"""
import logging
from typing import List
from langchain_openai import OpenAIEmbeddings
from langchain_core.documents import Document
from app.core.config import settings
from app.services.rag.vector_store import VectorStoreService

logger = logging.getLogger(__name__)

# Search configuration
OVERSEARCH_MULTIPLIER = 2  # Retrieve extra results to filter by confidence threshold


class KnowledgeBase:
    """
    Knowledge base search service using Pinecone vector store.
    
    This class handles semantic search over uploaded PDF documents by:
    1. Converting queries to embeddings using OpenAI
    2. Searching Pinecone for similar document chunks
    3. Returning ranked results with metadata
    
    Attributes:
        embeddings: OpenAI embedding model instance
        vector_store: Pinecone vector store service
    """
    
    # Minimum similarity score to consider a result relevant (0.0-1.0)
    CONFIDENCE_THRESHOLD = 0.50
    
    def __init__(self) -> None:
        """
        Initialize the knowledge base service.
        
        Sets up OpenAI embeddings and Pinecone connection.
        """
        logger.info("Initializing KnowledgeBase with Pinecone vector store")
        self.embeddings = OpenAIEmbeddings(api_key=settings.OPENAI_API_KEY)
        self.vector_store = VectorStoreService()
        
        # Simple LRU cache for search results
        self._cache = {}
        self._cache_order = []
        self._max_cache_size = 100
        logger.info("KnowledgeBase initialized successfully")

    async def search(self, query: str, k: int = 3) -> List[Document]:
        """
        Search for relevant documents using Pinecone vector similarity.
        
        Args:
            query: The search query string
            k: Number of top results to return (default: 3)
            
        Returns:
            List of Document objects with page_content and metadata.
            Metadata includes: source (filename), page (page number), score (relevance)
            
        Raises:
            ValueError: If query is empty or k is invalid
            RuntimeError: If search fails
            
        Example:
            >>> kb = KnowledgeBase()
            >>> results = await kb.search("printer troubleshooting", k=5)
            >>> for doc in results:
            ...     print(f"{doc.metadata['source']}: {doc.page_content[:100]}")
        """
        # Input validation
        if not query or not query.strip():
            raise ValueError("query cannot be empty")
        if k <= 0:
            raise ValueError("k must be positive")
            
        # Check cache
        cache_key = f"{query}::{k}"
        if cache_key in self._cache:
            # Move to end (recently used) - LRU cache
            self._cache_order.remove(cache_key)
            self._cache_order.append(cache_key)
            logger.debug(f"Cache hit for query: {query}")
            return self._cache[cache_key]
        
        try:
            # Generate query embedding using OpenAI (Async)
            query_embedding: List[float] = await self.embeddings.aembed_query(query)
            
            # Search Pinecone for similar vectors (get more to filter by threshold)
            results = self.vector_store.query(query_embedding, top_k=k * OVERSEARCH_MULTIPLIER)
            
            # Log search
            logger.info(f"KB Search: '{query}'")
            if not results:
                logger.info("No results from vector store")
            
            # Convert Pinecone results to Document objects
            # Filter by confidence threshold to ensure quality
            documents: List[Document] = []
            for result in results:
                logger.debug(f"Match - Score: {result.score:.4f} | Source: {result.metadata.get('source', 'Unknown')}")
                
                # Only include results above confidence threshold
                if result.score >= self.CONFIDENCE_THRESHOLD:
                    doc = Document(
                        page_content=result.metadata.get('text', ''),
                        metadata={
                            'source': result.metadata.get('source', 'Unknown'),
                            'page': result.metadata.get('page', 0),
                            'score': result.score
                        }
                    )
                    documents.append(doc)
                    
                    # Stop once we have k high-quality results
                    if len(documents) >= k:
                        break
            
            # Update cache (LRU eviction)
            self._cache[cache_key] = documents
            self._cache_order.append(cache_key)
            if len(self._cache_order) > self._max_cache_size:
                oldest = self._cache_order.pop(0)
                del self._cache[oldest]
            
            logger.info(f"Found {len(documents)} relevant documents (threshold: {self.CONFIDENCE_THRESHOLD}) for query: {query[:50]}...")
            return documents
            
        except Exception as e:
            logger.error(f"Pinecone search failed for query '{query}': {e}", exc_info=True)
            raise RuntimeError(f"Knowledge base search failed: {e}") from e
