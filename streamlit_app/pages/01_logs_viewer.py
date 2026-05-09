"""
Streamlit Logs Viewer - View mapping log history from SQLite database.

Run from main app folder:
python -m streamlit run streamlit_app/app.py

This will automatically show as a separate page called "Logs" in the sidebar.
"""
import streamlit as st
import pandas as pd
from pathlib import Path
import sys

# Add parent path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from mapping.mapping_engine.sqlite_logger import (
    get_all_logs, 
    get_logs_by_file, 
    get_logs_by_type, 
    get_stats, 
    clear_logs,
    DB_PATH
)

# Cache data fetching to prevent unnecessary reruns
@st.cache_data
def cached_get_all_logs(limit=500):
    return get_all_logs(limit=limit)

@st.cache_data
def cached_get_logs_by_file(file_name):
    return get_logs_by_file(file_name)

@st.cache_data
def cached_get_logs_by_type(mapping_type):
    return get_logs_by_type(mapping_type)

@st.cache_data
def cached_get_stats():
    return get_stats()

st.set_page_config(page_title="Mapping Logs", page_icon="📊", layout="wide")

st.title("📊 Mapping Change Logs")
st.caption("View the complete history of all mapping changes from the local SQLite database.")

# Sidebar: Filter options
st.sidebar.markdown("---")
st.sidebar.subheader("📋 Log Filters")

filter_type = st.sidebar.radio(
    "View logs by:",
    ["All Logs", "By File", "By Mapping Type", "Statistics"]
)

# Main content
if filter_type == "All Logs":
    st.subheader("All Mapping Changes")
    
    if "log_limit" not in st.session_state:
        st.session_state.log_limit = 500
    
    col1, col2 = st.columns(2)
    with col1:
        st.session_state.log_limit = st.number_input("Number of logs to display", min_value=10, max_value=10000, value=st.session_state.log_limit, step=50)
    with col2:
        if st.button("🔄 Refresh"):
            st.cache_data.clear()
            st.rerun()
    
    logs = cached_get_all_logs(limit=st.session_state.log_limit)
    if logs:
        df = pd.DataFrame(logs)
        # Format columns
        df = df[["timestamp", "source_column", "target_file_column", "mapping_type", "confidence_score", "file_name", "sheet_name"]]
        df.columns = ["Timestamp", "Source Column", "Target Column", "Type", "Confidence (%)", "File", "Sheet"]
        
        st.dataframe(df, use_container_width=True, height=600)
        
        st.info(f"Showing {len(df)} of {len(df)} logs")
    else:
        st.info("No logs found in database.")

elif filter_type == "By File":
    st.subheader("Logs by File")
    
    if "selected_file" not in st.session_state:
        st.session_state.selected_file = None
    
    # Get unique files
    all_logs = cached_get_all_logs(limit=10000)
    unique_files = sorted(set(log["file_name"] for log in all_logs if log["file_name"]))
    
    if unique_files:
        st.session_state.selected_file = st.selectbox("Select file", unique_files, index=0 if st.session_state.selected_file is None else unique_files.index(st.session_state.selected_file) if st.session_state.selected_file in unique_files else 0)
        
        if st.button("📂 Load logs for this file"):
            file_logs = cached_get_logs_by_file(st.session_state.selected_file)
            if file_logs:
                df = pd.DataFrame(file_logs)
                df = df[["timestamp", "source_column", "target_file_column", "mapping_type", "confidence_score", "sheet_name"]]
                df.columns = ["Timestamp", "Source Column", "Target Column", "Type", "Confidence (%)", "Sheet"]
                
                st.success(f"Found {len(df)} logs for {st.session_state.selected_file}")
                st.dataframe(df, use_container_width=True, height=600)
            else:
                st.info(f"No logs found for {st.session_state.selected_file}")
    else:
        st.info("No files in log history yet.")

elif filter_type == "By Mapping Type":
    st.subheader("Logs by Mapping Type")
    
    if "selected_mapping_type" not in st.session_state:
        st.session_state.selected_mapping_type = None
    
    # Get all logs and extract unique types
    all_logs = cached_get_all_logs(limit=10000)
    unique_types = sorted(set(log["mapping_type"] for log in all_logs))
    
    if unique_types:
        st.session_state.selected_mapping_type = st.selectbox(
            "Select mapping type",
            unique_types,
            index=0 if st.session_state.selected_mapping_type is None else unique_types.index(st.session_state.selected_mapping_type) if st.session_state.selected_mapping_type in unique_types else 0,
            help="Examples: engine_auto, manual_remapped, ai_suggested_by_gemini"
        )
        
        col1, col2 = st.columns(2)
        with col1:
            type_count = sum(1 for log in all_logs if log["mapping_type"] == st.session_state.selected_mapping_type)
            st.metric("Count", type_count)
        with col2:
            avg_conf = sum(log["confidence_score"] or 0 for log in all_logs if log["mapping_type"] == st.session_state.selected_mapping_type) / max(1, type_count)
            st.metric("Avg Confidence", f"{avg_conf:.1f}%")
        
        st.write("---")
        
        type_logs = cached_get_logs_by_type(st.session_state.selected_mapping_type)
        if type_logs:
            df = pd.DataFrame(type_logs)
            df = df[["timestamp", "source_column", "target_file_column", "confidence_score", "file_name", "sheet_name"]]
            df.columns = ["Timestamp", "Source Column", "Target Column", "Confidence (%)", "File", "Sheet"]
            
            st.dataframe(df, use_container_width=True, height=600)
        else:
            st.info(f"No logs found for type: {st.session_state.selected_mapping_type}")
    else:
        st.info("No mapping types in log history yet.")

elif filter_type == "Statistics":
    st.subheader("📈 Mapping Statistics")
    
    stats = cached_get_stats()
    
    if stats:
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("Total Mappings", stats.get("total_logs", 0))
        with col2:
            st.metric("Avg Confidence", f"{stats.get('average_confidence', 0):.1f}%")
        with col3:
            st.metric("Unique Files", stats.get("unique_files", 0))
        with col4:
            st.metric("DB Location", str(DB_PATH).split(chr(92))[-1])  # Show filename only
        
        st.write("---")
        
        # By type breakdown
        st.subheader("Breakdown by Type")
        by_type = stats.get("by_type", {})
        if by_type:
            type_data = pd.DataFrame([
                {"Mapping Type": k, "Count": v}
                for k, v in by_type.items()
            ])
            
            col1, col2 = st.columns([2, 1])
            with col1:
                st.dataframe(type_data, use_container_width=True)
            with col2:
                st.bar_chart(type_data.set_index("Mapping Type"))
        
        st.info(f"📁 SQLite Database: {stats.get('db_path', 'unknown')}")
    else:
        st.info("No statistics available yet.")

# Sidebar: Actions
st.sidebar.markdown("---")
st.sidebar.subheader("⚙️ Actions")

if "confirm_clear_logs" not in st.session_state:
    st.session_state.confirm_clear_logs = False

if st.sidebar.button("🗑️ Clear All Logs", help="Permanently delete all mapping logs from database"):
    st.session_state.confirm_clear_logs = True

if st.session_state.confirm_clear_logs:
    if st.sidebar.checkbox("⚠️ I understand this is permanent"):
        if clear_logs():
            st.cache_data.clear()
            st.sidebar.success("All logs cleared!")
            st.session_state.confirm_clear_logs = False
            st.rerun()
        else:
            st.sidebar.error("Failed to clear logs")
    if st.sidebar.button("Cancel"):
        st.session_state.confirm_clear_logs = False

st.sidebar.markdown("---")
st.sidebar.caption(f"📊 **Database Info**\n\nPath: `{DB_PATH}`\n\nFormat: SQLite 3")
