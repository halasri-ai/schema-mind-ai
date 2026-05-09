# Pattern detection module for data type inference

import re
from typing import Dict, List, Any
import logging

logger = logging.getLogger(__name__)

# Data type patterns
DATA_TYPES = {
    "datetime": {
        "patterns": [
            r"^\d{4}-\d{2}-\d{2}",  # YYYY-MM-DD
            r"^\d{2}/\d{2}/\d{4}",  # MM/DD/YYYY or DD/MM/YYYY
            r"^\d{1,2}-\w+-\d{4}",  # D-Mon-YYYY
        ],
        "keywords": ["date", "time", "timestamp", "created", "updated", "posted"]
    },
    "numeric": {
        "patterns": [r"^-?\d+\.?\d*$"],
        "keywords": ["amount", "count", "total", "price", "quantity", "value", "number", "id"]
    },
    "categorical": {
        "patterns": [r"^[A-Z]{2,}$"],  # Codes like "US", "ACTIVE"
        "keywords": ["category", "status", "type", "code", "state", "region", "level"]
    },
    "text": {
        "patterns": [],
        "keywords": ["name", "description", "text", "title", "subject", "comment"]
    }
}


class PatternDetector:
    """
    Detect data patterns from sample values.
    """
    
    @staticmethod
    def detect_pattern(sample_values: List[str], inferred_type: str = None) -> str:
        """
        Detect the data pattern (datetime, numeric, categorical, text).
        
        Args:
            sample_values: List of sample values from the column
            inferred_type: Pandas inferred type (optional)
        
        Returns:
            Pattern type: "datetime", "numeric", "categorical", or "text"
        """
        if not sample_values:
            return "text"
        
        # Check datetime patterns
        if PatternDetector._is_datetime(sample_values):
            return "datetime"
        
        # Check numeric patterns
        if PatternDetector._is_numeric(sample_values):
            return "numeric"
        
        # Check categorical (low variety)
        if PatternDetector._is_categorical(sample_values):
            return "categorical"
        
        return "text"
    
    @staticmethod
    def _is_datetime(samples: List[str]) -> bool:
        """Check if samples are datetime values."""
        datetime_patterns = DATA_TYPES["datetime"]["patterns"]
        
        matches = 0
        for sample in samples[:min(5, len(samples))]:
            for pattern in datetime_patterns:
                if re.match(pattern, str(sample)):
                    matches += 1
                    break
        
        return matches >= len(samples) * 0.6  # At least 60% match
    
    @staticmethod
    def _is_numeric(samples: List[str]) -> bool:
        """Check if samples are numeric values."""
        numeric_pattern = DATA_TYPES["numeric"]["patterns"][0]
        
        matches = 0
        for sample in samples[:min(5, len(samples))]:
            try:
                float(str(sample))
                matches += 1
            except ValueError:
                pass
        
        return matches >= len(samples) * 0.7  # At least 70% match
    
    @staticmethod
    def _is_categorical(samples: List[str]) -> bool:
        """Check if samples are categorical (low cardinality)."""
        unique_ratio = len(set(str(s) for s in samples)) / len(samples) if samples else 1.0
        return unique_ratio < 0.3  # Less than 30% unique values
    
    @staticmethod
    def get_pattern_keywords(pattern: str) -> List[str]:
        """Get keywords associated with a pattern type."""
        return DATA_TYPES.get(pattern, {}).get("keywords", [])
    
    @staticmethod
    def pattern_compatibility_score(
        file_pattern: str,
        source_pattern: str
    ) -> float:
        """
        Compute compatibility score between two patterns.
        
        Returns score between 0 and 1.
        """
        if file_pattern == source_pattern:
            return 1.0
        
        # Define compatibility matrix
        compatibility = {
            ("numeric", "numeric"): 1.0,
            ("numeric", "categorical"): 0.3,
            ("numeric", "text"): 0.2,
            ("numeric", "datetime"): 0.1,
            
            ("datetime", "datetime"): 1.0,
            ("datetime", "text"): 0.4,
            ("datetime", "numeric"): 0.1,
            ("datetime", "categorical"): 0.1,
            
            ("categorical", "categorical"): 1.0,
            ("categorical", "numeric"): 0.3,
            ("categorical", "text"): 0.5,
            ("categorical", "datetime"): 0.1,
            
            ("text", "text"): 1.0,
            ("text", "categorical"): 0.5,
            ("text", "numeric"): 0.2,
            ("text", "datetime"): 0.4,
        }
        
        key = (file_pattern, source_pattern)
        return compatibility.get(key, 0.0)
