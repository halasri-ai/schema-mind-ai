"""
Auto-detection of best matching source schema file.
Uses Gemini AI (if available) or string similarity fallback.
"""
import logging
from typing import List, Dict, Tuple
from pathlib import Path
import pandas as pd

logger = logging.getLogger(__name__)

try:
    import google.generativeai as genai
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False


def _similarity_score(str1: str, str2: str) -> float:
    """Calculate simple string similarity score (0-1)."""
    str1, str2 = str1.lower(), str2.lower()
    if str1 == str2:
        return 1.0
    
    # Use character overlap ratio
    common = sum(1 for c in str1 if c in str2)
    return common / max(len(str1), len(str2), 1)


def _get_schema_columns(schema_path: Path) -> List[str]:
    """Extract column names from schema file."""
    try:
        if schema_path.suffix.lower() == ".csv":
            df = pd.read_csv(schema_path, nrows=0)
        else:
            df = pd.read_excel(schema_path, nrows=0)
        return list(df.columns)
    except Exception as e:
        logger.warning(f"Could not read schema file {schema_path}: {e}")
        return []


def _compute_schema_match_score_simple(
    file_columns: List[str],
    schema_columns: List[str]
) -> float:
    """
    Compute match score between file columns and schema columns.
    Returns 0-1 score based on how many schema columns match file columns.
    """
    if not schema_columns:
        return 0.0
    
    matched = 0
    for schema_col in schema_columns:
        # Check if schema column has a similar match in file
        for file_col in file_columns:
            if _similarity_score(schema_col, file_col) > 0.6:
                matched += 1
                break
    
    return matched / len(schema_columns)

def _detect_best_schema_with_gemini(
    file_columns: List[str],
    schema_info: Dict[str, List[str]],
    api_key: str = None
) -> Tuple[str, float]:
    """
    Use Gemini to detect best matching schema.
    
    Args:
        file_columns: Columns from uploaded file
        schema_info: {schema_name: [columns]}
        api_key: Optional Gemini API key
    
    Returns:
        (best_schema_name, confidence_score)
    """
    if not GEMINI_AVAILABLE or not api_key:
        return None, 0.0
    
    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel("gemini-1.5-flash")
        
        # Build prompt
        prompt = f"""You are a data mapping expert. Given a file with columns and multiple source schema options, 
identify which source schema is the BEST match for this file.

FILE COLUMNS (from uploaded Excel):
{', '.join(file_columns[:20])}

AVAILABLE SOURCE SCHEMAS:
"""
        for schema_name, schema_cols in schema_info.items():
            prompt += f"\n- {schema_name}: {', '.join(schema_cols[:15])}"
        
        prompt += """

RESPOND ONLY with JSON (no markdown):
{
  "best_schema": "schema_name",
  "confidence": 85,
  "reasoning": "brief explanation"
}
"""
        
        response = model.generate_content(prompt)
        import json
        import re
        
        json_match = re.search(r"\{.*\}", response.text, re.DOTALL)
        if json_match:
            result = json.loads(json_match.group(0))
            best = result.get("best_schema")
            conf = result.get("confidence", 0) / 100.0  # Normalize to 0-1
            
            if best in schema_info:
                logger.info(f"Gemini detected best schema: {best} (confidence: {conf:.2%})")
                return best, conf
        
        return None, 0.0
    except Exception as e:
        logger.warning(f"Gemini schema detection failed: {e}")
        return None, 0.0


def detect_best_schema(
    file_columns: List[str],
    schema_dir: Path,
    gemini_api_key: str = None
) -> Tuple[Path, float, str]:
    """
    Detect the best matching source schema file for uploaded file.
    
    Args:
        file_columns: List of column names from uploaded file
        schema_dir: Directory containing schema files
        gemini_api_key: Optional Gemini API key for AI-powered detection
    
    Returns:
        (best_schema_path, confidence, detection_method)
        - detection_method: "gemini", "similarity", "default"
    """
    schema_files = [p for p in schema_dir.iterdir() if p.suffix.lower() in [".csv", ".xlsx", ".xls"]]
    
    if not schema_files:
        return None, 0.0, "no_schemas"
    
    # Try Gemini first
    if gemini_api_key:
        schema_info = {}
        for schema_path in schema_files:
            cols = _get_schema_columns(schema_path)
            if cols:
                schema_info[schema_path.name] = cols
        
        if schema_info:
            best_name, confidence = _detect_best_schema_with_gemini(file_columns, schema_info, gemini_api_key)
            if best_name:
                # Find the path for this name
                for schema_path in schema_files:
                    if schema_path.name == best_name:
                        return schema_path, confidence, "gemini"
    
    # Fallback: simple similarity matching
    best_score = 0.0
    best_path = None
    
    for schema_path in schema_files:
        schema_cols = _get_schema_columns(schema_path)
        if schema_cols:
            score = _compute_schema_match_score_simple(file_columns, schema_cols)
            if score > best_score:
                best_score = score
                best_path = schema_path
    
    if best_path:
        return best_path, best_score, "similarity"
    
    # Default: return first schema
    if schema_files:
        return schema_files[0], 0.0, "default"
    
    return None, 0.0, "no_schemas"
