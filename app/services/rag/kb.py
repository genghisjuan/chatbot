"""
Knowledge Base Service using Pinecone.

This module provides the interface for searching the knowledge base using
cloud-based vector similarity search via Pinecone.

Enhanced with:
- Explicit retrieval pipeline (retrieve → rerank → ground)
- Pluggable reranking (Jina → OpenAI → Local)
- Citation tracking via grounding contract
- Policy-based routing via variant detection
"""
import logging
from typing import List, Optional, Union
from langchain_openai import OpenAIEmbeddings
from langchain_core.documents import Document
from app.core.config import settings
from app.services.rag.vector_store import VectorStoreService
from app.services.rag.grounding import GroundedResult, build_grounded_result
from app.services.rag.reranker import RerankerService, get_reranker

logger = logging.getLogger(__name__)

# Search configuration
OVERSEARCH_MULTIPLIER = 5  # Retrieve extra results for reranking (higher = better recall)


class KnowledgeBase:
    """
    Knowledge base search service using Pinecone vector store.
    
    This class handles semantic search over uploaded PDF documents by:
    1. Converting queries to embeddings using OpenAI
    2. Searching Pinecone for similar document chunks
    3. Reranking results for improved relevance (optional)
    4. Building grounded results with citations
    
    Attributes:
        embeddings: OpenAI embedding model instance
        vector_store: Pinecone vector store service
        reranker: Reranking service (Jina/OpenAI/Local)
    """
    
    # Minimum similarity score to consider a result relevant (0.0-1.0)
    CONFIDENCE_THRESHOLD = 0.50
    
    def __init__(self) -> None:
        """
        Initialize the knowledge base service.
        
        Sets up OpenAI embeddings, Pinecone connection, and reranker.
        """
        logger.info("Initializing KnowledgeBase with Pinecone vector store")
        self.embeddings = OpenAIEmbeddings(api_key=settings.OPENAI_API_KEY)
        self.vector_store = VectorStoreService()
        
        # Initialize reranker (auto-detects best backend)
        self.reranker = get_reranker()
        
        # Simple LRU cache for search results
        self._cache = {}
        self._cache_order = []
        self._max_cache_size = 100
        logger.info(f"KnowledgeBase initialized (reranker: {self.reranker.backend})")

    async def search(
        self, 
        query: str, 
        k: int = 3,
        rerank: bool = False,
        include_grounding: bool = False
    ) -> Union[List[Document], GroundedResult]:
        """
        Search for relevant documents using Pinecone vector similarity.
        
        Args:
            query: The search query string
            k: Number of top results to return (default: 3)
            rerank: Whether to rerank results for improved relevance (default: False)
            include_grounding: Whether to return GroundedResult with citations (default: False)
            
        Returns:
            List[Document] if include_grounding=False (backward compatible)
            GroundedResult if include_grounding=True (enhanced mode)
            
        Raises:
            ValueError: If query is empty or k is invalid
            RuntimeError: If search fails
            
        Example:
            >>> kb = KnowledgeBase()
            >>> # Backward compatible usage
            >>> results = await kb.search("printer troubleshooting", k=5)
            >>> # Enhanced usage with reranking and citations
            >>> grounded = await kb.search("printer issue", k=3, rerank=True, include_grounding=True)
            >>> print(f"Grounded: {grounded.is_grounded}, Sources: {grounded.top_sources}")
        """
        # Input validation
        if not query or not query.strip():
            raise ValueError("query cannot be empty")
        if k <= 0:
            raise ValueError("k must be positive")
        
        # Build cache key (include new params)
        cache_key = f"{query}::{k}::{rerank}::{include_grounding}"
        if cache_key in self._cache:
            self._cache_order.remove(cache_key)
            self._cache_order.append(cache_key)
            logger.debug(f"Cache hit for query: {query}")
            return self._cache[cache_key]
        
        try:
            # === STAGE 1: RETRIEVE (oversample for reranking) ===
            retrieve_k = k * OVERSEARCH_MULTIPLIER if rerank else k * 2
            documents = await self._retrieve(query, retrieve_k)
            
            # === STAGE 2: RERANK (if enabled) ===
            reranked = False
            backend_used = "none"
            if rerank and documents:
                rerank_result = await self.reranker.rerank(query, documents, k * 2)  # Get extra for dedup
                documents = rerank_result.documents
                reranked = rerank_result.reranked
                backend_used = rerank_result.backend_used
                
                # === SOURCE DEDUPLICATION ===
                # Keep only the best chunk per source to ensure diverse results
                seen_sources = set()
                deduped = []
                for doc in documents:
                    source = doc.metadata.get('source', '')
                    if source not in seen_sources:
                        seen_sources.add(source)
                        deduped.append(doc)
                documents = deduped
                
                # === PHRASE-AWARE KEYWORD BOOST ===
                # Exact phrase matches get high boost, scattered words get less
                import re
                query_lower = query.lower()
                
                # Extract meaningful phrases (2-3 word combos)
                # Remove common filler words
                stopwords = {'how', 'to', 'the', 'a', 'an', 'is', 'what', 'on', 'for', 'in', 'of', 'do', 'i', 'can', 'you'}
                words = [w for w in query_lower.split() if w not in stopwords]
                
                # Build phrases to look for (e.g., "piston rings", "replace piston", etc.)
                phrases = []
                if len(words) >= 2:
                    for i in range(len(words) - 1):
                        phrases.append(f"{words[i]} {words[i+1]}")
                    if len(words) >= 3:
                        for i in range(len(words) - 2):
                            phrases.append(f"{words[i]} {words[i+1]} {words[i+2]}")
                
                for doc in documents:
                    content_lower = doc.page_content.lower()
                    rerank_score = doc.metadata.get('rerank_score', 0.5)
                    boost = 0.0
                    
                    # High boost for exact phrase matches
                    for phrase in phrases:
                        if phrase in content_lower:
                            boost += 0.25  # Strong boost per phrase match
                            # Extra if phrase is in title/header (first 300 chars)
                            if phrase in content_lower[:300]:
                                boost += 0.20  # Title match is very strong signal
                    
                    # Small boost for individual keywords (only if no phrase match)
                    if boost == 0:
                        for word in words:
                            if word in content_lower:
                                boost += 0.03  # Minimal boost for scattered words
                    
                    # Cap total boost
                    boost = min(boost, 0.6)
                    doc.metadata['boosted_score'] = rerank_score + boost
                
                # Re-sort by boosted score
                documents.sort(key=lambda d: d.metadata.get('boosted_score', 0), reverse=True)
                documents = documents[:k]
                
                logger.info(f"Reranked using {backend_used}: {len(documents)} docs (deduped+boosted)")
            else:
                # Just take top k without reranking
                documents = documents[:k]
            
            # === STAGE 3: BUILD RESULT ===
            if include_grounding:
                result = build_grounded_result(
                    documents=documents,
                    reranked=reranked,
                    backend_used=backend_used
                )
            else:
                result = documents
            
            # Update cache
            self._cache[cache_key] = result
            self._cache_order.append(cache_key)
            if len(self._cache_order) > self._max_cache_size:
                oldest = self._cache_order.pop(0)
                del self._cache[oldest]
            
            doc_count = len(documents) if isinstance(result, list) else len(result.documents)
            logger.info(f"Found {doc_count} documents for query: {query[:50]}...")
            return result
            
        except Exception as e:
            logger.error(f"Search failed for query '{query}': {e}", exc_info=True)
            raise RuntimeError(f"Knowledge base search failed: {e}") from e
    
    async def _retrieve(self, query: str, top_k: int) -> List[Document]:
        """
        Stage 1: Retrieve candidates from vector store.
        
        Args:
            query: The search query
            top_k: Number of candidates to retrieve
            
        Returns:
            List of Document objects passing confidence threshold
        """
        # Generate query embedding
        query_embedding: List[float] = await self.embeddings.aembed_query(query)
        
        # Search Pinecone
        results = self.vector_store.query(query_embedding, top_k=top_k)
        
        logger.debug(f"Retrieved {len(results)} raw results from Pinecone")
        
        if not results:
            return []
        
        # Convert to Documents, filtering by threshold
        documents: List[Document] = []
        for result in results:
            if result.score >= self.CONFIDENCE_THRESHOLD:
                doc = Document(
                    page_content=result.metadata.get('text', ''),
                    metadata={
                        'source': result.metadata.get('source', 'Unknown'),
                        'page': result.metadata.get('page', 0),
                        'score': result.score,
                        'chunk_id': result.id if hasattr(result, 'id') else ''
                    }
                )
                documents.append(doc)
        
        logger.debug(f"Filtered to {len(documents)} documents above threshold {self.CONFIDENCE_THRESHOLD}")
        return documents
    
    async def search_grounded(
        self,
        query: str,
        k: int = 3,
        rerank: bool = True
    ) -> GroundedResult:
        """
        Convenience method for grounded search with reranking.
        
        This is the recommended method for production use as it provides
        full citation tracking and reranking by default.
        
        Args:
            query: The search query
            k: Number of results
            rerank: Whether to rerank (default: True)
            
        Returns:
            GroundedResult with documents and citations
        """
        result = await self.search(query, k, rerank=rerank, include_grounding=True)
        return result


# Singleton instance for backward compatibility
_kb_instance: Optional[KnowledgeBase] = None

def get_knowledge_base() -> KnowledgeBase:
    """Get singleton KnowledgeBase instance."""
    global _kb_instance
    if _kb_instance is None:
        _kb_instance = KnowledgeBase()
    return _kb_instance
