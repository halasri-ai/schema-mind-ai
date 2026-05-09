"""
Azure OpenAI integration for intelligent column matching support.
Provides semantic analysis and ambiguity resolution using Azure OpenAI.
"""

import logging
import os
import re
from typing import Dict, List, Optional, Any

logger = logging.getLogger(__name__)

# Configuration from environment
AZURE_OPENAI_KEY = os.getenv("AZURE_OPENAI_KEY")
AZURE_OPENAI_BASE = os.getenv("AZURE_OPENAI_BASE")
AZURE_OPENAI_VERSION = os.getenv("AZURE_OPENAI_VERSION") or os.getenv("AZURE_OPENAI_API_VERSION", "2024-02-15-preview")
AZURE_OPENAI_DEPLOYMENT_NAME = os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME", "gpt-4o")

# Try to import Azure OpenAI, but don't fail if package is missing
try:
    from openai import AzureOpenAI
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False
    AzureOpenAI = None
    logger.warning("openai package not installed. Install with: pip install openai>=1.0.0")

AZURE_AVAILABLE = OPENAI_AVAILABLE and all([
    AZURE_OPENAI_KEY,
    AZURE_OPENAI_BASE,
    AZURE_OPENAI_DEPLOYMENT_NAME
])

# Lazy client initialization
_client = None

def _get_client():
    """Lazy initialization of Azure OpenAI client to avoid SSL issues at import time."""
    global _client
    
    if not AZURE_AVAILABLE:
        return None
    
    if _client is None:
        try:
            # Temporarily disable SSL verification for Azure OpenAI client to avoid certificate issues
            import os
            ssl_cert_file = os.environ.pop("SSL_CERT_FILE", None)
            ssl_cert_dir = os.environ.pop("SSL_CERT_DIR", None)
            
            try:
                _client = AzureOpenAI(
                    api_key=AZURE_OPENAI_KEY,
                    api_version=AZURE_OPENAI_VERSION,
                    azure_endpoint=AZURE_OPENAI_BASE
                )
                logger.info("Azure OpenAI client initialized successfully")
            finally:
                # Restore environment variables
                if ssl_cert_file:
                    os.environ["SSL_CERT_FILE"] = ssl_cert_file
                if ssl_cert_dir:
                    os.environ["SSL_CERT_DIR"] = ssl_cert_dir
        except Exception as e:
            logger.error(f"Failed to initialize Azure OpenAI client: {e}")
            return None
    
    return _client


def _infer_simple_type(values: List[str]) -> str:
    """Infer a simple data type from sample values."""
    if not values:
        return "unknown"
    vals = [str(v).strip() for v in values if v is not None]
    if not vals:
        return "unknown"
    # integer
    if all(re.fullmatch(r"[-+]?\d+", v) for v in vals):
        return "integer"
    # float
    if all(re.fullmatch(r"[-+]?\d+(?:\.\d+)?", v) for v in vals):
        return "float"
    # date-like heuristic
    date_like = sum(1 for v in vals if re.search(r"\d{4}-\d{2}-\d{2}|\d{2}/\d{2}/\d{4}", v))
    if date_like >= max(1, len(vals) // 2):
        return "date"
    # email heuristic
    if any("@" in v for v in vals):
        return "email"
    return "string"


def _format_samples_preview(values: List[str], max_items: int = 5) -> str:
    if not values:
        return "(no samples)"
    preview = [str(v) for v in values[:max_items]]
    return ", ".join(preview)

# Log availability status
if not OPENAI_AVAILABLE:
    logger.warning("Azure OpenAI not available - openai package not installed.")
elif not all([AZURE_OPENAI_KEY, AZURE_OPENAI_BASE, AZURE_OPENAI_DEPLOYMENT_NAME]):
    logger.warning("Azure OpenAI not configured. Set environment variables to enable AI support.")


def get_ai_mapping_suggestion(
    source_column: str,
    file_column: str,
    file_columns: List[str],
    source_columns: List[str],
    file_samples: Dict[str, List[str]] = None
) -> Dict[str, Any]:
    """
    Use Azure OpenAI to suggest the best column mapping.
    
    Args:
        source_column: Source schema column name
        file_column: Current candidate file column
        file_columns: All available file columns
        source_columns: All available source columns
        file_samples: Sample data from file columns
    
    Returns:
        {
            "suggestion": str (best match),
            "confidence": float (0-100),
            "reasoning": str,
            "alternatives": List[str]
        }
    """
    client = _get_client()
    if not AZURE_AVAILABLE or client is None:
        return {
            "suggestion": file_column,
            "confidence": 0,
            "reasoning": "AI not available",
            "alternatives": [],
            "inferred_type": "unknown"
        }
    
    try:
        # Build context about alternatives and include sample-based data hints
        alternatives_text = "\n".join([f"- {col}" for col in file_columns[:5]])

        samples_text = ""
        data_summary_text = ""
        if file_samples and file_column in file_samples:
            all_samples = list(file_samples[file_column])
            samples = all_samples[:8]
            inferred = _infer_simple_type(all_samples[:20])
            sample_count = len(all_samples)
            samples_text = f"\nSample examples ({min(sample_count,8)}/{sample_count}): {_format_samples_preview(samples, max_items=5)}"
            data_summary_text = f"\nInferred type: {inferred}. {min(sample_count,8)} example values shown."

        # Include a short type/ sample summary for top alternatives when available
        alt_summaries = []
        if file_samples:
            for col in file_columns[:4]:
                svals = file_samples.get(col, [])
                if svals:
                    alt_type = _infer_simple_type(svals[:20])
                    alt_preview = _format_samples_preview(svals, max_items=3)
                    alt_summaries.append(f"- {col}: type={alt_type}, examples=({alt_preview})")
        alt_summary_text = "\n" + "\n".join(alt_summaries) if alt_summaries else ""

        prompt = f"""You are a column mapping expert. Use both the column names and the sample data to determine if '{source_column}' should map to '{file_column}'.

Source Column: {source_column}
Candidate File Column: {file_column}{samples_text}{data_summary_text}

Other available file columns:
{alternatives_text}{alt_summary_text}

When making your decision, explicitly check semantic meaning, sample data values, and data type compatibility. If sample values are inconsistent with the source semantics, downgrade confidence and explain why. Provide your analysis in this format:
1. Is this a good match? (Yes/No)
2. Confidence (0-100): 
3. Brief reasoning (mention sample-driven checks):
4. Better alternatives if any (name them and why):

If you think additional checks are needed, list them concisely."""

        response = client.chat.completions.create(
            model=AZURE_OPENAI_DEPLOYMENT_NAME,
            messages=[
                {"role": "system", "content": "You are a database schema expert analyzing column name mappings."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.3,
            max_tokens=200
        )
        
        response_text = response.choices[0].message.content
        
        # Parse response
        lines = response_text.split('\n')
        confidence = 70  # Default
        reasoning = ""
        alternatives = []
        inferred_type = "unknown"
        
        for line in lines:
            if "confidence" in line.lower():
                try:
                    confidence = int(''.join(filter(str.isdigit, line.split(':')[-1])))
                except:
                    pass
            if "reasoning" in line.lower() or "because" in line.lower():
                reasoning = line.split(':')[-1].strip()
            if "alternative" in line.lower():
                alternatives = [col.strip() for col in line.split(':')[-1].split(',')]
        
        logger.info(f"AI Analysis: {source_column} → {file_column} (Confidence: {confidence}%)")
        
        # If sample data was provided, include inferred type in returned metadata
        try:
            if file_samples and file_column in file_samples:
                inferred_type = _infer_simple_type(list(file_samples[file_column])[:20])
        except Exception:
            inferred_type = "unknown"

        return {
            "suggestion": file_column,
            "confidence": min(confidence, 100),
            "reasoning": reasoning or response_text[:100],
            "alternatives": alternatives[:2],
            "inferred_type": inferred_type
        }
    
    except Exception as e:
        logger.error(f"Azure OpenAI error: {e}")
        return {
            "suggestion": file_column,
            "confidence": 0,
            "reasoning": f"AI analysis failed: {str(e)}",
            "alternatives": [],
            "inferred_type": "unknown"
        }


def resolve_ambiguous_mappings(
    ambiguous_pairs: List[Dict[str, Any]],
    schemas: Dict[str, List[str]]
) -> Dict[str, Any]:
    """
    Use Azure OpenAI to resolve ambiguous mappings with low confidence.
    
    Args:
        ambiguous_pairs: List of low-confidence mappings
        schemas: Available schemas for context
    
    Returns:
        Resolved mappings with AI reasoning
    """
    client = _get_client()
    if not AZURE_AVAILABLE or not ambiguous_pairs or client is None:
        return {}
    
    try:
        pairs_text = "\n".join([
            f"- '{p['source']}' could map to {[p['candidates'][:2]]}" 
            for p in ambiguous_pairs
        ])
        
        prompt = f"""Review these ambiguous column mappings and suggest the best matches:

{pairs_text}

For each pair, explain your reasoning and provide a confidence score 0-100.
Format: source_column → best_target_column (confidence: XX%)"""

        response = client.chat.completions.create(
            model=AZURE_OPENAI_DEPLOYMENT_NAME,
            messages=[
                {"role": "system", "content": "You are an expert at resolving database column mapping ambiguities."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.2,
            max_tokens=500
        )
        
        logger.info(f"AI resolved {len(ambiguous_pairs)} ambiguous mappings")
        return {"ai_resolutions": response.choices[0].message.content}
    
    except Exception as e:
        logger.error(f"Failed to resolve ambiguous mappings: {e}")
        return {}


def get_ai_batch_file_to_source_mapping(
    source_columns: List[str],
    file_columns_batch: List[str],
    file_samples: Dict[str, List[str]] = None
) -> Dict[str, Dict[str, Any]]:
    """Ask Azure OpenAI in a single call to map multiple file columns to best source columns.

    Returns a dict: {file_col: {"source_match": str, "confidence": float, "reasoning": str, "inferred_type": str}}
    """
    client = _get_client()
    if not AZURE_AVAILABLE or client is None:
        return {}

    try:
        # Build prompt listing columns and small samples
        file_blocks = []
        for fc in file_columns_batch:
            samples = _format_samples_preview(file_samples.get(fc, []), max_items=5) if file_samples else "(no samples)"
            inferred = _infer_simple_type(file_samples.get(fc, [])[:20]) if file_samples and fc in file_samples else "unknown"
            file_blocks.append(f"- {fc} (type hint: {inferred}) Samples: {samples}")

        prompt = f"""You are a database mapping assistant. Given the list of standard source schema columns and the following file columns (with sample values), map each file column to the best matching source column.

Source columns:
{chr(10).join([f'- {s}' for s in source_columns])}

File columns to map:
{chr(10).join(file_blocks)}

For each file column, output a single line in this exact format:
<file_column> -> <best_source_column> (confidence: XX%)

If no good match exists, respond with:
<file_column> -> [No Match] (confidence: 0%)

Keep answers terse and one line per file column."""

        response = client.chat.completions.create(
            model=AZURE_OPENAI_DEPLOYMENT_NAME,
            messages=[
                {"role": "system", "content": "You are an expert at mapping file column names to a canonical schema."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.2,
            max_tokens=800
        )

        text = response.choices[0].message.content

        results = {}
        # Parse lines like: ColumnName -> SourceColumn (confidence: 85%)
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            m = re.match(r"^(?P<file>.+?)\s*->\s*(?P<source>.+?)\s*\(confidence:\s*(?P<conf>\d+)%\)", line, flags=re.IGNORECASE)
            if m:
                fc = m.group('file').strip()
                src = m.group('source').strip()
                try:
                    conf = int(m.group('conf'))
                except Exception:
                    conf = 0
                inferred = _infer_simple_type(file_samples.get(fc, [])[:20]) if file_samples and fc in file_samples else "unknown"
                results[fc] = {
                    "source_match": src if src != '[No Match]' else None,
                    "confidence": conf,
                    "reasoning": line,
                    "inferred_type": inferred
                }
            else:
                # Fallback: try to split on '->' and extract digits
                if '->' in line:
                    parts = [p.strip() for p in line.split('->', 1)]
                    fc = parts[0]
                    rest = parts[1]
                    conf_m = re.search(r"(\d+)%", rest)
                    conf = int(conf_m.group(1)) if conf_m else 0
                    src = rest.split('(')[0].strip()
                    inferred = _infer_simple_type(file_samples.get(fc, [])[:20]) if file_samples and fc in file_samples else "unknown"
                    results[fc] = {
                        "source_match": src if src != '[No Match]' else None,
                        "confidence": conf,
                        "reasoning": line,
                        "inferred_type": inferred
                    }

        return results

    except Exception as e:
        logger.error(f"Batch AI mapping failed: {e}")
        return {}
