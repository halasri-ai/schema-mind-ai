# Semantic similarity module using sentence-transformers
# Uses local sentence-transformer models for all processing
# No cloud dependencies required
# HuggingFace remote downloads disabled - using local models only

import numpy as np
from typing import Dict, List, Tuple, Optional
import logging
import json
import os
import threading

logger = logging.getLogger(__name__)

# Disable HuggingFace remote model downloads - use local models only
os.environ['HF_HUB_OFFLINE'] = '1'


class SemanticSimilarityEngine:
    """
    Compute semantic similarity using HuggingFace embeddings (sentence-transformers).
    All processing is local - no cloud calls needed.
    """
    
    def __init__(self, model: str = "minilm"):
        """
        Initialize the semantic engine with local sentence-transformer models.
        Models must be cached locally - no remote downloads.
        
        Args:
            model: "minilm" (default, fast & accurate) or other sentence-transformer models
        """
        self.model_type = model
        self.embeddings_cache = {}
        self.transformer = None
        self.model_loaded = False
        logger.info("✓ Semantic engine initialized (local models only mode)")
        logger.info(f"  - Model type: {model}")
        logger.info(f"  - HuggingFace remote disabled (offline mode)")
        logger.info(f"  - Embeddings will be cached in memory for performance")

    
    def get_embedding(self, text: str) -> Optional[np.ndarray]:
        """
        Get local sentence-transformer embedding for a text string.
        Results are cached for efficiency.
        Model is loaded on first use (lazy loading).
        Falls back gracefully if model is unavailable.
        """
        if not text:
            return None
        
        # Check cache first
        if text in self.embeddings_cache:
            return self.embeddings_cache[text]
        
        # Lazy load transformer on first use
        if not self.model_loaded and self.model_type == "minilm":
            def load_model():
                try:
                    from sentence_transformers import SentenceTransformer
                    # Try to load from local directory first
                    local_dir = os.getenv("HUGGINGFACE_LOCAL_DIR", os.path.join("streamlit_app", "models", "all-MiniLM-L6-v2"))
                    
                    if os.path.exists(local_dir):
                        logger.info(f"✓ Loading local sentence-transformer model from: {local_dir}")
                        self.transformer = SentenceTransformer(local_dir)
                        logger.info(f"✓ Model loaded successfully from local cache")
                    else:
                        logger.warning(f"⚠ Local model directory not found: {local_dir}")
                        logger.warning(f"⚠ Remote HuggingFace downloads are disabled")
                        logger.warning(f"⚠ Semantic embeddings will be unavailable")
                        logger.info(f"  To enable embeddings, download model from HuggingFace and place in: {local_dir}")
                        self.transformer = None
                    
                    self.model_loaded = True
                except Exception as e:
                    logger.error(f"❌ Error loading sentence-transformer model: {e}")
                    logger.warning(f"⚠ Continuing without semantic embeddings")
                    self.transformer = None
                    self.model_loaded = True
            
            # Try to load with 30-second timeout
            loader_thread = threading.Thread(target=load_model, daemon=True)
            loader_thread.start()
            loader_thread.join(timeout=30)
            
            if not self.model_loaded:
                logger.warning("⚠ Model loading timeout (>30s). Using hybrid scoring only.")
                self.transformer = None
                self.model_loaded = True
        
        if self.transformer is not None:
            try:
                # Using local sentence-transformers
                embedding = self.transformer.encode(text, convert_to_numpy=True)
                self.embeddings_cache[text] = embedding
                logger.debug(f"✓ Generated embedding for: '{text[:50]}...'")
                return embedding
            except Exception as e:
                logger.error(f"Error generating embedding: {e}")
                return None
        else:
            if not self.model_loaded:
                logger.debug(f"Local model not available for text: {text}")
            return None
    
    def get_embeddings_batch(self, texts: List[str]) -> Dict[str, np.ndarray]:
        """
        Get embeddings for multiple texts efficiently using local sentence-transformers.
        Caches results and batches processing for speed.
        Falls back gracefully if model is unavailable.
        """
        embeddings = {}
        
        # Find texts not yet cached
        texts_to_embed = [t for t in texts if t and t not in self.embeddings_cache]
        
        if not texts_to_embed:
            # All texts are already cached
            for text in texts:
                if text in self.embeddings_cache:
                    embeddings[text] = self.embeddings_cache[text]
            return embeddings
        
        # Load model with timeout if not already loaded
        if not self.model_loaded and self.model_type == "minilm":
            def load_model():
                try:
                    from sentence_transformers import SentenceTransformer
                    local_dir = os.getenv("HUGGINGFACE_LOCAL_DIR", os.path.join("streamlit_app", "models", "all-MiniLM-L6-v2"))
                    
                    if os.path.exists(local_dir):
                        logger.info(f"✓ Loading local model for batch processing from: {local_dir}")
                        self.transformer = SentenceTransformer(local_dir)
                        logger.info(f"✓ Batch embedding using {len(texts_to_embed)} texts")
                    else:
                        logger.warning(f"⚠ Local model not found: {local_dir}")
                        self.transformer = None
                    
                    self.model_loaded = True
                except Exception as e:
                    logger.error(f"Error loading model for batch: {e}")
                    self.transformer = None
                    self.model_loaded = True
            
            # Try to load with 30-second timeout
            loader_thread = threading.Thread(target=load_model, daemon=True)
            loader_thread.start()
            loader_thread.join(timeout=30)
            
            if not self.model_loaded:
                logger.warning("⚠ Batch model loading timeout. Skipping semantic embeddings.")
                self.transformer = None
                self.model_loaded = True
        
        if texts_to_embed and self.transformer is not None:
            try:
                # Batch process with local sentence-transformers
                batch_embeddings = self.transformer.encode(
                    texts_to_embed,
                    convert_to_numpy=True,
                    batch_size=32,
                    show_progress_bar=False
                )
                # Cache all new embeddings
                for text, embedding in zip(texts_to_embed, batch_embeddings):
                    self.embeddings_cache[text] = embedding
                logger.info(f"✓ Batch embedded {len(texts_to_embed)} texts successfully")
            except Exception as e:
                logger.error(f"Error in batch embedding: {e}")
        
        # Collect all embeddings (cached + newly created)
        for text in texts:
            if text in self.embeddings_cache:
                embeddings[text] = self.embeddings_cache[text]
        
        return embeddings
    
    def similarity_matrix(
        self,
        source_texts: List[str],
        file_texts: List[str]
    ) -> np.ndarray:
        """
        Compute similarity matrix between source and file texts.
        Returns zeros if embeddings are not available (graceful degradation).
        
        Args:
            source_texts: List of source column names
            file_texts: List of file column names
        
        Returns:
            Similarity matrix of shape (len(source_texts), len(file_texts))
        """
        # Check if transformer is available
        if self.transformer is None:
            logger.debug("Transformer not available - returning zero similarity matrix")
            return np.zeros((len(source_texts), len(file_texts)))
        
        # Get embeddings
        all_texts = source_texts + file_texts
        embeddings_dict = self.get_embeddings_batch(all_texts)
        
        # Check if we have any embeddings
        if not embeddings_dict:
            logger.warning("⚠ No semantic embeddings available - returning zeros")
            return np.zeros((len(source_texts), len(file_texts)))
        
        source_embeddings = []
        file_embeddings = []
        
        for t in source_texts:
            if t in embeddings_dict and embeddings_dict[t] is not None:
                source_embeddings.append(embeddings_dict[t])
            else:
                source_embeddings.append(None)
        
        for t in file_texts:
            if t in embeddings_dict and embeddings_dict[t] is not None:
                file_embeddings.append(embeddings_dict[t])
            else:
                file_embeddings.append(None)
        
        # If no valid embeddings, return zeros
        valid_source = [e for e in source_embeddings if e is not None]
        valid_file = [e for e in file_embeddings if e is not None]
        
        if not valid_source or not valid_file:
            logger.warning("⚠ Semantic embeddings unavailable - using hybrid scoring only")
            return np.zeros((len(source_texts), len(file_texts)))
        
        source_embeddings = np.array(valid_source)
        file_embeddings = np.array(valid_file)
        
        # Compute cosine similarity
        try:
            similarity = self._cosine_similarity(source_embeddings, file_embeddings)
            logger.debug(f"✓ Computed similarity matrix: {similarity.shape}")
            return similarity
        except Exception as e:
            logger.error(f"Error computing similarity: {e}")
            return np.zeros((len(source_texts), len(file_texts)))
    
    @staticmethod
    def _cosine_similarity(matrix1: np.ndarray, matrix2: np.ndarray) -> np.ndarray:
        """
        Compute cosine similarity between two matrices.
        """
        # Normalize rows
        matrix1_norm = matrix1 / (np.linalg.norm(matrix1, axis=1, keepdims=True) + 1e-8)
        matrix2_norm = matrix2 / (np.linalg.norm(matrix2, axis=1, keepdims=True) + 1e-8)
        
        # Compute cosine similarity
        similarity = np.dot(matrix1_norm, matrix2_norm.T)
        
        return similarity
    
    def clear_cache(self):
        """Clear the embeddings cache."""
        self.embeddings_cache.clear()


# Global instance
_engine = None


def get_semantic_engine(model: str = "minilm") -> SemanticSimilarityEngine:
    """Get or create the semantic engine singleton."""
    global _engine
    if _engine is None:
        _engine = SemanticSimilarityEngine(model)
    return _engine
