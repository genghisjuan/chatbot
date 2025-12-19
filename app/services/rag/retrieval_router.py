"""
Retrieval Router for Policy-Based Query Handling.

Connects variant detection to retrieval policy decisions,
enabling smart query routing based on result characteristics.
"""
import logging
from enum import Enum
from typing import List, Optional
from dataclasses import dataclass

try:
    from langchain_core.documents import Document
except ImportError:
    Document = None

from app.services.rag.variant_detector import detect_variants, VariantInfo

logger = logging.getLogger(__name__)


class RetrievalPolicy(Enum):
    """
    Retrieval policies that control search behavior.
    
    Each policy adjusts:
    - Number of results (k)
    - Confidence threshold
    - Whether to ask for clarification
    """
    STANDARD = "standard"           # Default: balanced retrieval
    PRECISE = "precise"             # Factual query: small k, high threshold
    BROAD = "broad"                 # Synthesis query: larger k, lower threshold
    NEEDS_CLARIFICATION = "clarify" # Multiple variants detected, ask user
    FALLBACK = "fallback"           # No good results, use fallback behavior


@dataclass
class RoutingDecision:
    """
    Result of query routing decision.
    
    Attributes:
        policy: The retrieval policy to apply
        reason: Human-readable explanation
        variant_info: Variant detection results if applicable
        suggested_k: Recommended number of results
        suggested_threshold: Recommended confidence threshold
    """
    policy: RetrievalPolicy
    reason: str
    variant_info: Optional[VariantInfo] = None
    suggested_k: int = 3
    suggested_threshold: float = 0.50
    
    @property
    def needs_clarification(self) -> bool:
        """Check if user clarification is needed."""
        return self.policy == RetrievalPolicy.NEEDS_CLARIFICATION
    
    @property
    def clarification_options(self) -> List[str]:
        """Get options to present to user for clarification."""
        if self.variant_info and self.variant_info.get("has_variants"):
            return self.variant_info.get("options", [])
        return []


class RetrievalRouter:
    """
    Route queries to appropriate retrieval strategy.
    
    Analyzes preliminary results and query characteristics to determine
    the optimal retrieval policy.
    
    Usage:
        router = RetrievalRouter()
        decision = router.route(query, preliminary_results)
        if decision.needs_clarification:
            # Ask user to choose from decision.clarification_options
        else:
            # Proceed with decision.suggested_k and decision.suggested_threshold
    """
    
    # Keywords indicating factual/lookup queries (need precise results)
    FACTUAL_KEYWORDS = [
        "how to", "what is", "where is", "steps to", "procedure for",
        "part number", "torque spec", "specification"
    ]
    
    # Keywords indicating synthesis queries (need broader context)
    SYNTHESIS_KEYWORDS = [
        "explain", "compare", "difference between", "overview",
        "summary", "when should", "why does"
    ]
    
    def __init__(self, enable_variant_detection: bool = True):
        """
        Initialize router.
        
        Args:
            enable_variant_detection: Whether to check for variants
        """
        self.enable_variant_detection = enable_variant_detection
    
    def route(
        self, 
        query: str, 
        preliminary_results: List["Document"]
    ) -> RoutingDecision:
        """
        Determine retrieval policy based on query and preliminary results.
        
        Args:
            query: The user's search query
            preliminary_results: Initial retrieval results (oversample)
            
        Returns:
            RoutingDecision with policy and parameters
        """
        query_lower = query.lower()
        
        # Check for variants first (if enabled and results exist)
        if self.enable_variant_detection and preliminary_results:
            variant_info = detect_variants(preliminary_results)
            
            if variant_info.get("has_variants", False):
                logger.info(
                    f"Variants detected for '{query[:30]}...': "
                    f"type={variant_info.get('variant_type')}, "
                    f"options={variant_info.get('options')}"
                )
                return RoutingDecision(
                    policy=RetrievalPolicy.NEEDS_CLARIFICATION,
                    reason=f"Multiple {variant_info.get('variant_type', 'variant')} options found",
                    variant_info=variant_info,
                    suggested_k=3,
                    suggested_threshold=0.50
                )
        
        # Check query type for factual vs synthesis
        if self._is_factual_query(query_lower):
            return RoutingDecision(
                policy=RetrievalPolicy.PRECISE,
                reason="Factual lookup query detected",
                suggested_k=2,
                suggested_threshold=0.60
            )
        
        if self._is_synthesis_query(query_lower):
            return RoutingDecision(
                policy=RetrievalPolicy.BROAD,
                reason="Synthesis/overview query detected",
                suggested_k=5,
                suggested_threshold=0.40
            )
        
        # Check result quality
        if not preliminary_results:
            return RoutingDecision(
                policy=RetrievalPolicy.FALLBACK,
                reason="No results found",
                suggested_k=5,
                suggested_threshold=0.30
            )
        
        # Default: standard retrieval
        return RoutingDecision(
            policy=RetrievalPolicy.STANDARD,
            reason="Standard query",
            suggested_k=3,
            suggested_threshold=0.50
        )
    
    def _is_factual_query(self, query: str) -> bool:
        """Check if query is a factual/lookup query."""
        return any(kw in query for kw in self.FACTUAL_KEYWORDS)
    
    def _is_synthesis_query(self, query: str) -> bool:
        """Check if query requires synthesis/broad context."""
        return any(kw in query for kw in self.SYNTHESIS_KEYWORDS)


# Singleton instance
_router: Optional[RetrievalRouter] = None

def get_router() -> RetrievalRouter:
    """Get singleton router instance."""
    global _router
    if _router is None:
        _router = RetrievalRouter()
    return _router
