# Hybrid column scorer combining multiple similarity metrics

import numpy as np
from typing import Dict, List, Tuple, Any
import logging
from difflib import SequenceMatcher
import sys
from pathlib import Path

# Add current directory to path for relative imports
sys.path.insert(0, str(Path(__file__).parent))

from semantic import get_semantic_engine
from patterns import PatternDetector

logger = logging.getLogger(__name__)

# Scoring weights
SCORING_WEIGHTS = {
    "string_similarity": 0.25,
    "token_match": 0.20,
    "semantic_similarity": 0.35,
    "pattern_match": 0.20
}


class HybridScorer:
    """
    Score column matches using hybrid approach:
    - String similarity
    - Token overlap
    - Semantic embeddings
    - Data pattern compatibility
    """
    
    def __init__(self):
        self.semantic_engine = get_semantic_engine()
        self.pattern_detector = PatternDetector()
    
    def score_columns(
        self,
        source_columns: List[str],
        file_columns: List[str],
        file_metadata: Dict[str, Any],
        source_patterns: Dict[str, str] = None
    ) -> np.ndarray:
        """
        Score all source × file column pairs.
        
        Args:
            source_columns: List of source (standard) column names
            file_columns: List of file column names
            file_metadata: Metadata including patterns, samples
            source_patterns: Optional predefined patterns for source columns
        
        Returns:
            Score matrix of shape (len(source), len(file)) with values 0-100
        """
        n_source = len(source_columns)
        n_file = len(file_columns)
        
        # Initialize score components
        string_scores = np.zeros((n_source, n_file))
        token_scores = np.zeros((n_source, n_file))
        semantic_scores = np.zeros((n_source, n_file))
        pattern_scores = np.zeros((n_source, n_file))
        
        # 1️⃣ STRING SIMILARITY
        logger.info("Computing string similarity scores...")
        string_scores = self._string_similarity_matrix(source_columns, file_columns)
        
        # 2️⃣ TOKEN OVERLAP
        logger.info("Computing token overlap scores...")
        token_scores = self._token_overlap_matrix(source_columns, file_columns)
        
        # 3️⃣ SEMANTIC SIMILARITY
        logger.info("Computing semantic similarity scores...")
        semantic_scores = self._semantic_similarity_matrix(source_columns, file_columns)
        
        # 4️⃣ PATTERN MATCHING
        logger.info("Computing pattern compatibility scores...")
        pattern_scores = self._pattern_compatibility_matrix(
            source_columns, file_columns, file_metadata, source_patterns
        )
        
        # COMBINE SCORES
        final_scores = (
            SCORING_WEIGHTS["string_similarity"] * string_scores +
            SCORING_WEIGHTS["token_match"] * token_scores +
            SCORING_WEIGHTS["semantic_similarity"] * semantic_scores +
            SCORING_WEIGHTS["pattern_match"] * pattern_scores
        )
        
        # Normalize to 0-100
        final_scores = self._normalize_scores(final_scores)
        
        logger.info(f"Scoring complete: {n_source} × {n_file} matrix")
        
        return final_scores
    
    @staticmethod
    def _normalize_text(text: str) -> str:
        """Normalize text for comparison."""
        return text.lower().strip().replace('_', ' ').replace('-', ' ')
    
    @staticmethod
    def _tokenize(text: str) -> List[str]:
        """Tokenize text into words."""
        normalized = HybridScorer._normalize_text(text)
        return [t for t in normalized.split() if t]
    
    @staticmethod
    def _string_similarity_matrix(
        source_cols: List[str],
        file_cols: List[str]
    ) -> np.ndarray:
        """Compute string similarity matrix using SequenceMatcher."""
        scores = np.zeros((len(source_cols), len(file_cols)))
        
        for i, src_col in enumerate(source_cols):
            src_norm = HybridScorer._normalize_text(src_col)
            for j, file_col in enumerate(file_cols):
                file_norm = HybridScorer._normalize_text(file_col)
                ratio = SequenceMatcher(None, src_norm, file_norm).ratio()
                scores[i, j] = ratio
        
        return scores
    
    @staticmethod
    def _token_overlap_matrix(
        source_cols: List[str],
        file_cols: List[str]
    ) -> np.ndarray:
        """Compute token overlap matrix (Jaccard similarity)."""
        scores = np.zeros((len(source_cols), len(file_cols)))
        
        for i, src_col in enumerate(source_cols):
            src_tokens = set(HybridScorer._tokenize(src_col))
            for j, file_col in enumerate(file_cols):
                file_tokens = set(HybridScorer._tokenize(file_col))
                
                if not src_tokens or not file_tokens:
                    scores[i, j] = 0.0
                else:
                    intersection = len(src_tokens & file_tokens)
                    union = len(src_tokens | file_tokens)
                    scores[i, j] = intersection / union if union > 0 else 0.0
        
        return scores
    
    def _semantic_similarity_matrix(
        self,
        source_cols: List[str],
        file_cols: List[str]
    ) -> np.ndarray:
        """Compute semantic similarity matrix using embeddings."""
        try:
            similarity = self.semantic_engine.similarity_matrix(source_cols, file_cols)
            # Clip to [0, 1]
            similarity = np.clip(similarity, 0, 1)
            return similarity
        except Exception as e:
            logger.warning(f"Semantic similarity failed: {e}")
            return np.zeros((len(source_cols), len(file_cols)))
    
    def _pattern_compatibility_matrix(
        self,
        source_cols: List[str],
        file_cols: List[str],
        file_metadata: Dict[str, Any],
        source_patterns: Dict[str, str] = None
    ) -> np.ndarray:
        """Compute pattern compatibility matrix."""
        scores = np.zeros((len(source_cols), len(file_cols)))
        
        # Get file column patterns
        file_patterns = {}
        for file_col in file_cols:
            samples = file_metadata.get("column_samples", {}).get(file_col, [])
            pattern = PatternDetector.detect_pattern(samples)
            file_patterns[file_col] = pattern
        
        for i, src_col in enumerate(source_cols):
            # Infer source pattern from column name or use provided
            if source_patterns and src_col in source_patterns:
                src_pattern = source_patterns[src_col]
            else:
                src_pattern = self._infer_pattern_from_name(src_col)
            
            for j, file_col in enumerate(file_cols):
                file_pattern = file_patterns[file_col]
                compatibility = PatternDetector.pattern_compatibility_score(
                    file_pattern, src_pattern
                )
                scores[i, j] = compatibility
        
        return scores
    
    @staticmethod
    def _infer_pattern_from_name(col_name: str) -> str:
        """Infer pattern from column name."""
        col_lower = col_name.lower()
        
        # Check datetime keywords
        if any(kw in col_lower for kw in ["date", "time", "created", "updated"]):
            return "datetime"
        
        # Check numeric keywords
        if any(kw in col_lower for kw in ["id", "count", "amount", "price", "number"]):
            return "numeric"
        
        # Check categorical keywords
        if any(kw in col_lower for kw in ["status", "type", "code", "category"]):
            return "categorical"
        
        # Default to text
        return "text"
    
    @staticmethod
    def _normalize_scores(scores: np.ndarray) -> np.ndarray:
        """Normalize scores to 0-100 range."""
        if scores.size == 0:
            return scores
        
        min_val = scores.min()
        max_val = scores.max()
        
        if max_val == min_val:
            return np.full_like(scores, 50.0)
        
        normalized = 100 * (scores - min_val) / (max_val - min_val)
        return np.clip(normalized, 0, 100)
    
    def get_top_k_matches(
        self,
        scores: np.ndarray,
        source_col_idx: int,
        k: int = 3
    ) -> List[Tuple[int, float]]:
        """
        Get top-K file column matches for a source column.
        
        Returns:
            List of (file_col_idx, score) tuples
        """
        col_scores = scores[source_col_idx, :]
        top_indices = np.argsort(col_scores)[::-1][:k]
        
        return [(idx, col_scores[idx]) for idx in top_indices]
