"""
Pinecone Vector Store Service.

This module provides the interface for managing vector embeddings in Pinecone,
including index creation, vector upsert, similarity search, and index management.

Required Configuration:
- PINECONE_API_KEY: Pinecone API key (set to "changeme" to disable)
- PINECONE_INDEX_NAME: Name of the Pinecone index
- AWS_REGION: AWS region for serverless index (e.g., 'us-east-1')
"""
import logging
import time
from typing import List, Dict, Any, Optional

from pinecone import Pinecone, ServerlessSpec


from app.core.config import settings

logger = logging.getLogger(__name__)


class VectorStoreService:
    """
    Service for managing vector embeddings in Pinecone cloud database.
    
    This service provides methods to:
    - Create and manage Pinecone indexes
    - Upsert (insert/update) vector embeddings with automatic batching
    - Perform similarity search queries
    - Get index statistics
    - Delete vectors
    
    The service gracefully handles missing API credentials by setting
    pc and index to None, allowing the application to run without Pinecone.
    
    Attributes:
        pc: Pinecone client instance (None if not configured)
        index: Active Pinecone index (None if not configured)
    """
    
    # OpenAI text-embedding-ada-002 produces 1536-dimensional vectors
    EMBEDDING_DIMENSION = 1536
    # Default batch size for upsert operations (Pinecone serverless limit)
    DEFAULT_BATCH_SIZE = 100
    # Magic value indicating Pinecone is disabled
    PINECONE_DISABLED_VALUE = "changeme"
    
    def __init__(self) -> None:
        """
        Initialize Pinecone vector store service.
        
        Connects to Pinecone and initializes/connects to the index if API key is configured.
        If API key is "changeme", service will be disabled but won't crash.
        """
        self.pc: Optional[Pinecone] = None
        self.index: Optional[Any] = None
        
        if settings.PINECONE_API_KEY and settings.PINECONE_API_KEY != self.PINECONE_DISABLED_VALUE:
            try:
                self.pc = Pinecone(api_key=settings.PINECONE_API_KEY)
                self._init_index()
            except Exception as e:
                logger.error(f"Failed to initialize Pinecone service: {e}", exc_info=True)
                self.pc = None
                self.index = None
    
    def _init_index(self) -> None:
        """
        Initialize or connect to existing Pinecone index.
        
        Creates a new serverless index if it doesn't exist, otherwise connects
        to the existing index. Index is configured with cosine similarity metric
        for semantic search.
        
        Raises:
            Exception: If index creation or connection fails
        """
        if not self.pc:
            raise ValueError("Pinecone client not initialized")
            
        try:
            # Check if index exists
            existing_indexes = self.pc.list_indexes()
            index_names = [idx.name for idx in existing_indexes]
            
            if settings.PINECONE_INDEX_NAME not in index_names:
                logger.info(f"Creating new Pinecone index: {settings.PINECONE_INDEX_NAME}")
                # Create new serverless index
                self.pc.create_index(
                    name=settings.PINECONE_INDEX_NAME,
                    dimension=self.EMBEDDING_DIMENSION,
                    metric='cosine',  # Cosine similarity for text embeddings
                    spec=ServerlessSpec(
                        cloud=getattr(settings, 'PINECONE_CLOUD', 'aws'),
                        region=settings.AWS_REGION
                    )
                )
                # Wait for index to be ready with polling
                logger.info("Waiting for index to be ready...")
                max_wait_time = 60  # Maximum wait time in seconds
                elapsed = 0
                while elapsed < max_wait_time:
                    try:
                        index_description = self.pc.describe_index(settings.PINECONE_INDEX_NAME)
                        if index_description.status.ready:
                            logger.info("Index is ready")
                            break
                    except Exception:
                        pass
                    time.sleep(1)
                    elapsed += 1
                else:
                    logger.warning(f"Index creation timed out after {max_wait_time}s, attempting to connect anyway")
            
            self.index = self.pc.Index(settings.PINECONE_INDEX_NAME)
            logger.info(f"Successfully connected to Pinecone index: {settings.PINECONE_INDEX_NAME}")
            
            # Verify index dimension matches application expectation
            try:
                index_desc = self.pc.describe_index(settings.PINECONE_INDEX_NAME)
                if hasattr(index_desc, 'dimension') and int(index_desc.dimension) != self.EMBEDDING_DIMENSION:
                    logger.warning(
                        f"Index dimension mismatch: Index has {index_desc.dimension}, "
                        f"app expects {self.EMBEDDING_DIMENSION}. Queries may fail or produce poor results."
                    )
            except Exception as e:
                logger.warning(f"Could not verify index dimension: {e}")
            
            
        except Exception as e:
            logger.error(f"Error initializing Pinecone index: {e}", exc_info=True)
            raise
    
    def upsert_vectors(
        self, 
        vectors: List[Dict[str, Any]], 
        batch_size: Optional[int] = None,
        namespace: str = ""
    ) -> bool:
        """
        Insert or update vectors in Pinecone with automatic batching.
        
        Args:
            vectors: List of dicts with structure:
                {
                    'id': str,  # Unique vector ID
                    'values': List[float],  # 1536-dimensional embedding
                    'metadata': Dict  # Optional metadata (source, page, text, etc.)
                }
            batch_size: Maximum number of vectors per batch (default: 100)
            namespace: Optional namespace for organizing vectors (default: "")
            
        Returns:
            True if successful, False otherwise
            
        Example:
            >>> service = VectorStoreService()
            >>> vectors = [{
            ...     'id': 'doc1_chunk0',
            ...     'values': [0.1, 0.2, ...],  # 1536 dimensions
            ...     'metadata': {'source': 'manual.pdf', 'page': 1}
            ... }]
            >>> success = service.upsert_vectors(vectors)
        """
        if batch_size is None:
            batch_size = self.DEFAULT_BATCH_SIZE
            
        if not self.index:
            logger.warning("Pinecone index not configured")
            return False
        
        if not vectors:
            logger.warning("Cannot upsert empty vector list")
            return False
        
        # Validate vector structure
        for i, vec in enumerate(vectors):
            if 'id' not in vec or 'values' not in vec:
                logger.error(f"Vector at index {i} missing required 'id' or 'values' field")
                return False
            if not isinstance(vec['values'], (list, tuple)):
                logger.error(f"Vector at index {i} has invalid 'values' type: {type(vec['values'])}")
                return False
            if len(vec['values']) != self.EMBEDDING_DIMENSION:
                logger.error(
                    f"Vector at index {i} has wrong dimension: expected {self.EMBEDDING_DIMENSION}, got {len(vec['values'])}"
                )
                return False
        
        try:
            # Process in batches to respect API limits
            total_batches = (len(vectors) + batch_size - 1) // batch_size
            successful_batches = 0
            
            for batch_num, i in enumerate(range(0, len(vectors), batch_size), 1):
                batch = vectors[i:i + batch_size]
                try:
                    logger.debug(f"Upserting batch {batch_num}/{total_batches} ({len(batch)} vectors)")
                    self.index.upsert(vectors=batch, namespace=namespace)
                    successful_batches += 1
                except Exception as e:
                    logger.error(f"Failed to upsert batch {batch_num}/{total_batches}: {e}", exc_info=True)
                    # Continue with remaining batches
            
            if successful_batches == total_batches:
                logger.info(f"Successfully upserted {len(vectors)} vectors in {total_batches} batch(es)")
                return True
            else:
                logger.warning(
                    f"Partial upsert: {successful_batches}/{total_batches} batches succeeded"
                )
                return False
        except Exception as e:
            logger.error(f"Error upserting vectors: {e}", exc_info=True)
            return False
    
    def query(
        self,
        vector: List[float],
        top_k: int = 5,
        filter: Optional[Dict] = None,
        namespace: str = ""
    ) -> List[Any]:
        """
        Query similar vectors from Pinecone using cosine similarity.
        
        Args:
            vector: Query embedding (1536-dimensional list of floats)
            top_k: Number of most similar results to return (default: 5)
            filter: Optional metadata filter dict (e.g., {'source': 'manual.pdf'})
            namespace: Optional namespace to query (default: "")
            
        Returns:
            List of match objects with attributes:
            - id: Vector ID
            - score: Similarity score (0-1, higher is more similar)
            - metadata: Associated metadata dict
            
        Example:
            >>> embedding = embeddings_model.embed_query("printer issue")
            >>> results = service.query(embedding, top_k=3)
            >>> for match in results:
            ...     print(f"Score: {match.score}, Source: {match.metadata['source']}")
        """
        if not self.index:
            logger.warning("Pinecone index not configured")
            return []
        
        # Validate input
        if vector is None or len(vector) == 0:
            logger.error("Cannot query with None or empty vector")
            return []
        
        if not isinstance(vector, (list, tuple)):
            logger.error(f"Vector must be a list or tuple, got {type(vector)}")
            return False
        
        if len(vector) != self.EMBEDDING_DIMENSION:
            logger.warning(
                f"Vector dimension mismatch: expected {self.EMBEDDING_DIMENSION}, got {len(vector)}"
            )
        
        if top_k <= 0:
            logger.error(f"top_k must be positive, got {top_k}")
            return []
        
        if top_k > 10000:
            logger.warning(f"top_k={top_k} exceeds typical Pinecone limit of 10,000")
        
        try:
            results = self.index.query(
                vector=vector,
                top_k=top_k,
                include_metadata=True,
                filter=filter,
                namespace=namespace
            )
            logger.debug(f"Query returned {len(results.matches)} matches")
            return results.matches
        except Exception as e:
            logger.error(f"Error querying vectors: {e}", exc_info=True)
            return []
    
    def delete_vectors(
        self, 
        ids: List[str], 
        namespace: str = "",
        batch_size: int = 1000
    ) -> bool:
        """
        Delete specific vectors by ID.
        
        Args:
            ids: List of vector IDs to delete
            namespace: Optional namespace (default: "")
            batch_size: Maximum number of vectors to delete per batch (default: 1000)
        
        Returns:
            True if successful, False otherwise
        """
        if not self.index:
            logger.warning("Pinecone index not configured")
            return False
        
        if not ids:
            logger.warning("Cannot delete empty ID list")
            return False
        
        try:
            # unique IDs to prevent duplicate deletion operations in same batch if user provided duplicates
            unique_ids = list(set(ids))
            total_batches = (len(unique_ids) + batch_size - 1) // batch_size
            
            for batch_num, i in enumerate(range(0, len(unique_ids), batch_size), 1):
                batch = unique_ids[i:i + batch_size]
                logger.debug(f"Deleting batch {batch_num}/{total_batches} ({len(batch)} vectors)")
                self.index.delete(ids=batch, namespace=namespace)
                
            logger.info(f"Successfully deleted {len(unique_ids)} vectors from namespace '{namespace}'")
            return True
        except Exception as e:
            logger.error(f"Error deleting vectors: {e}", exc_info=True)
            return False
    
    def delete_all(self, namespace: str = "") -> bool:
        """
        Delete all vectors from the index or a specific namespace.
        
        NOTE: If namespace is provided, only that namespace is cleared. 
        If no namespace is provided, ALL vectors in the index (across all namespaces) 
        may be deleted depending on Pinecone API behavior (use with extreme caution).
        Current Pinecone 'delete_all' flag usually requires a namespace if configured,
        or wipes everything if at index root.
        
        WARNING: This is a destructive operation that cannot be undone.
        Use with caution in production.
        
        Args:
            namespace: Optional namespace to delete from (default: "" deletes all)
        
        Returns:
            True if successful, False otherwise
        """
        if not self.index:
            logger.warning("Pinecone index not configured")
            return False
        
        try:
            if namespace:
                logger.warning(f"Deleting all vectors from namespace '{namespace}' - this cannot be undone!")
                self.index.delete(delete_all=True, namespace=namespace)
                logger.info(f"Successfully deleted all vectors from namespace '{namespace}'")
            else:
                logger.warning("Deleting all vectors from index - this cannot be undone!")
                self.index.delete(delete_all=True)
                logger.info("Successfully deleted all vectors")
            return True
        except Exception as e:
            logger.error(f"Error deleting vectors: {e}", exc_info=True)
            return False
    
    def get_stats(self) -> Dict[str, Any]:
        """
        Get statistics about the Pinecone index.
        
        Returns:
            Dictionary containing:
            - dimension: Vector dimensionality (int)
            - index_fullness: Percentage of index capacity used (float)
            - total_vector_count: Total number of vectors stored (int)
            - namespaces: Dict of namespace-specific stats
            
        Example:
            >>> stats = service.get_stats()
            >>> print(f"Index has {stats.get('total_vector_count', 0)} vectors")
        """
        if not self.index:
            logger.warning("Pinecone index not configured")
            return {}
        
        try:
            stats = self.index.describe_index_stats()
            logger.debug(f"Index stats: {stats.get('total_vector_count', 0)} total vectors")
            return stats
        except Exception as e:
            logger.error(f"Error getting index stats: {e}", exc_info=True)
            return {}
    
    def is_configured(self) -> bool:
        """
        Check if Pinecone service is properly configured and ready to use.
        
        Returns:
            True if the service has a valid connection and index, False otherwise
        """
        return self.index is not None
    
    def index_exists(self, index_name: Optional[str] = None) -> bool:
        """
        Check if an index exists in Pinecone.
        
        Args:
            index_name: Name of index to check (default: configured index)
        
        Returns:
            True if index exists, False otherwise
        """
        if not self.pc:
            logger.warning("Pinecone client not initialized")
            return False
        
        target_name = index_name or settings.PINECONE_INDEX_NAME
        
        try:
            existing_indexes = self.pc.list_indexes()
            return target_name in [idx.name for idx in existing_indexes]
        except Exception as e:
            logger.error(f"Error checking index existence: {e}", exc_info=True)
            return False
