"""
Mapping Memory Viewer Page
Display and manage learned manual mappings from the memory database.
"""
import streamlit as st
import pandas as pd
from mapping.mapping_engine.mapping_memory import (
    get_memory_stats,
    get_all_file_mappings,
    get_suggested_mapping,
    save_manual_mapping,
    clear_memory,
    clear_specific_data
)

# Cache data fetching to prevent unnecessary reruns
@st.cache_data
def cached_get_memory_stats():
    return get_memory_stats()

@st.cache_data
def cached_get_all_file_mappings():
    return get_all_file_mappings()

st.set_page_config(page_title="Mapping Memory", page_icon="📚", layout="wide")

st.title("📚 Mapping Memory")
st.caption("View and manage learned column mappings from your manual mapping history.")

# Initialize session state for refresh
if "memory_refresh_count" not in st.session_state:
    st.session_state.memory_refresh_count = 0

# Display overall statistics
st.subheader("Memory Statistics")
stats = cached_get_memory_stats()

if stats["total_manual_mappings"] > 0:
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Total Saved Mappings", stats["total_manual_mappings"])
    with col2:
        st.metric("Files Processed", stats["total_files_processed"])
    with col3:
        st.metric("Avg Success Rate", f"{stats['average_success_rate']:.1f}%")
    with col4:
        st.metric("Database Size", f"{len(str(stats['db_path']))} chars")
    
    # Refresh button
    if st.button("🔄 Refresh Data"):
        st.cache_data.clear()
        st.session_state.memory_refresh_count += 1
        st.rerun()
else:
    st.info("🔍 No mapping memory recorded yet.")
    st.write("Start by mapping columns in the main app to build your mapping memory. Manually confirmed mappings will be saved here.")
