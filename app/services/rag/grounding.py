"""
Grounding Contract for RAG Results.

Enforces evidence tracking on all retrieved results to prevent hallucination.
Every answer must link back to source chunks with confidence metrics.
"""
import logging
from typing import List, Optional
from dataclasses import dataclass, field

try:
    from langchain_core.documents import Document
except ImportError:
    Document = None  # Type hint only

logger = logging.getLogger(__name__)


@dataclass
class Citation:
    """
    A traceable reference to source material.
    
    Attributes:
        source: Filename or document identifier
        page: Page number (1-indexed, 0 if unknown)
        chunk_id: Vector ID for traceability
        text_snippet: First N chars for display/verification
        score: Relevance score from retrieval (0-1)
    """
    source: str
    page: int = 0
    chunk_id: str = ""
    text_snippet: str = ""
    score: float = 0.0
    
    def to_markdown(self) -> str:
        """Format citation as markdown reference."""
        if self.page > 0:
            return f"[{self.source}, p.{self.page}]"
        return f"[{self.source}]"
    
    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "source": self.source,
            "page": self.page,
            "chunk_id": self.chunk_id,
            "text_snippet": self.text_snippet,
            "score": self.score
        }


@dataclass
class GroundedResult:
    """
    RAG result with mandatory evidence trail.
    
    This ensures every retrieval result can be traced back to its source,
    enabling hallucination detection and trust verification.
    
    Attributes:
        documents: Retrieved document chunks
        citations: Ordered list of citations matching documents
        coverage_score: Percentage of results with valid sources (0-1)
        reranked: Whether results were reranked
        backend_used: Reranking backend if used
    """
    documents: List["Document"] = field(default_factory=list)
    citations: List[Citation] = field(default_factory=list)
    coverage_score: float = 0.0
    reranked: bool = False
    backend_used: str = "none"
    
    def __post_init__(self):
        """Calculate coverage score if not provided."""
        if self.documents and not self.coverage_score:
            valid_sources = sum(
                1 for doc in self.documents 
                if doc.metadata.get('source') and doc.metadata.get('source') != 'Unknown'
            )
            self.coverage_score = valid_sources / len(self.documents)
    
    @property
    def is_grounded(self) -> bool:
        """Check if results meet minimum grounding threshold."""
        return self.coverage_score >= 0.5  # At least 50% must have valid sources
    
    @property
    def top_sources(self) -> List[str]:
        """Get unique source filenames from citations."""
        seen = set()
        sources = []
        for citation in self.citations:
            if citation.source not in seen:
                seen.add(citation.source)
                sources.append(citation.source)
        return sources
    
    def get_context_string(self, max_chars: int = 4000) -> str:
        """
        Build context string from documents for LLM consumption.
        
        Args:
            max_chars: Maximum total characters to include
            
        Returns:
            Formatted context string with source annotations
        """
        if not self.documents:
            return ""
        
        chunks = []
        total_chars = 0
        
        for doc, citation in zip(self.documents, self.citations):
            content = doc.page_content
            header = f"[Source: {citation.source}"
            if citation.page > 0:
                header += f", Page {citation.page}"
            header += "]\n"
            
            chunk = header + content
            
            if total_chars + len(chunk) > max_chars:
                # Truncate this chunk to fit
                remaining = max_chars - total_chars - len(header)
                if remaining > 100:
                    chunk = header + content[:remaining] + "..."
                    chunks.append(chunk)
                break
            
            chunks.append(chunk)
            total_chars += len(chunk)
        
        return "\n\n---\n\n".join(chunks)
    
    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "documents": [
                {"content": doc.page_content, "metadata": doc.metadata}
                for doc in self.documents
            ],
            "citations": [c.to_dict() for c in self.citations],
            "coverage_score": self.coverage_score,
            "reranked": self.reranked,
            "backend_used": self.backend_used,
            "is_grounded": self.is_grounded
        }


def build_grounded_result(
    documents: List["Document"],
    reranked: bool = False,
    backend_used: str = "none"
) -> GroundedResult:
    """
    Build a GroundedResult from raw documents.
    
    Extracts citations from document metadata and calculates coverage.
    
    Args:
        documents: List of retrieved documents
        reranked: Whether documents were reranked
        backend_used: Reranking backend name
        
    Returns:
        GroundedResult with citations
    """
    citations = []
    
    for i, doc in enumerate(documents):
        metadata = doc.metadata or {}
        
        citation = Citation(
            source=metadata.get('source', 'Unknown'),
            page=metadata.get('page', 0),
            chunk_id=metadata.get('chunk_id', f"chunk_{i}"),
            text_snippet=doc.page_content[:100] if doc.page_content else "",
            score=metadata.get('score', metadata.get('rerank_score', 0.0))
        )
        citations.append(citation)
    
    result = GroundedResult(
        documents=documents,
        citations=citations,
        reranked=reranked,
        backend_used=backend_used
    )
    
    logger.debug(
        f"Built grounded result: {len(documents)} docs, "
        f"coverage={result.coverage_score:.1%}, grounded={result.is_grounded}"
    )
    
    return result
