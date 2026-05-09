"""
Gemini-based agent for resolving unmapped columns.

Analyzes:
- Column names (semantic similarity)
- Data types (samples from file)
- Column purpose/meaning (inferred from name patterns)

Returns intelligent mapping suggestions.
"""
import os
import json
import logging
from typing import Dict, List, Any, Tuple
from pathlib import Path

logger = logging.getLogger(__name__)

# Try to import Gemini
try:
    import google.generativeai as genai
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False
    logger.warning("google.generativeai not installed. Gemini agent will be unavailable.")


class GeminiUnmappedAgent:
    """Uses Gemini API to resolve unmapped columns intelligently."""

    def __init__(self, api_key: str = None):
        """
        Initialize agent with optional API key.
        
        Args:
            api_key: Gemini API key (if None, tries to read from GEMINI_API_KEY env var)
        """
        if not GEMINI_AVAILABLE:
            raise RuntimeError("google.generativeai is not installed. Install with: pip install google-generativeai")

        self.api_key = api_key or os.getenv("GEMINI_API_KEY", "")
        if not self.api_key:
            raise ValueError("GEMINI_API_KEY not provided and not in environment. Set it as parameter or env var.")

        genai.configure(api_key=self.api_key)
        # Try to use the latest available Gemini model
        # Try models in order of preference
        model_names = ["gemini-2.0-flash", "gemini-1.5-flash-latest", "gemini-1.5-pro"]
        self.model = None
        for model_name in model_names:
            try:
                logger.info(f"Attempting to initialize model: {model_name}")
                self.model = genai.GenerativeModel(model_name)
                logger.info(f"Successfully initialized model: {model_name}")
                break
            except Exception as e:
                logger.debug(f"Model {model_name} not available: {e}")
                continue
        
        if not self.model:
            # Fallback: use gemini-pro
            logger.warning("Could not initialize specified models, using gemini-pro")
            self.model = genai.GenerativeModel("gemini-pro")

    @staticmethod
    def _infer_data_type(samples: List[Any]) -> str:
        """Infer data type from samples."""
        if not samples:
            return "unknown"

        samples_str = [str(s).lower() for s in samples]

        # Check for datetime patterns
        datetime_keywords = ["date", "time", "jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"]
        if any(kw in s for s in samples_str for kw in datetime_keywords):
            return "datetime"

        # Check for numeric
        try:
            all_numeric = all(float(s) for s in samples_str if s)
            if all_numeric:
                return "numeric"
        except Exception:
            pass

        # Check for boolean/status
        status_kw = ["yes", "no", "true", "false", "active", "inactive", "open", "closed"]
        if any(s in status_kw for s in samples_str):
            return "categorical"

        return "text"

    def suggest_mappings(
        self,
        unmapped_sources: List[str],
        file_columns: List[str],
        file_metadata: Dict[str, Any],
        mapped_already: Dict[str, str]
    ) -> Dict[str, Dict[str, Any]]:
        """
        Use Gemini to suggest mappings for unmapped source columns.

        Args:
            unmapped_sources: List of source column names without mappings
            file_columns: All available file column names
            file_metadata: File metadata with column samples
            mapped_already: Already-mapped {source: file_column} pairs

        Returns:
            {
                "source_col": {
                    "suggested_file_column": str,
                    "confidence": float (0-100),
                    "reasoning": str
                },
                ...
            }
        """
        if not unmapped_sources:
            return {}

        # Build context about file columns
        file_col_info = []
        for fc in file_columns:
            if fc in mapped_already.values():
                continue  # Skip already used columns
            samples = file_metadata.get("column_samples", {}).get(fc, [])[:3]
            data_type = self._infer_data_type(samples)
            file_col_info.append({
                "name": fc,
                "data_type": data_type,
                "samples": samples
            })

        # Build prompt
        prompt = self._build_prompt(unmapped_sources, file_col_info, mapped_already)

        # Call Gemini
        try:
            response = self.model.generate_content(prompt)
            result = self._parse_response(response.text, unmapped_sources, file_col_info)
            return result
        except Exception as e:
            logger.error(f"Gemini suggestion error: {e}")
            return {}

    @staticmethod
    def _build_prompt(
        unmapped_sources: List[str],
        file_col_info: List[Dict[str, Any]],
        mapped_already: Dict[str, str]
    ) -> str:
        """Build the prompt for Gemini."""
        prompt = f"""You are an expert data analyst helping to map source column names to file columns.

TASK: For each source column below, suggest the best matching file column from those available.
Consider: column name similarity, data type compatibility, and semantic meaning.

AVAILABLE FILE COLUMNS:
"""
        for info in file_col_info:
            prompt += f"\n- {info['name']}"
            prompt += f" (type: {info['data_type']})"
            if info['samples']:
                prompt += f" samples: {info['samples'][:2]}"

        prompt += "\n\nALREADY MAPPED:"
        for src, tgt in mapped_already.items():
            prompt += f"\n- {src} -> {tgt}"

        prompt += "\n\nUNMAPPED SOURCE COLUMNS TO RESOLVE:"
        for src in unmapped_sources:
            prompt += f"\n- {src}"

        prompt += """

RESPOND ONLY with a JSON object, no markdown or extra text. Format:
{
  "source_column_name": {
    "suggested_file_column": "file_col_name or null",
    "confidence": 85,
    "reasoning": "brief explanation"
  },
  ...
}

Example:
{
  "Incident ID": {
    "suggested_file_column": "Number",
    "confidence": 95,
    "reasoning": "Incident ID matches Number column; both are unique identifiers"
  },
  "Service Month": {
    "suggested_file_column": null,
    "confidence": 30,
    "reasoning": "No clear match; consider manual mapping"
  }
}
"""
        return prompt

    @staticmethod
    def _parse_response(response_text: str, unmapped: List[str], file_cols: List[Dict]) -> Dict:
        """Parse Gemini response into structured format."""
        try:
            # Extract JSON from response
            import re
            json_match = re.search(r"\{.*\}", response_text, re.DOTALL)
            if not json_match:
                logger.warning("No JSON found in Gemini response")
                return {}

            json_str = json_match.group(0)
            data = json.loads(json_str)

            # Validate and normalize
            result = {}
            file_col_names = set(c["name"] for c in file_cols)

            for src in unmapped:
                if src in data:
                    suggestion = data[src]
                    suggested = suggestion.get("suggested_file_column")
                    confidence = suggestion.get("confidence", 0)

                    # Validate suggested column exists
                    if suggested and suggested not in file_col_names:
                        logger.warning(f"Gemini suggested non-existent column: {suggested}")
                        suggested = None
                        confidence = 0

                    result[src] = {
                        "suggested_file_column": suggested,
                        "confidence": float(confidence),
                        "reasoning": suggestion.get("reasoning", "")
                    }

            return result
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse Gemini JSON response: {e}")
            logger.debug(f"Response text: {response_text[:500]}")
            return {}
        except Exception as e:
            logger.error(f"Unexpected error parsing Gemini response: {e}")
            return {}


def get_gemini_agent(api_key: str = None) -> GeminiUnmappedAgent:
    """Factory for creating a Gemini agent."""
    return GeminiUnmappedAgent(api_key=api_key)
