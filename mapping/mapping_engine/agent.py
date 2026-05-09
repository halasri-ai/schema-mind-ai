"""Module for resolving ambiguous column mappings."""

from typing import Dict, List, Tuple, Any, Optional
import logging
import json

logger = logging.getLogger(__name__)

# Configuration
CONFIDENCE_THRESHOLD_AUTO = 80
CONFIDENCE_THRESHOLD_REVIEW = 70
AMBIGUITY_THRESHOLD = 5  # Score difference in percentage points


class AmbiguityAgent:
    """
    AI agent that resolves ambiguous column mappings.
    
    Triggered when:
    - Top 2 scores differ by < AMBIGUITY_THRESHOLD
    - Confidence between CONFIDENCE_THRESHOLD_REVIEW and CONFIDENCE_THRESHOLD_AUTO
    """
    
    def __init__(self):
        self.decisions_made = 0
    
    def should_trigger(
        self,
        top_score: float,
        second_score: float,
        confidence: float
    ) -> bool:
        """
        Determine if agent should be triggered for ambiguity resolution.
        """
        # If very confident, no need for agent
        if confidence >= CONFIDENCE_THRESHOLD_AUTO:
            return False
        
        # If too low confidence, agent can't help much
        if confidence < CONFIDENCE_THRESHOLD_REVIEW:
            return False
        
        # If top two scores are very close, agent needed
        score_diff = abs(top_score - second_score)
        if score_diff < AMBIGUITY_THRESHOLD:
            return True
        
        return False
    
    def resolve_ambiguity(
        self,
        source_column: str,
        file_columns: List[str],
        scores: List[float],
        file_metadata: Dict[str, Any],
        top_k: int = 3
    ) -> Dict[str, Any]:
        """
        Resolve an ambiguous mapping using logical heuristics.
        
        Args:
            source_column: The source column name
            file_columns: All candidate file columns
            scores: Confidence scores for each candidate
            file_metadata: File metadata (samples, types, etc.)
            top_k: Number of top candidates to consider
        
        Returns:
            {
                "mapped_file_column": str (best match),
                "confidence_score": float,
                "explanation": str,
                "alternatives": List[str],
                "decision_type": "review"  # Marked as needs review
            }
        """
        # Get top candidates
        top_indices = sorted(
            range(len(scores)),
            key=lambda i: scores[i],
            reverse=True
        )[:top_k]
        
        top_candidates = [(file_columns[i], scores[i]) for i in top_indices]
        
        # Apply heuristics
        best_match = self._apply_heuristics(
            source_column,
            top_candidates,
            file_metadata
        )
        
        # Generate explanation
        explanation = self._generate_explanation(
            source_column,
            best_match,
            top_candidates
        )
        
        # Prepare alternatives
        alternatives = [col for col, _ in top_candidates[1:]]
        
        self.decisions_made += 1
        
        return {
            "mapped_file_column": best_match,
            "confidence_score": 75.0,  # Agent decision confidence
            "explanation": explanation,
            "alternatives": alternatives,
            "decision_type": "review"
        }
    
    def _apply_heuristics(
        self,
        source_column: str,
        top_candidates: List[Tuple[str, float]],
        file_metadata: Dict[str, Any]
    ) -> str:
        """
        Apply logical heuristics to break ties.
        """
        source_lower = source_column.lower()
        
        # Heuristic 1: Exact substring match
        for file_col, _ in top_candidates:
            if source_lower in file_col.lower() or file_col.lower() in source_lower:
                logger.info(f"Agent: Substring match for {source_column} -> {file_col}")
                return file_col
        
        # Heuristic 2: Common abbreviations
        abbreviations = self._get_abbreviations(source_column)
        for file_col, _ in top_candidates:
            file_lower = file_col.lower()
            if any(abbr in file_lower for abbr in abbreviations):
                logger.info(f"Agent: Abbreviation match for {source_column} -> {file_col}")
                return file_col
        
        # Heuristic 3: Pattern compatibility in samples
        best_col = self._pattern_heuristic(source_column, top_candidates, file_metadata)
        if best_col:
            logger.info(f"Agent: Pattern match for {source_column} -> {best_col}")
            return best_col
        
        # Fallback: highest score
        logger.info(f"Agent: Fallback to highest score for {source_column}")
        return top_candidates[0][0]
    
    @staticmethod
    def _get_abbreviations(col_name: str) -> List[str]:
        """Extract possible abbreviations from column name."""
        abbreviations = []
        
        # First letters of words
        words = col_name.lower().split('_')
        if len(words) > 1:
            abbr = ''.join(w[0] for w in words)
            abbreviations.append(abbr)
        
        # Common abbreviations
        common = {
            "identifier": ["id", "ids"],
            "customer": ["cust", "cust_"],
            "date": ["dt", "d"],
            "time": ["tm", "t"],
            "amount": ["amt", "amt_"],
            "status": ["sts", "stat"],
        }
        
        col_lower = col_name.lower()
        for key, abbrs in common.items():
            if key in col_lower:
                abbreviations.extend(abbrs)
        
        return abbreviations
    
    @staticmethod
    def _pattern_heuristic(
        source_column: str,
        top_candidates: List[Tuple[str, float]],
        file_metadata: Dict[str, Any]
    ) -> Optional[str]:
        """Apply pattern-based heuristics."""
        
        source_lower = source_column.lower()
        
        for file_col, _ in top_candidates:
            samples = file_metadata.get("column_samples", {}).get(file_col, [])
            
            # Check if samples are non-empty (suggests data-rich column)
            if samples and len(samples) > 2:
                return file_col
        
        return None
    
    @staticmethod
    def _generate_explanation(
        source_column: str,
        best_match: str,
        top_candidates: List[Tuple[str, float]]
    ) -> str:
        """Generate human-readable explanation for the mapping decision."""
        if not top_candidates:
            return f"Could not find a match for {source_column}"
        
        top_score = top_candidates[0][1]
        second_score = top_candidates[1][1] if len(top_candidates) > 1 else 0
        
        score_diff = top_score - second_score
        
        explanation = (
            f"Mapping '{source_column}' to '{best_match}' "
            f"(confidence: {top_score:.1f}%). "
        )
        
        if score_diff < 5:
            explanation += (
                f"Top candidates were very close (diff: {score_diff:.1f}%), "
                f"so ambiguity resolution logic was applied. "
            )
        else:
            explanation += (
                f"Matched against {len(top_candidates)} candidate columns. "
            )
        
        if len(top_candidates) > 1:
            second = top_candidates[1][0]
            explanation += f"Alternative: '{second}' ({second_score:.1f}%)"
        
        return explanation


# Global instance
_agent = None


def get_agent() -> AmbiguityAgent:
    """Get or create the agent singleton."""
    global _agent
    if _agent is None:
        _agent = AmbiguityAgent()
    return _agent
