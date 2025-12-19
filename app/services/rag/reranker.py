"""
Reranker Service with Solopreneur-Friendly Fallback Chain.

Priority order:
1. Jina Reranker (free tier: 1M tokens/month)
2. OpenAI GPT-4o-mini (uses existing API key)
3. Local cross-encoder (offline, free forever)
4. Disabled (returns documents unchanged)

All options are optional - system gracefully degrades.
"""
import logging
import os
from typing import List, Optional, Tuple
from dataclasses import dataclass

try:
    from langchain_core.documents import Document
except ImportError:
    Document = None  # Type hint only

logger = logging.getLogger(__name__)


@dataclass
class RerankResult:
    """Result of reranking operation."""
    documents: List["Document"]
    backend_used: str
    reranked: bool


class RerankerService:
    """
    Rerank retrieved documents for improved relevance.
    
    Automatically detects available backends and uses the best one:
    1. Jina (if JINA_API_KEY set)
    2. OpenAI (if OPENAI_API_KEY set) 
    3. Local cross-encoder (if sentence-transformers installed)
    4. Disabled (passthrough)
    
    Attributes:
        backend: Currently active backend name
        enabled: Whether reranking is enabled
    """
    
    # Jina reranker endpoint
    JINA_RERANK_URL = "https://api.jina.ai/v1/rerank"
    
    def __init__(self, force_backend: Optional[str] = None) -> None:
        """
        Initialize reranker service.
        
        Args:
            force_backend: Force specific backend ("jina", "openai", "local", "disabled")
        """
        self._jina_api_key: Optional[str] = None
        self._openai_api_key: Optional[str] = None
        self._local_model = None
        
        if force_backend:
            self.backend = force_backend
        else:
            self.backend = self._detect_backend()
        
        self.enabled = self.backend != "disabled"
        
        if self.enabled:
            logger.info(f"Reranker initialized with backend: {self.backend}")
        else:
            logger.warning("Reranker disabled - no backend available")
    
    def _detect_backend(self) -> str:
        """Detect best available reranking backend."""
        # Try loading config (may not be available in all contexts)
        try:
            from app.core.config import settings
            self._jina_api_key = getattr(settings, 'JINA_API_KEY', '') or ''
            self._openai_api_key = getattr(settings, 'OPENAI_API_KEY', '') or ''
        except ImportError:
            # Fallback to environment variables
            self._jina_api_key = os.environ.get('JINA_API_KEY', '')
            self._openai_api_key = os.environ.get('OPENAI_API_KEY', '')
        
        # Priority 1: Jina (free tier)
        if self._jina_api_key and self._jina_api_key.strip():
            return "jina"
        
        # Priority 2: OpenAI (existing key)
        if self._openai_api_key and self._openai_api_key.strip():
            return "openai"
        
        # Priority 3: Local cross-encoder
        try:
            from sentence_transformers import CrossEncoder
            return "local"
        except ImportError:
            pass
        
        # No backend available
        return "disabled"
    
    async def rerank(
        self, 
        query: str, 
        documents: List["Document"], 
        top_k: int = 5
    ) -> RerankResult:
        """
        Rerank documents using best available method.
        
        Args:
            query: The search query
            documents: List of documents to rerank
            top_k: Number of top documents to return
            
        Returns:
            RerankResult with reranked documents and metadata
        """
        if not documents:
            return RerankResult(documents=[], backend_used="none", reranked=False)
        
        if not self.enabled or self.backend == "disabled":
            return RerankResult(
                documents=documents[:top_k], 
                backend_used="disabled", 
                reranked=False
            )
        
        try:
            if self.backend == "jina":
                reranked = await self._rerank_jina(query, documents, top_k)
            elif self.backend == "openai":
                reranked = await self._rerank_openai(query, documents, top_k)
            elif self.backend == "local":
                reranked = self._rerank_local(query, documents, top_k)
            else:
                reranked = documents[:top_k]
            
            return RerankResult(
                documents=reranked,
                backend_used=self.backend,
                reranked=True
            )
        except Exception as e:
            logger.error(f"Reranking failed with {self.backend}: {e}")
            # Fallback to no reranking
            return RerankResult(
                documents=documents[:top_k],
                backend_used="fallback",
                reranked=False
            )
    
    async def _rerank_jina(
        self, 
        query: str, 
        documents: List["Document"], 
        top_k: int
    ) -> List["Document"]:
        """Rerank using Jina API (free tier: 1M tokens/month)."""
        import aiohttp
        
        # Prepare documents for Jina
        doc_texts = [doc.page_content for doc in documents]
        
        headers = {
            "Authorization": f"Bearer {self._jina_api_key}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "model": "jina-reranker-v2-base-multilingual",
            "query": query,
            "documents": doc_texts,
            "top_n": min(top_k, len(documents))
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.post(
                self.JINA_RERANK_URL,
                headers=headers,
                json=payload,
                timeout=aiohttp.ClientTimeout(total=30)
            ) as response:
                response.raise_for_status()
                result = await response.json()
        
        # Reorder documents based on Jina scores
        reranked = []
        for item in result.get("results", []):
            idx = item.get("index", 0)
            if idx < len(documents):
                doc = documents[idx]
                # Add rerank score to metadata
                doc.metadata["rerank_score"] = item.get("relevance_score", 0)
                reranked.append(doc)
        
        logger.debug(f"Jina reranked {len(reranked)} documents")
        return reranked
    
    async def _rerank_openai(
        self, 
        query: str, 
        documents: List["Document"], 
        top_k: int
    ) -> List["Document"]:
        """Rerank using OpenAI GPT-4o-mini (uses existing API key)."""
        from openai import AsyncOpenAI
        
        client = AsyncOpenAI(api_key=self._openai_api_key)
        
        # Build prompt for relevance scoring
        doc_texts = []
        for i, doc in enumerate(documents):
            preview = doc.page_content[:500] if len(doc.page_content) > 500 else doc.page_content
            doc_texts.append(f"[{i}] {preview}")
        
        prompt = f"""Score each document's relevance to the query on a scale of 1-10.
Query: {query}

Documents:
{chr(10).join(doc_texts)}

Return ONLY a JSON array of objects with "index" and "score" keys, sorted by score descending.
Example: [{{"index": 2, "score": 9}}, {{"index": 0, "score": 7}}]"""

        response = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
            max_tokens=500
        )
        
        # Parse response
        import json
        try:
            content = response.choices[0].message.content.strip()
            # Handle markdown code blocks
            if content.startswith("```"):
                content = content.split("```")[1]
                if content.startswith("json"):
                    content = content[4:]
            scores = json.loads(content)
        except (json.JSONDecodeError, IndexError):
            logger.warning("Failed to parse OpenAI rerank response, using original order")
            return documents[:top_k]
        
        # Reorder documents
        reranked = []
        for item in scores[:top_k]:
            idx = item.get("index", 0)
            if idx < len(documents):
                doc = documents[idx]
                doc.metadata["rerank_score"] = item.get("score", 0) / 10.0
                reranked.append(doc)
        
        logger.debug(f"OpenAI reranked {len(reranked)} documents")
        return reranked
    
    def _rerank_local(
        self, 
        query: str, 
        documents: List["Document"], 
        top_k: int
    ) -> List["Document"]:
        """Rerank using local cross-encoder model."""
        from sentence_transformers import CrossEncoder
        
        # Lazy load model
        if self._local_model is None:
            logger.info("Loading local cross-encoder model (first use)...")
            self._local_model = CrossEncoder('cross-encoder/ms-marco-MiniLM-L-6-v2')
        
        # Score all documents
        pairs = [(query, doc.page_content) for doc in documents]
        scores = self._local_model.predict(pairs)
        
        # Sort by score
        scored_docs = list(zip(documents, scores))
        scored_docs.sort(key=lambda x: x[1], reverse=True)
        
        # Return top_k with scores in metadata
        reranked = []
        for doc, score in scored_docs[:top_k]:
            doc.metadata["rerank_score"] = float(score)
            reranked.append(doc)
        
        logger.debug(f"Local reranked {len(reranked)} documents")
        return reranked


# Singleton instance
_reranker: Optional[RerankerService] = None

def get_reranker() -> RerankerService:
    """Get singleton reranker instance."""
    global _reranker
    if _reranker is None:
        _reranker = RerankerService()
    return _reranker
