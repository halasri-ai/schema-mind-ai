"""
Multi-Schema Column Matching Streamlit App

- Azure OpenAI powered with intelligent column mapping
- File-based caching for repeated uploads  
- Source schemas are loaded from `streamlit_app/source_schemas` folder
- All available schemas are used for matching
- Creates separate output files for each matched schema
- Uses `mapping.function_app.process_mapping` for mapping
"""
import sys
from pathlib import Path

# Add parent directory to path so we can import mapping module
sys.path.insert(0, str(Path(__file__).parent.parent))

import streamlit as st
import pandas as pd
import os
import json
import logging
import tempfile
import time
from difflib import SequenceMatcher
from typing import Dict, Any, List
from io import BytesIO
import zipfile
from dotenv import load_dotenv

# Load environment variables
load_dotenv(Path(__file__).parent.parent / ".env")

# Local mapping function
from mapping.function_app import process_mapping, load_all_schemas
from mapping.mapping_engine.sqlite_logger import log_mapping_change, get_all_logs, get_stats
from mapping.mapping_engine.schema_detector import detect_best_schema
from mapping.mapping_engine.mapping_memory import (
    save_manual_mapping, get_suggested_mapping, get_memory_stats, 
    save_file_mapping, get_mapping_pair_frequency
)
from mapping.mapping_engine.azure_ai import (
    AZURE_AVAILABLE,
    get_ai_mapping_suggestion,
    get_ai_batch_file_to_source_mapping,
)
from mapping.mapping_engine.file_cache import (
    calculate_file_hash, get_cached_file_mappings, save_file_mapping_cache,
    file_exists_in_cache, get_cache_stats
)

# Basic logger
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("streamlit_app")

# Constants
PAGE_TITLE = "Multi-Schema Column Matching"
PAGE_ICON = ":mag_right:"
LAYOUT = "wide"

# Ensure source schemas folder exists
SCHEMA_DIR = Path(__file__).parent / "source_schemas"
SCHEMA_DIR.mkdir(parents=True, exist_ok=True)

st.set_page_config(page_title=PAGE_TITLE, page_icon=PAGE_ICON, layout=LAYOUT)

st.title("Multi-Schema Column Matching")
st.caption("Matches file columns against ALL available standard schemas. Place source schema files (CSV/XLSX) in the `streamlit_app/source_schemas` folder.")

# Keep track of unmapped expander open state and accepted mappings
if "unmapped_expanded" not in st.session_state:
    st.session_state["unmapped_expanded"] = True
if "accepted_mappings" not in st.session_state:
    st.session_state["accepted_mappings"] = {}  # {schema_name: {source: {target, confidence, type, alternatives}}}

def _keep_unmapped_open():
    st.session_state["unmapped_expanded"] = True


def _get_memory_suggestion_hint(source_col: str) -> str:
    """Get a memory suggestion hint for a source column."""
    suggestions = get_suggested_mapping(source_col, limit=1)
    if suggestions:
        top = suggestions[0]
        count = top.get("usage_count", 0)
        return f"💾 Previously mapped to: {top['target_column']} ({count}x)"
    return ""


def _log_mapping_change(source_col: str, file_col: str, mapping_type: str, confidence: float = 0):
    """Log mapping changes to SQLite database and optionally save to memory."""
    import datetime
    timestamp = datetime.datetime.now().isoformat()
    # Log to both terminal and SQLite
    logger.info(f"MAPPING CHANGE | Timestamp: {timestamp} | Source: {source_col} | Target: {file_col} | Type: {mapping_type} | Confidence: {confidence}%")
    # Get file/sheet context from session state if available
    file_name = st.session_state.get("uploaded_file_name", None)
    sheet_name = st.session_state.get("_current_sheet_name", None)
    log_mapping_change(source_col, file_col, mapping_type, confidence, file_name, sheet_name)
    
    # Save to mapping memory if it's a manual mapping and has a valid target
    if file_col and file_col != "[Not Mapped]":
        if "manual" in mapping_type.lower() or "remapped" in mapping_type.lower():
            success = save_manual_mapping(
                source_column=source_col,
                target_column=file_col,
                file_type="excel" if file_name and file_name.endswith(".xlsx") else "csv",
                confidence_score=confidence,
                user_confirmed=True
            )
            if success:
                logger.info(f"✓ SAVED TO MEMORY | {source_col} → {file_col}")
            else:
                logger.warning(f"✗ FAILED TO SAVE TO MEMORY | {source_col} → {file_col}")
    else:
        if file_col == "[Not Mapped]" and "manual" in mapping_type.lower():
            logger.info(f"ℹ UNMAPPED | {source_col} (removed mapping to memory)")

# Sidebar: Mapping Memory Statistics
st.sidebar.markdown("---")
st.sidebar.subheader("📚 Mapping Memory")

try:
    memory_stats = get_memory_stats()
    if memory_stats.get("total_manual_mappings", 0) > 0:
        st.sidebar.metric("Saved Mappings", memory_stats["total_manual_mappings"])
        st.sidebar.metric("Files Processed", memory_stats["total_files_processed"])
        st.sidebar.metric("Success Rate", f"{memory_stats['average_success_rate']:.1f}%")
    else:
        st.sidebar.info("No mappings saved yet. Manually map unmapped columns above to build memory.")
except Exception as e:
    st.sidebar.warning(f"Memory stats unavailable: {str(e)[:50]}")

# Sidebar: Azure AI Status
st.sidebar.markdown("---")
st.sidebar.subheader("🤖 AI Support")
if AZURE_AVAILABLE:
    st.sidebar.success("Azure OpenAI: ✓ Active")
    try:
        cache_stats = get_cache_stats()
        st.sidebar.metric("Files Cached", cache_stats.get("total_files_cached", 0))
        st.sidebar.metric("Schema Mappings", cache_stats.get("total_schema_mappings", 0))
        st.sidebar.metric("Cache Hits", cache_stats.get("total_uploads_from_cache", 0))
    except:
        pass
else:
    st.sidebar.warning("Azure OpenAI: Not configured. Set environment variables to enable.")
    st.sidebar.info("Fill in your Azure credentials in the `.env` file.")

st.sidebar.markdown("---")

# Initialize session variables
if "schemas_dict" not in st.session_state:
    st.session_state.schemas_dict = {}
if "mapping_result" not in st.session_state:
    st.session_state.mapping_result = None

st.write("---")

# File uploader for data file to map
uploaded_file = st.file_uploader("Upload Excel file to match with standard schemas", type=["xlsx", "xls", "xlsm"])

if uploaded_file:
    # Check if file changed
    current_file = st.session_state.get("_current_uploaded_file")
    if current_file != uploaded_file.name:
        st.session_state["_current_uploaded_file"] = uploaded_file.name
        st.session_state.mapping_result = None  # Reset mapping for new file
    
    # Save to temp file
    temp_dir = tempfile.gettempdir()
    temp_path = os.path.join(temp_dir, uploaded_file.name)
    with open(temp_path, "wb") as f:
        f.write(uploaded_file.getbuffer())

    st.info(f"📁 Processing file: {uploaded_file.name}")
    st.session_state["uploaded_file_name"] = uploaded_file.name
    
    # Calculate file hash for caching
    file_size = len(uploaded_file.getbuffer())
    file_hash = calculate_file_hash(temp_path, uploaded_file.name, file_size)

    # Read all sheets and build file_metadata
    try:
        wb = pd.read_excel(temp_path, sheet_name=None)
    except Exception as e:
        st.error(f"Failed to read Excel file: {e}")
        st.stop()

    sheets_meta = {}
    for sheet_name, df in wb.items():
        cols = list(df.columns)
        samples = {c: df[c].dropna().astype(str).head(5).tolist() for c in cols}
        sheets_meta[sheet_name] = {"columns": cols, "column_samples": samples}

    file_metadata = {"file_name": uploaded_file.name, "sheets": sheets_meta}

    # Load ALL available schemas
    st.info("🔍 Loading all available standard schemas...")
    
    if not st.session_state.schemas_dict:
        schemas_dict = load_all_schemas(SCHEMA_DIR)
        if not schemas_dict:
            st.error(f"No source schema files found in {SCHEMA_DIR}. Please add CSV/XLSX schema files to this folder.")
            st.stop()
        st.session_state.schemas_dict = schemas_dict
        st.success(f"✓ Loaded {len(schemas_dict)} standard schema(s)")
        
        # Show loaded schemas
        schema_list = ", ".join(list(schemas_dict.keys()))
        st.info(f"📊 Available schemas: {schema_list}")
    else:
        schemas_dict = st.session_state.schemas_dict
    
    # Check if file is in cache
    cache_hit = False
    if file_hash and file_exists_in_cache(file_hash):
        st.info(f"🎯 Cache Hit! Found previous mappings for this file.")
        cached_data = get_cached_file_mappings(file_hash)
        if cached_data.get("found"):
            st.success(f"📋 Previously uploaded {cached_data.get('upload_count', 1)} time(s)")
            cache_hit = True
            
            # Auto-apply cached mappings
            mapping_result = {
                "file_name": uploaded_file.name,
                "schemas": list(schemas_dict.keys()),
                "sheets": {},
                "cached": True,
                "cached_at": cached_data.get('last_seen', 'N/A')
            }
            
            # Build mapping result from cache
            for schema_name, cached_mappings in cached_data.get("schemas", {}).items():
                mapping_result["sheets"][sheet_name] = {
                    "sheet_name": sheet_name,
                    "file_columns": list(file_metadata.get("sheets", {}).values())[0].get("columns", []),
                    "schema_mappings": {
                        schema_name: {
                            "mappings": cached_mappings,
                            "sheet_name": sheet_name
                        }
                    }
                }
            
            st.session_state.mapping_result = mapping_result
            logger.info(f"✓ Applied cached mappings for {uploaded_file.name}")
    
    # If not in cache, process mapping
    if not cache_hit:
        st.info("⚙️ Matching file columns against all standard schemas...")
        
        with st.spinner("Running multi-schema matching..."):
            try:
                mapping_result = process_mapping(
                    source_schema=[],  # Not used in multi-schema mode
                    file_metadata=file_metadata,
                    config={"agent_enabled": False},
                    schemas_dict=schemas_dict
                )
                st.session_state.mapping_result = mapping_result
            except Exception as e:
                st.error(f"Mapping failed: {e}")
                logger.exception("Mapping error")
                st.stop()

    if mapping_result and "error" not in mapping_result:
        st.success(f"✓ Matching complete for {len(sheets_meta)} sheet(s)")
    
        # --- MULTI-SCHEMA RESULTS ANALYSIS ---
        st.subheader("Matching Summary by Schema")
        
        # Analyze results across all schemas
        # Separate mappings by confidence level: auto (≥80%), review (70-80%), manual (<70%)
        schema_stats = {}
        schema_review_mappings = {}  # For human review
        
        for schema_name in schemas_dict.keys():
            schema_stats[schema_name] = {
                "matched_columns": [],
                "file_columns_matched": [],
                "mappings": {}
            }
            schema_review_mappings[schema_name] = {
                "review": [],  # confidence 70-80% or decision_type="review"
                "manual": []   # confidence < 70% or decision_type="manual"
            }
        
        for sheet_name, sheet_result in mapping_result.get("sheets", {}).items():
            schema_mappings = sheet_result.get("schema_mappings", {})
            
            for schema_name, schema_result in schema_mappings.items():
                mappings = schema_result.get("mappings", {})
                for src_col, info in mappings.items():
                    # Handle both string values (just column name) and dict values (with metadata)
                    if isinstance(info, str):
                        mapped_to = info
                        confidence = 85  # Default high confidence for cached/existing mappings
                        decision_type = "cached"
                        alternatives = []
                    else:
                        mapped_to = info.get("mapped_file_column", "")
                        confidence = info.get("confidence_score", 0)
                        decision_type = info.get("decision_type", "manual")
                        alternatives = info.get("alternatives", [])
                    
                    # Only auto-apply if confidence >= 80% AND decision_type == "auto"
                    if mapped_to and confidence >= 80 and decision_type in ["auto", "cached"]:
                        schema_stats[schema_name]["matched_columns"].append(src_col)
                        schema_stats[schema_name]["file_columns_matched"].append(mapped_to)
                        schema_stats[schema_name]["mappings"][src_col] = mapped_to
                    
                    # Collect mappings for human review (70-80%) or manual (<70%)
                    elif mapped_to:
                        if confidence >= 70:  # Review needed
                            schema_review_mappings[schema_name]["review"].append({
                                "source": src_col,
                                "target": mapped_to,
                                "confidence": confidence,
                                "decision_type": decision_type,
                                "alternatives": alternatives
                            })
                        else:  # Manual mapping needed
                            schema_review_mappings[schema_name]["manual"].append({
                                "source": src_col,
                                "target": mapped_to,
                                "confidence": confidence,
                                "decision_type": decision_type,
                                "alternatives": info.get("alternatives", [])
                            })
        
        # Display schema statistics
        summary_data = []
        for schema_name, stats in schema_stats.items():
            matched = len(set(stats["file_columns_matched"]))
            review_count = len(schema_review_mappings[schema_name]["review"])
            manual_count = len(schema_review_mappings[schema_name]["manual"])
            
            summary_data.append({
                "Schema Name": schema_name,
                "Auto-Matched (≥80%)": matched,
                "Review (70-80%)": review_count,
                "Manual (<70%)": manual_count,
                "Total": len(stats["matched_columns"]) + review_count + manual_count
            })
        st.dataframe(pd.DataFrame(summary_data), use_container_width=True)
        
        
        st.write("---")
        
        # --- AI MAPPING FOR UNMAPPED AND REVIEW COLUMNS (Optional) ---
        # Initialize session state for AI toggle
        if "enable_ai_suggestions" not in st.session_state:
            st.session_state.enable_ai_suggestions = False
        
        # Show AI toggle button
        col1, col2 = st.columns([2, 1])
        with col1:
            st.subheader("🤖 AI Suggestions for Unmapped Columns")
        with col2:
            if st.button("Enable AI" if not st.session_state.enable_ai_suggestions else "Disable AI", 
                        use_container_width=True,
                        key="toggle_ai_button"):
                st.session_state.enable_ai_suggestions = not st.session_state.enable_ai_suggestions
                st.rerun()
        
        # Only run AI if user explicitly enabled it
        if st.session_state.enable_ai_suggestions and AZURE_AVAILABLE:
            ai_suggestions = {}
            ai_timeout_exceeded = False
            ai_start_time = time.time()
            AI_TIMEOUT_SECONDS = 120
            
            for schema_name, stats in schema_stats.items():
                file_columns = list(file_metadata.get("sheets", {}).values())[0].get("columns", [])
                matched_file_columns = set(stats.get("file_columns_matched", []))
                unmapped = [col for col in file_columns if col not in matched_file_columns]
                source_columns = list(schemas_dict[schema_name])
                if unmapped and len(unmapped) > 0:
                    ai_suggestions[schema_name] = {}
                    # collect column_samples for this file (same sheet used earlier)
                    column_samples = list(file_metadata.get("sheets", {}).values())[0].get("column_samples", {})
                    ai_auto_applied = {}
                    
                    # Use batching to reduce API calls: chunk unmapped columns into groups
                    BATCH_SIZE = 5
                    with st.spinner(f"🔍 Analyzing unmapped columns for {schema_name}... (batching, timeout {AI_TIMEOUT_SECONDS}s)"):
                        for i in range(0, len(unmapped), BATCH_SIZE):
                            batch = unmapped[i:i+BATCH_SIZE]
                            # Check timeout before each batch
                            if time.time() - ai_start_time > AI_TIMEOUT_SECONDS:
                                ai_timeout_exceeded = True
                                logger.warning(f"AI analysis timeout reached after {AI_TIMEOUT_SECONDS} seconds")
                                break

                            try:
                                batch_results = get_ai_batch_file_to_source_mapping(
                                    source_columns=source_columns,
                                    file_columns_batch=batch,
                                    file_samples=column_samples
                                )

                                for file_col in batch:
                                    suggestion = batch_results.get(file_col)
                                    if not suggestion:
                                        continue

                                    best_source = suggestion.get("source_match")
                                    best_confidence = suggestion.get("confidence", 0)
                                    best_suggestion = suggestion

                                    # Auto-apply high-confidence mappings (>=80%) but verify name similarity/type before applying
                                    if best_source and best_confidence >= 80:
                                        inferred_type = suggestion.get("inferred_type", "unknown")
                                        name_similarity = SequenceMatcher(None, str(best_source).lower(), str(file_col).lower()).ratio()

                                        if name_similarity >= 0.5 or (inferred_type != "unknown"):
                                            if schema_name not in st.session_state["accepted_mappings"]:
                                                st.session_state["accepted_mappings"][schema_name] = {}
                                            st.session_state["accepted_mappings"][schema_name][best_source] = {
                                                "target": file_col,
                                                "confidence": best_confidence,
                                                "type": "ai_auto",
                                                "inferred_type": inferred_type,
                                                "source": best_source
                                            }
                                            schema_stats[schema_name]["matched_columns"].append(best_source)
                                            schema_stats[schema_name]["file_columns_matched"].append(file_col)
                                            schema_stats[schema_name]["mappings"][best_source] = file_col
                                            ai_auto_applied[file_col] = {
                                                "source_match": best_source,
                                                "confidence": best_confidence,
                                                "inferred_type": inferred_type,
                                                "name_similarity": round(name_similarity, 2)
                                            }
                                        else:
                                            ai_suggestions[schema_name][file_col] = {
                                                "source_match": best_source,
                                                "confidence": best_confidence,
                                                "reasoning": f"High AI confidence but low name similarity ({name_similarity:.2f}) - needs review",
                                                "inferred_type": inferred_type,
                                                "name_similarity": round(name_similarity, 2)
                                            }

                                    # Keep lower-confidence suggestions for review
                                    elif best_source and best_confidence > 50:
                                        ai_suggestions[schema_name][file_col] = {
                                            "source_match": best_source,
                                            "confidence": best_confidence,
                                            "reasoning": suggestion.get("reasoning", ""),
                                            "inferred_type": suggestion.get("inferred_type", "unknown")
                                        }
                            except Exception as e:
                                logger.warning(f"AI batch analysis failed for batch starting at {i}: {e}")

                    # Display any auto-applied AI mappings first (with undo)
                    if ai_auto_applied:
                        with st.expander(f"🤖 AI Auto-Mapped (>=80%) - {schema_name} ({len(ai_auto_applied)})", expanded=True):
                            st.info("These mappings were auto-applied by AI. Review or undo below:")
                            for file_col, applied in ai_auto_applied.items():
                                col1, col2, col3 = st.columns([3, 1, 1])
                                with col1:
                                    st.write(f"**File Column:** `{file_col}` → **Source:** `{applied['source_match']}`")
                                with col2:
                                    st.write(f"Type: {applied.get('inferred_type', 'unknown')}")
                                with col3:
                                    if st.button("Undo", key=f"undo_ai_auto_{schema_name}_{file_col}"):
                                        # Remove from accepted mappings and schema stats
                                        if schema_name in st.session_state["accepted_mappings"] and applied['source_match'] in st.session_state["accepted_mappings"][schema_name]:
                                            st.session_state["accepted_mappings"][schema_name].pop(applied['source_match'], None)
                                        try:
                                            schema_stats[schema_name]["matched_columns"].remove(applied['source_match'])
                                        except Exception:
                                            pass
                                        try:
                                            schema_stats[schema_name]["file_columns_matched"].remove(file_col)
                                        except Exception:
                                            pass
                                        st.success("AI auto-mapping undone")
                                        st.rerun()
            
            # Show timeout warning if exceeded
            if ai_timeout_exceeded:
                st.warning(f"⏱️ AI analysis limited by 30-second timeout. Consider running again for more AI suggestions.")
            
            
            # Display AI suggestions
            if ai_suggestions and any(ai_suggestions.values()):
                for schema_name, suggestions in ai_suggestions.items():
                    if suggestions:
                        with st.expander(f"💡 {schema_name} - AI Suggestions ({len(suggestions)} unmapped column(s))", expanded=True):
                            st.info("AI has identified potential matches for unmapped columns. Review and accept if applicable:")
                            for file_col, suggestion in suggestions.items():
                                col1, col2, col3, col4 = st.columns([2, 2, 1, 1])
                                with col1:
                                    st.write(f"**File Column:**\n`{file_col}`")
                                with col2:
                                    st.write(f"**AI Match:**\n`{suggestion.get('source_match', 'N/A')}`")
                                with col3:
                                    st.write(f"**Confidence:**\n{suggestion.get('confidence', 0):.0f}%")
                                with col4:
                                    if st.button("✓ Accept", key=f"accept_ai_{schema_name}_{file_col}"):
                                        if schema_name not in st.session_state["accepted_mappings"]:
                                            st.session_state["accepted_mappings"][schema_name] = {}
                                        st.session_state["accepted_mappings"][schema_name][suggestion.get('source_match')] = {
                                            "target": file_col,
                                            "confidence": suggestion.get("confidence", 0),
                                            "type": "ai_matched",
                                            "source": suggestion.get('source_match')
                                        }
                                        schema_stats[schema_name]["matched_columns"].append(suggestion.get('source_match'))
                                        schema_stats[schema_name]["file_columns_matched"].append(file_col)
                                        st.success("✓ AI suggestion accepted!")
                                        st.rerun()
        
        st.write("---")
        
        # Display review and manual mappings
        st.subheader("🔍 Human Review Required")
        
        has_review_items = any(
            schema_review_mappings[schema_name]["review"] 
            for schema_name in schema_review_mappings
        )
        has_manual_items = any(
            schema_review_mappings[schema_name]["manual"] 
            for schema_name in schema_review_mappings
        )
        
        if has_review_items or has_manual_items:
            for schema_name, review_data in schema_review_mappings.items():
                review_list = review_data.get("review", [])
                manual_list = review_data.get("manual", [])
                
                # Review mappings (70-80%)
                if review_list:
                    with st.expander(f"⚠️ {schema_name} - Confidence 70-80% ({len(review_list)} to verify)", expanded=True):
                        st.write(f"These mappings have 70-80% confidence. Please verify before accepting:")
                        for mapping in review_list:
                            col1, col2, col3, col4, col5 = st.columns([2, 2, 1, 1.5, 0.5])
                            with col1:
                                st.write(f"**{mapping['source']}**")
                            with col2:
                                st.write(f"→ {mapping['target']}")
                            with col3:
                                st.write(f"{mapping['confidence']:.1f}%")
                            with col4:
                                if mapping['alternatives']:
                                    alt_text = "\n".join([f"• {alt}" for alt in mapping['alternatives'][:2]])
                                    st.caption(f"**Alternatives:**\n{alt_text}")
                            with col5:
                                if st.button("✓", key=f"accept_review_{schema_name}_{mapping['source']}", help="Accept this mapping"):
                                    if schema_name not in st.session_state["accepted_mappings"]:
                                        st.session_state["accepted_mappings"][schema_name] = {}
                                    st.session_state["accepted_mappings"][schema_name][mapping['source']] = {
                                        "target": mapping['target'],
                                        "confidence": mapping['confidence'],
                                        "type": "ai_review",
                                        "alternatives": mapping['alternatives']
                                    }
                                    schema_stats[schema_name]["matched_columns"].append(mapping['source'])
                                    schema_stats[schema_name]["file_columns_matched"].append(mapping['target'])
                                    schema_stats[schema_name]["mappings"][mapping['source']] = mapping['target']
                                    _log_mapping_change(mapping['source'], mapping['target'], "ai_suggested_review_accepted", mapping['confidence'])
                                    # Save to memory for future use
                                    save_manual_mapping(
                                        source_column=mapping['source'],
                                        target_column=mapping['target'],
                                        file_type="excel" if uploaded_file.name.endswith(".xlsx") else "csv",
                                        confidence_score=mapping['confidence'],
                                        user_confirmed=True
                                    )
                                    st.rerun()
                
                # Manual mappings (<70%)
                if manual_list:
                    with st.expander(f"❌ {schema_name} - Confidence < 70% ({len(manual_list)} needs mapping)", expanded=st.session_state.get("unmapped_expanded", True)):
                        st.write(f"These mappings have very low confidence (< 70%) and need your decision:")
                        for mapping in manual_list:
                            col1, col2, col3, col4, col5 = st.columns([2, 2, 1, 1.5, 0.5])
                            with col1:
                                st.write(f"**{mapping['source']}**")
                            with col2:
                                st.write(f"→ {mapping['target']} (suggested)")
                            with col3:
                                st.write(f"{mapping['confidence']:.1f}%")
                            with col4:
                                if mapping['alternatives']:
                                    alt_text = "\n".join([f"• {alt}" for alt in mapping['alternatives'][:2]])
                                    st.caption(f"**Alternatives:**\n{alt_text}")
                            with col5:
                                if st.button("✓", key=f"accept_manual_{schema_name}_{mapping['source']}", help="Accept this mapping"):
                                    if schema_name not in st.session_state["accepted_mappings"]:
                                        st.session_state["accepted_mappings"][schema_name] = {}
                                    st.session_state["accepted_mappings"][schema_name][mapping['source']] = {
                                        "target": mapping['target'],
                                        "confidence": mapping['confidence'],
                                        "type": "manual",
                                        "alternatives": mapping['alternatives']
                                    }
                                    schema_stats[schema_name]["matched_columns"].append(mapping['source'])
                                    schema_stats[schema_name]["file_columns_matched"].append(mapping['target'])
                                    schema_stats[schema_name]["mappings"][mapping['source']] = mapping['target']
                                    _log_mapping_change(mapping['source'], mapping['target'], "manual_remapped_from_low_confidence", mapping['confidence'])
                                    # Save to memory for future use
                                    save_manual_mapping(
                                        source_column=mapping['source'],
                                        target_column=mapping['target'],
                                        file_type="excel" if uploaded_file.name.endswith(".xlsx") else "csv",
                                        confidence_score=mapping['confidence'],
                                        user_confirmed=True
                                    )
                                    st.rerun()
        else:
            st.success("✓ All high-confidence mappings completed! No human review needed.")
        
        st.write("---")
        
        # Display accepted mappings with full details
        st.subheader("✅ Accepted Mappings")
        
        has_accepted = any(
            st.session_state["accepted_mappings"].get(schema_name, {}) 
            for schema_name in st.session_state["accepted_mappings"]
        )
        
        if has_accepted:
            for schema_name in st.session_state["accepted_mappings"]:
                accepted_in_schema = st.session_state["accepted_mappings"][schema_name]
                if accepted_in_schema:
                    with st.expander(f"✓ {schema_name} - {len(accepted_in_schema)} Accepted", expanded=True):
                        for source, mapping_info in accepted_in_schema.items():
                            # Support both string mappings and dict mappings
                            if isinstance(mapping_info, str):
                                target = mapping_info
                                confidence = 85
                                mtype = "cached"
                                alternatives = []
                                inferred_type = "unknown"
                            else:
                                target = mapping_info.get("target", "[Not Mapped]")
                                confidence = mapping_info.get("confidence", 0)
                                mtype = mapping_info.get("type", "manual")
                                alternatives = mapping_info.get("alternatives", []) or []
                                inferred_type = mapping_info.get("inferred_type", "unknown")

                            col1, col2, col3, col4, col5, col6 = st.columns([1.5, 1.5, 0.8, 1, 1.5, 1])
                            with col1:
                                st.write(f"**{source}**")
                            with col2:
                                st.write(f"→ {target}")
                            with col3:
                                st.metric("Conf", f"{confidence:.0f}%")
                            with col4:
                                type_badge = str(mtype).replace("_", " ").title()
                                # Show inferred type when available
                                if inferred_type and inferred_type != "unknown":
                                    st.caption(f"🏷️ {type_badge} • {inferred_type}")
                                else:
                                    st.caption(f"🏷️ {type_badge}")
                            with col5:
                                if alternatives:
                                    alt_text = ", ".join(alternatives[:2])
                                    st.caption(f"Alt: {alt_text}")
                            with col6:
                                if st.button("❌", key=f"remove_{schema_name}_{source}", help="Remove this mapping"):
                                    del st.session_state["accepted_mappings"][schema_name][source]
                                    st.rerun()
        else:
            st.info("No mappings accepted yet. Accept mappings from the review section above.")
        
        st.write("---")
        
        # Save final mappings to cache for future uploads
        if file_hash:
            # derive file columns from file_metadata (first sheet)
            try:
                file_columns_list = list(file_metadata.get("sheets", {}).values())[0].get("columns", [])
            except Exception:
                file_columns_list = []

            for schema_name, stats in schema_stats.items():
                if stats["mappings"]:
                    try:
                        # Save to file cache for fast retrieval on future uploads
                        save_file_mapping_cache(
                            file_hash=file_hash,
                            file_name=uploaded_file.name,
                            file_size=file_size,
                            file_columns=list(file_columns_list),
                            schema_name=schema_name,
                            mappings=stats["mappings"]
                        )
                        logger.info(f"✓ Cached mappings for {schema_name}")
                    except Exception as e:
                        logger.warning(f"Failed to cache mappings: {e}")
            
            st.success("💾 Mappings saved to cache for future uploads!")
        
        st.write("---")
        st.subheader("📥 Download Results")
        
        # Read all sheets
        try:
            all_sheets = pd.read_excel(temp_path, sheet_name=None)
        except Exception as e:
            st.error(f"Failed to read sheets: {e}")
            all_sheets = {}
        
        # Create a dictionary to store DataFrames for each schema
        schema_outputs = {}
        
        for schema_name, stats in schema_stats.items():
            matched_cols = set(stats["file_columns_matched"])
            
            # Only create output if there are matched columns
            if matched_cols:
                # Combine data from all sheets that have matched columns
                combined_df = None
                
                for sheet_name, sheet_df in all_sheets.items():
                    sheet_cols = set(sheet_df.columns)
                    
                    # Get columns that exist in this sheet AND are matched
                    actual_matched = matched_cols & sheet_cols
                    
                    if actual_matched:
                        # Create mapping for column renaming
                        file_col_to_standard = {}
                        for src_col, file_col in stats["mappings"].items():
                            if file_col in sheet_cols:
                                file_col_to_standard[file_col] = src_col
                        
                        # Select columns: matched + unmatched in this sheet
                        cols_to_include = list(actual_matched)
                        unmatched_in_sheet = sheet_cols - matched_cols
                        cols_to_include.extend(unmatched_in_sheet)
                        
                        # Filter to only existing columns
                        cols_to_include = [c for c in cols_to_include if c in sheet_cols]
                        
                        # Create output DataFrame
                        output_df = sheet_df[cols_to_include].copy()
                        
                        # Rename matched columns to standard names
                        rename_map = {}
                        for file_col, source_col in file_col_to_standard.items():
                            if file_col in output_df.columns:
                                rename_map[file_col] = source_col
                        
                        output_df = output_df.rename(columns=rename_map)
                        
                        # Combine with previous sheets
                        if combined_df is None:
                            combined_df = output_df
                        else:
                            # Append data from this sheet
                            combined_df = pd.concat([combined_df, output_df], ignore_index=True)
                
                if combined_df is not None:
                    schema_outputs[schema_name] = combined_df
        
        # Get all file columns for reference
        file_columns = set()
        for sheet_df in all_sheets.values():
            file_columns.update(sheet_df.columns)
        
        # Create multiple download options
        if schema_outputs:
            # Option 1: Download individual files

            st.write("**Option 1: Download individual matched schemas**")
            cols = st.columns(len(schema_outputs))
            
            for idx, (schema_name, output_df) in enumerate(schema_outputs.items()):
                with cols[idx]:
                    csv_buffer = BytesIO()
                    output_df.to_csv(csv_buffer, index=False)
                    csv_buffer.seek(0)
                    
                    st.download_button(
                        label=f"📥 {schema_name}",
                        data=csv_buffer.getvalue(),
                        file_name=f"{schema_name}_{uploaded_file.name.rsplit('.', 1)[0]}.csv",
                        mime="text/csv",
                        key=f"download_{schema_name}"
                    )
            
            st.write("---")
            
            # Option 2: Download as ZIP with all files + summary
            st.write("**Option 2: Download all results as ZIP**")
            
            zip_buffer = BytesIO()
            with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
                # Add each schema output file
                for schema_name, output_df in schema_outputs.items():
                    csv_str = output_df.to_csv(index=False)
                    zip_file.writestr(
                        f"{schema_name}_{uploaded_file.name.rsplit('.', 1)[0]}.csv",
                        csv_str
                    )
                
                # Create and add summary file
                summary_lines = []
                summary_lines.append(f"File Matching Summary")
                summary_lines.append(f"===================")
                summary_lines.append(f"Source File: {uploaded_file.name}")
                summary_lines.append(f"Processing Date: {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M:%S')}")
                summary_lines.append(f"Total File Columns: {len(file_columns)}")
                summary_lines.append(f"Total Schemas Matched: {len(schema_outputs)}")
                summary_lines.append("")
                summary_lines.append("Matching Results by Schema:")
                summary_lines.append("---------------------------")
                
                for schema_name, output_df in schema_outputs.items():
                    matched_cols = schema_stats[schema_name]["matched_columns"]
                    matched_count = len(matched_cols)
                    summary_lines.append(f"\n{schema_name}:")
                    summary_lines.append(f"  - Matched Columns: {matched_count}")
                    summary_lines.append(f"  - Columns Remapped To Standard: {matched_count}")
                    summary_lines.append(f"  - Unmatched Columns Included: {len(output_df.columns) - matched_count}")
                
                summary_text = "\n".join(summary_lines)
                zip_file.writestr("SUMMARY.txt", summary_text)
            
            zip_buffer.seek(0)
            st.download_button(
                label="📦 Download All as ZIP",
                data=zip_buffer.getvalue(),
                file_name=f"matched_schemas_{uploaded_file.name.rsplit('.', 1)[0]}.zip",
                mime="application/zip",
                key="download_zip"
            )
        else:
            st.warning("No columns matched to any standard schema.")
        
        st.write("---")
        
        # Initialize session state for manual mappings
        if "manual_mappings_by_schema" not in st.session_state:
            st.session_state.manual_mappings_by_schema = {}
        
        # Manual mapping for each schema separately
        st.subheader("✏️ Manual Mapping for Unmapped Columns")
        st.write("For each standard schema, manually map columns that didn't match:")
        
        total_manual_mapped = 0
        
        for schema_name, stats in schema_stats.items():
            # Initialize schema in session state if not exists
            if schema_name not in st.session_state.manual_mappings_by_schema:
                st.session_state.manual_mappings_by_schema[schema_name] = {}
            
            # Get unmapped file columns for this specific schema (excluding already manually mapped)
            matched_file_cols = set(stats["file_columns_matched"])
            manually_mapped_in_schema = set(st.session_state.manual_mappings_by_schema[schema_name].keys())
            unmapped_file_columns = (file_columns - matched_file_cols) - manually_mapped_in_schema
            
            # Get unmapped standard columns: all schema columns minus the ones already matched
            all_standard_cols = set(schemas_dict[schema_name])
            already_matched_standard = set(stats["matched_columns"])
            manually_mapped_standard = set(st.session_state.manual_mappings_by_schema[schema_name].values())
            unmapped_standard_columns = sorted(all_standard_cols - already_matched_standard - manually_mapped_standard)
            
            # Show mapped columns first
            if st.session_state.manual_mappings_by_schema[schema_name]:
                with st.expander(f"✅ {schema_name} - Manually Mapped Columns ({len(st.session_state.manual_mappings_by_schema[schema_name])})", expanded=True):
                    for file_col, std_col in st.session_state.manual_mappings_by_schema[schema_name].items():
                        col1, col2, col3, col4, col5 = st.columns([2, 2.5, 1.2, 1.2, 0.5])
                        with col1:
                            st.write(f"**{file_col}**")
                        with col2:
                            st.write(f"→ {std_col}")
                        with col3:
                            st.caption("100.0")
                        with col4:
                            st.caption("🧑 Human")
                        with col5:
                            st.caption("✓")
            
            # Show unmapped columns for mapping
            if unmapped_file_columns:
                with st.expander(f"📋 {schema_name} - Unmapped Columns ({len(unmapped_file_columns)} to map / {len(unmapped_standard_columns)} available)", expanded=True):
                    st.write(f"**Map to {schema_name} standard columns:**")
                    st.write("---")
                    
                    for unmapped_col in sorted(unmapped_file_columns):
                        col1, col2, col3 = st.columns([2, 2.5, 1])
                        
                        with col1:
                            selected_file = st.selectbox(
                                "File Column",
                                options=sorted(unmapped_file_columns),
                                index=sorted(unmapped_file_columns).index(unmapped_col) if unmapped_col in unmapped_file_columns else 0,
                                key=f"file_col_{schema_name}_{unmapped_col}",
                                label_visibility="collapsed"
                            )
                        
                        with col2:
                            selected_standard = st.selectbox(
                                f"Standard Column",
                                options=unmapped_standard_columns,
                                key=f"standard_col_{schema_name}_{unmapped_col}",
                                label_visibility="collapsed"
                            )
                        
                        with col3:
                            if selected_file and selected_standard:
                                if st.button(
                                    "✓ Accept",
                                    key=f"accept_{schema_name}_{unmapped_col}",
                                    use_container_width=True  # TODO: update to width parameter when available
                                ):
                                    # Add to manual mappings
                                    st.session_state.manual_mappings_by_schema[schema_name][selected_file] = selected_standard
                                    total_manual_mapped += 1
                                    
                                    # Save to memory immediately
                                    try:
                                        save_manual_mapping(
                                            source_column=selected_standard,
                                            target_column=selected_file,
                                            file_type="excel" if uploaded_file.name.endswith(".xlsx") else "csv",
                                            confidence_score=100.0,
                                            user_confirmed=True
                                        )
                                    except Exception as e:
                                        logger.warning(f"Failed to save mapping: {e}")
                                    
                                    st.rerun()

        
        st.write("---")
        
        # Show detailed mappings with confidence and type
        st.subheader("📊 Detailed Matching Results")
        
        for schema_name, stats in schema_stats.items():
            # Collect all mappings: auto-matched + accepted + manual
            all_mappings = {}
            
            # 1. Add auto-matched mappings (80%+ confidence)
            for src_col, file_col in stats["mappings"].items():
                all_mappings[src_col] = {
                    "file_col": file_col,
                    "confidence": 85.0,  # Default for auto-matched
                    "type": "auto"
                }
            
            # 2. Add accepted mappings from review section (70-80% and <70%)
            accepted_in_schema = st.session_state["accepted_mappings"].get(schema_name, {})
            for src_col, mapping_info in accepted_in_schema.items():
                all_mappings[src_col] = {
                    "file_col": mapping_info['target'],
                    "confidence": mapping_info['confidence'],
                    "type": mapping_info['type']
                }
            
            # 3. Add manually mapped columns (from unmapped section)
            manual_mappings_schema = st.session_state.manual_mappings_by_schema.get(schema_name, {})
            for file_col, src_col in manual_mappings_schema.items():
                all_mappings[src_col] = {
                    "file_col": file_col,
                    "confidence": 100.0,
                    "type": "manual"
                }
            
            # Display if there are any mappings
            if all_mappings:
                with st.expander(f"Schema: {schema_name} ({len(all_mappings)} matches)"):
                    mapping_data = []
                    for src_col, info in all_mappings.items():
                        mapping_data.append({
                            "Source Column": src_col,
                            "File Column": info['file_col'],
                            "Confidence %": f"{info['confidence']:.0f}" if info['confidence'] > 0 else "80+",
                            "Type": info['type'].replace("_", " ").title()
                        })
                    
                    mapping_df = pd.DataFrame(mapping_data)
                    st.dataframe(mapping_df, use_container_width=True)

else:
    st.info("📤 Upload an Excel file to start matching with all available standard schemas.")
