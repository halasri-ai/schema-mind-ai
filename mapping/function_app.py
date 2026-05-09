"""
Local Mapping Engine with AWS Bedrock and HuggingFace Models

All processing runs locally - no cloud dependencies required.
Supports optional AWS Bedrock for advanced AI resolution of ambiguous mappings.
Multi-schema support: matches file columns against all available standard schemas.
"""

import json
import logging
from typing import Dict, Any, List
import sys
from pathlib import Path
import pandas as pd
import numpy as np

# Add current directory to path for relative imports
sys.path.insert(0, str(Path(__file__).parent))

from mapping_engine.scorer import HybridScorer
from mapping_engine.agent import get_agent, CONFIDENCE_THRESHOLD_AUTO, CONFIDENCE_THRESHOLD_REVIEW, AMBIGUITY_THRESHOLD

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


# ============================================================================
# LOCAL PROCESSING FUNCTIONS (no HTTP required)
# ============================================================================

def load_all_schemas(schema_dir: Path) -> Dict[str, List[str]]:
    """
    Load all schema files from the schema directory.
    
    Args:
        schema_dir: Path to schema directory
    
    Returns:
        Dictionary with schema name as key and column list as value
    """
    schemas = {}
    
    if not schema_dir.exists():
        logger.warning(f"Schema directory not found: {schema_dir}")
        return schemas
    
    # Load all CSV and XLSX files
    for schema_file in schema_dir.glob("*"):
        if schema_file.is_file() and schema_file.suffix.lower() in ['.csv', '.xlsx', '.xls']:
            try:
                if schema_file.suffix.lower() == '.csv':
                    df = pd.read_csv(schema_file, nrows=0)
                else:
                    df = pd.read_excel(schema_file, nrows=0)
                
                schema_name = schema_file.stem  # filename without extension
                column_list = list(df.columns)
                schemas[schema_name] = column_list
                logger.info(f"Loaded schema: {schema_name} ({len(column_list)} columns)")
            except Exception as e:
                logger.error(f"Failed to load schema {schema_file.name}: {e}")
                continue
    
    return schemas


def process_mapping(
    source_schema: List[str],
    file_metadata: Dict[str, Any],
    config: Dict[str, Any] = None,
    schemas_dict: Dict[str, List[str]] = None
) -> Dict[str, Any]:
    """
    Process column mapping against ALL available schemas.
    
    Args:
        source_schema: Legacy parameter (ignored when schemas_dict provided)
        file_metadata: File metadata (sheets, columns, samples)
        config: Optional configuration dict
        schemas_dict: Dictionary of all available schemas {schema_name: columns}
    
    Returns:
        Mapping results for each sheet against all schemas
    """
    logger.info("Local mapping processing started (multi-schema mode)")
    
    if not file_metadata or "sheets" not in file_metadata:
        logger.error("No file metadata provided")
        return {"error": "file_metadata.sheets is required"}
    
    # If no schemas provided, return error
    if not schemas_dict:
        logger.error("No schemas provided for multi-schema matching")
        return {"error": "schemas_dict is required"}
    
    # Process each sheet
    try:
        results = {
            "file_name": file_metadata.get("file_name", "unknown"),
            "schemas": list(schemas_dict.keys()),
            "sheets": {}
        }
        
        sheets_metadata = file_metadata.get("sheets", {})
        
        for sheet_name, sheet_data in sheets_metadata.items():
            logger.info(f"Processing sheet: {sheet_name}")
            
            sheet_result = process_sheet_multi_schema(
                sheet_name=sheet_name,
                sheet_data=sheet_data,
                schemas_dict=schemas_dict,
                config=config
            )
            
            results["sheets"][sheet_name] = sheet_result
        
        logger.info("Local multi-schema mapping complete")
        return results
    
    except Exception as e:
        logger.exception("Error during multi-schema mapping")
        return {"error": str(e)}


def process_sheet_multi_schema(
    sheet_name: str,
    sheet_data: Dict[str, Any],
    schemas_dict: Dict[str, List[str]],
    config: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Process a single sheet against multiple schemas.
    
    Args:
        sheet_name: Name of the sheet
        sheet_data: Sheet metadata with columns and samples
        schemas_dict: Dictionary of schemas {schema_name: columns}
        config: Configuration dict
    
    Returns:
        Mapping results for this sheet against all schemas
    """
    file_columns = sheet_data.get("columns", [])
    
    if not file_columns:
        logger.warning(f"Sheet '{sheet_name}' has no columns")
        return {
            "sheet_name": sheet_name,
            "file_columns": [],
            "schema_mappings": {},
            "errors": ["No columns found in sheet"]
        }
    
    schema_mappings = {}
    
    # Match against each schema
    for schema_name, source_schema in schemas_dict.items():
        logger.info(f"Matching sheet '{sheet_name}' against schema '{schema_name}'")
        
        mapping_result = process_sheet(
            sheet_name=sheet_name,
            sheet_data=sheet_data,
            source_schema=source_schema,
            config=config
        )
        
        schema_mappings[schema_name] = mapping_result
    
    # Compute summary: which file column matched to which schema
    column_distribution = {}  # file_col -> {schema_name: source_col}
    
    for schema_name, mapping_result in schema_mappings.items():
        mappings = mapping_result.get("mappings", {})
        for src_col, info in mappings.items():
            mapped_to = info.get("mapped_file_column", "")
            if mapped_to:  # Only count mapped columns
                if mapped_to not in column_distribution:
                    column_distribution[mapped_to] = {}
                column_distribution[mapped_to][schema_name] = src_col
    
    return {
        "sheet_name": sheet_name,
        "file_columns": file_columns,
        "schema_mappings": schema_mappings,
        "column_distribution": column_distribution
    }


def process_sheet(
    sheet_name: str,
    sheet_data: Dict[str, Any],
    source_schema: List[str],
    config: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Process a single sheet and compute column mappings.
    """
    file_columns = sheet_data.get("columns", [])
    
    if not file_columns:
        logger.warning(f"Sheet '{sheet_name}' has no columns")
        return {
            "sheet_name": sheet_name,
            "file_columns": [],
            "mappings": {},
            "errors": ["No columns found in sheet"]
        }
    
    # Initialize scorer
    scorer = HybridScorer()
    agent = get_agent()
    agent_enabled = config.get("agent_enabled", True)
    
    # Compute scores
    try:
        scores = scorer.score_columns(
            source_columns=source_schema,
            file_columns=file_columns,
            file_metadata=sheet_data
        )
    except Exception as e:
        logger.error(f"Scoring error: {e}")
        return {
            "sheet_name": sheet_name,
            "file_columns": file_columns,
            "mappings": {},
            "errors": [f"Scoring failed: {str(e)}"]
        }
    
    # Generate mappings with decisions
    mappings = {}
    
    for src_idx, src_col in enumerate(source_schema):
        src_scores = scores[src_idx, :]
        best_idx = int(src_scores.argmax())
        best_score = float(src_scores[best_idx])
        
        # Get top matches
        top_matches = scorer.get_top_k_matches(scores, src_idx, k=3)
        
        # Determine decision type
        if best_score >= CONFIDENCE_THRESHOLD_AUTO:
            decision_type = "auto"
        elif best_score >= CONFIDENCE_THRESHOLD_REVIEW:
            # Check for ambiguity
            second_score = float(src_scores[np.argsort(src_scores)[-2]]) if len(src_scores) > 1 else 0
            
            if agent_enabled and agent.should_trigger(best_score, second_score, best_score):
                # Use agent for resolution
                agent_result = agent.resolve_ambiguity(
                    source_column=src_col,
                    file_columns=file_columns,
                    scores=src_scores.tolist(),
                    file_metadata=sheet_data
                )
                
                mappings[src_col] = agent_result
                continue
            else:
                decision_type = "review"
        else:
            decision_type = "manual"
        
        # Build mapping result
        alternatives = [file_columns[idx] for idx, _ in top_matches[1:]]
        
        mapping_result = {
            "mapped_file_column": file_columns[best_idx],
            "confidence_score": best_score,
            "decision_type": decision_type,
            "alternatives": alternatives,
            "explanation": generate_explanation(
                src_col,
                file_columns[best_idx],
                best_score,
                alternatives
            )
        }
        
        mappings[src_col] = mapping_result
    
    # --- Deduplicate file column assignments (keep best, expose alternatives) ---
    # Build reverse index: file_col -> list of (src_col, score, decision_type)
    file_assignments = {}
    for src_col, info in mappings.items():
        mapped = info.get("mapped_file_column")
        if not mapped:
            continue
        file_assignments.setdefault(mapped, []).append((src_col, info.get("confidence_score", 0.0), info.get("decision_type", "manual")))

    # Resolve duplicates
    for file_col, assigned_list in file_assignments.items():
        if len(assigned_list) <= 1:
            continue
        # Sort by score desc
        assigned_sorted = sorted(assigned_list, key=lambda x: x[1], reverse=True)
        top_src, top_score, top_decision = assigned_sorted[0]

        # If the top score is below review threshold, mark all as not mapped
        if top_score < CONFIDENCE_THRESHOLD_REVIEW:
            for src_col, _, _ in assigned_sorted:
                mappings[src_col]["mapped_file_column"] = ""
                mappings[src_col]["decision_type"] = "not_mapped"
                mappings[src_col]["explanation"] = (
                    f"No suitable mapping for '{src_col}' - all candidates below review threshold ({top_score:.1f})."
                )
            continue

        # Keep top_src mapped to file_col; for others, clear mapping and add to top's alternatives
        for src_col, score, decision in assigned_sorted[1:]:
            # Add to top's alternatives if not already present
            if src_col not in mappings[top_src].get("alternatives", []):
                mappings[top_src].setdefault("alternatives", []).append(src_col)
            # Mark the lower ones as alternatives/review
            mappings[src_col]["mapped_file_column"] = ""
            mappings[src_col]["decision_type"] = "review"
            mappings[src_col]["explanation"] = (
                f"Mapping conflict: best match for '{src_col}' was taken by '{top_src}'. Marked for review and listed as alternative."
            )

        # Update top's explanation to mention duplicate resolution
        mappings[top_src]["explanation"] += f" (Chosen among {len(assigned_sorted)} conflicting sources)"

    # Recompute summary metrics with dedupe applied
    summary = {
        "total_source_columns": len(source_schema),
        "total_file_columns": len(file_columns),
        "auto_mapped": sum(1 for m in mappings.values() if m["decision_type"] == "auto"),
        "review_needed": sum(1 for m in mappings.values() if m["decision_type"] == "review"),
        "manual_mapping": sum(1 for m in mappings.values() if m["decision_type"] == "manual"),
        "not_mapped": sum(1 for m in mappings.values() if m["decision_type"] == "not_mapped")
    }

    return {
        "sheet_name": sheet_name,
        "file_columns": file_columns,
        "mappings": mappings,
        "summary": summary
    }


def generate_explanation(
    source_col: str,
    file_col: str,
    confidence: float,
    alternatives: List[str]
) -> str:
    """Generate a human-readable explanation for the mapping."""
    explanation = (
        f"Mapped '{source_col}' to '{file_col}' with {confidence:.1f}% confidence. "
    )
    
    if confidence >= 80:
        explanation += "High confidence - automatic mapping recommended."
    elif confidence >= 70:
        explanation += "Moderate confidence - review recommended."
    else:
        explanation += "Low confidence - manual review required."
    
    if alternatives:
        explanation += f" Other candidates: {', '.join(alternatives[:2])}"
    
    return explanation
