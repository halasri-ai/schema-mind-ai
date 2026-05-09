"""
Manual Mapping Memory Manager
Stores and retrieves manually mapped column pairs for future use.
This module maintains a separate database of user-confirmed mappings.
"""
import sqlite3
import datetime
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple

logger = logging.getLogger(__name__)

# Database path for mapping memory
MEMORY_DB_PATH = Path(__file__).parent.parent.parent / "mapping_memory.db"


def _ensure_memory_db_exists():
    """Create mapping memory database and tables if they don't exist."""
    try:
        conn = sqlite3.connect(str(MEMORY_DB_PATH))
        cursor = conn.cursor()

        # Create table for manual mappings (source column -> target column)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS manual_mappings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_column TEXT NOT NULL,
                target_column TEXT NOT NULL,
                file_type TEXT,
                usage_count INTEGER DEFAULT 1,
                last_used DATETIME DEFAULT CURRENT_TIMESTAMP,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(source_column, target_column, file_type)
            )
        """)

        # Create table for file metadata (tracks which files use which mappings)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS file_mappings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                file_name TEXT NOT NULL,
                file_type TEXT,
                sheet_name TEXT,
                source_columns TEXT,
                target_columns TEXT,
                total_mappings INTEGER,
                successful_mappings INTEGER,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                last_modified DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Create table for mapping confidence tracking
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS mapping_confidence (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_column TEXT NOT NULL,
                target_column TEXT NOT NULL,
                confidence_score REAL,
                user_confirmed BOOLEAN DEFAULT 0,
                confirmed_at DATETIME,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)

        conn.commit()
        conn.close()
        logger.debug(f"Mapping memory database ready at {MEMORY_DB_PATH}")
    except Exception as e:
        logger.error(f"Failed to initialize mapping memory database: {e}")


def save_manual_mapping(
    source_column: str,
    target_column: str,
    file_type: str = None,
    confidence_score: float = 100.0,
    user_confirmed: bool = True
) -> bool:
    """
    Save a manually mapped column pair to memory.
    
    Args:
        source_column: Name of the source column
        target_column: Name of the target file column
        file_type: Optional file type identifier (e.g., 'csv', 'xlsx')
        confidence_score: Confidence level (0-100)
        user_confirmed: Whether user explicitly confirmed this mapping
    
    Returns:
        True if successful, False otherwise
    """
    _ensure_memory_db_exists()

    try:
        conn = sqlite3.connect(str(MEMORY_DB_PATH))
        cursor = conn.cursor()

        # Try to update existing mapping or insert new one
        cursor.execute("""
            INSERT INTO manual_mappings (source_column, target_column, file_type, usage_count, last_used)
            VALUES (?, ?, ?, 1, CURRENT_TIMESTAMP)
            ON CONFLICT(source_column, target_column, file_type)
            DO UPDATE SET usage_count = usage_count + 1, last_used = CURRENT_TIMESTAMP
        """, (source_column, target_column, file_type))

        # Also log confidence if user confirmed
        if user_confirmed:
            cursor.execute("""
                INSERT INTO mapping_confidence (source_column, target_column, confidence_score, user_confirmed, confirmed_at)
                VALUES (?, ?, ?, 1, CURRENT_TIMESTAMP)
            """, (source_column, target_column, confidence_score))

        conn.commit()
        conn.close()

        logger.debug(f"Saved manual mapping: {source_column} -> {target_column}")
        return True
    except Exception as e:
        logger.error(f"Failed to save manual mapping: {e}")
        return False


def get_suggested_mapping(
    source_column: str,
    file_type: str = None,
    limit: int = 5
) -> List[Dict[str, Any]]:
    """
    Get suggested mappings for a source column based on historical manual mappings.
    
    Args:
        source_column: Source column name
        file_type: Optional file type filter
        limit: Maximum number of suggestions
    
    Returns:
        List of suggested mappings sorted by usage frequency
    """
    _ensure_memory_db_exists()

    try:
        conn = sqlite3.connect(str(MEMORY_DB_PATH))
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        if file_type:
            cursor.execute("""
                SELECT target_column, usage_count, last_used, file_type
                FROM manual_mappings
                WHERE source_column = ? AND file_type = ?
                ORDER BY usage_count DESC, last_used DESC
                LIMIT ?
            """, (source_column, file_type, limit))
        else:
            cursor.execute("""
                SELECT target_column, usage_count, last_used, file_type
                FROM manual_mappings
                WHERE source_column = ?
                ORDER BY usage_count DESC, last_used DESC
                LIMIT ?
            """, (source_column, limit))

        rows = cursor.fetchall()
        conn.close()

        return [dict(row) for row in rows]
    except Exception as e:
        logger.error(f"Failed to get suggested mappings: {e}")
        return []


def save_file_mapping(
    file_name: str,
    sheet_name: str,
    source_columns: List[str],
    target_columns: List[str],
    file_type: str = None,
    successful_mappings: int = None
) -> bool:
    """
    Save file-level mapping metadata.
    
    Args:
        file_name: Name of the processed file
        sheet_name: Sheet name within the file
        source_columns: List of source column names
        target_columns: List of target column names
        file_type: Optional file type (csv, xlsx, etc.)
        successful_mappings: Number of successful mappings
    
    Returns:
        True if successful, False otherwise
    """
    _ensure_memory_db_exists()

    try:
        conn = sqlite3.connect(str(MEMORY_DB_PATH))
        cursor = conn.cursor()

        successful = successful_mappings or sum(1 for t in target_columns if t)
        total = len(source_columns)

        # Delete existing record if it exists, then insert new one
        cursor.execute(
            "DELETE FROM file_mappings WHERE file_name = ? AND sheet_name = ?",
            (file_name, sheet_name)
        )
        
        cursor.execute("""
            INSERT INTO file_mappings 
            (file_name, sheet_name, file_type, source_columns, target_columns, total_mappings, successful_mappings, created_at, last_modified)
            VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        """, (file_name, sheet_name, file_type, ";".join(source_columns), ";".join(target_columns), total, successful))

        conn.commit()
        conn.close()

        logger.debug(f"Saved file mapping metadata for {file_name} sheet {sheet_name}")
        return True
    except Exception as e:
        logger.error(f"Failed to save file mapping: {e}")
        return False


def get_file_mappings(file_name: str) -> Optional[Dict[str, Any]]:
    """
    Retrieve saved mapping metadata for a specific file.
    
    Args:
        file_name: Name of the file
    
    Returns:
        File mapping metadata or None if not found
    """
    _ensure_memory_db_exists()

    try:
        conn = sqlite3.connect(str(MEMORY_DB_PATH))
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute("""
            SELECT * FROM file_mappings
            WHERE file_name = ?
        """, (file_name,))

        row = cursor.fetchone()
        conn.close()

        if row:
            result = dict(row)
            # Parse the column lists
            result["source_columns"] = result["source_columns"].split(";") if result["source_columns"] else []
            result["target_columns"] = result["target_columns"].split(";") if result["target_columns"] else []
            return result
        return None
    except Exception as e:
        logger.error(f"Failed to retrieve file mapping: {e}")
        return None


def get_all_file_mappings(limit: int = 100) -> List[Dict[str, Any]]:
    """
    Get all saved file mappings.
    
    Args:
        limit: Maximum number of records to return
    
    Returns:
        List of file mapping records
    """
    _ensure_memory_db_exists()

    try:
        conn = sqlite3.connect(str(MEMORY_DB_PATH))
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute("""
            SELECT * FROM file_mappings
            ORDER BY last_modified DESC
            LIMIT ?
        """, (limit,))

        rows = cursor.fetchall()
        conn.close()

        result = []
        for row in rows:
            item = dict(row)
            item["source_columns"] = item["source_columns"].split(";") if item["source_columns"] else []
            item["target_columns"] = item["target_columns"].split(";") if item["target_columns"] else []
            result.append(item)
        return result
    except Exception as e:
        logger.error(f"Failed to retrieve file mappings: {e}")
        return []


def get_mapping_pair_frequency(source_column: str, target_column: str) -> int:
    """
    Get how many times a specific source-target mapping pair has been used.
    
    Args:
        source_column: Source column name
        target_column: Target column name
    
    Returns:
        Usage count (0 if not found)
    """
    _ensure_memory_db_exists()

    try:
        conn = sqlite3.connect(str(MEMORY_DB_PATH))
        cursor = conn.cursor()

        cursor.execute("""
            SELECT usage_count FROM manual_mappings
            WHERE source_column = ? AND target_column = ?
        """, (source_column, target_column))

        row = cursor.fetchone()
        conn.close()

        return row[0] if row else 0
    except Exception as e:
        logger.error(f"Failed to get mapping frequency: {e}")
        return 0


def get_memory_stats() -> Dict[str, Any]:
    """
    Get summary statistics about saved mappings.
    
    Returns:
        Dictionary with mapping statistics
    """
    _ensure_memory_db_exists()

    try:
        conn = sqlite3.connect(str(MEMORY_DB_PATH))
        cursor = conn.cursor()

        # Total unique manual mappings
        cursor.execute("SELECT COUNT(*) FROM manual_mappings")
        total_mappings = cursor.fetchone()[0]

        # Most frequently used mappings
        cursor.execute("""
            SELECT source_column, target_column, usage_count
            FROM manual_mappings
            ORDER BY usage_count DESC
            LIMIT 5
        """)
        top_mappings = [{"source": row[0], "target": row[1], "count": row[2]} for row in cursor.fetchall()]

        # Total files processed
        cursor.execute("SELECT COUNT(*) FROM file_mappings")
        total_files = cursor.fetchone()[0]

        # Average success rate
        cursor.execute("""
            SELECT AVG(CAST(successful_mappings AS FLOAT) / total_mappings * 100)
            FROM file_mappings
            WHERE total_mappings > 0
        """)
        avg_success_rate = cursor.fetchone()[0] or 0

        # Most recently used mappings
        cursor.execute("""
            SELECT source_column, target_column, last_used
            FROM manual_mappings
            ORDER BY last_used DESC
            LIMIT 5
        """)
        recent_mappings = [{"source": row[0], "target": row[1], "last_used": row[2]} for row in cursor.fetchall()]

        conn.close()

        return {
            "total_manual_mappings": total_mappings,
            "top_mappings": top_mappings,
            "total_files_processed": total_files,
            "average_success_rate": round(avg_success_rate, 2),
            "recent_mappings": recent_mappings,
            "db_path": str(MEMORY_DB_PATH)
        }
    except Exception as e:
        logger.error(f"Failed to get memory stats: {e}")
        return {
            "total_manual_mappings": 0,
            "top_mappings": [],
            "total_files_processed": 0,
            "average_success_rate": 0,
            "recent_mappings": [],
            "db_path": str(MEMORY_DB_PATH)
        }


def clear_memory() -> bool:
    """
    Clear all mapping memory data.
    
    Returns:
        True if successful, False otherwise
    """
    _ensure_memory_db_exists()

    try:
        conn = sqlite3.connect(str(MEMORY_DB_PATH))
        cursor = conn.cursor()
        
        cursor.execute("DELETE FROM manual_mappings")
        cursor.execute("DELETE FROM file_mappings")
        cursor.execute("DELETE FROM mapping_confidence")
        
        conn.commit()
        conn.close()
        
        logger.info("Mapping memory cleared")
        return True
    except Exception as e:
        logger.error(f"Failed to clear mapping memory: {e}")
        return False


def clear_specific_data(table_names: List[str] = None) -> bool:
    """
    Clear specific tables from the mapping memory database.
    
    Args:
        table_names: List of table names to clear ('manual_mappings', 'file_mappings', 'mapping_confidence')
                    If None, clears all tables
    
    Returns:
        True if successful, False otherwise
    """
    _ensure_memory_db_exists()

    try:
        conn = sqlite3.connect(str(MEMORY_DB_PATH))
        cursor = conn.cursor()
        
        if table_names is None:
            table_names = ["manual_mappings", "file_mappings", "mapping_confidence"]
        
        for table_name in table_names:
            if table_name in ["manual_mappings", "file_mappings", "mapping_confidence"]:
                cursor.execute(f"DELETE FROM {table_name}")
        
        conn.commit()
        conn.close()
        
        logger.info(f"Cleared tables: {', '.join(table_names)}")
        return True
    except Exception as e:
        logger.error(f"Failed to clear specific data: {e}")
        return False


def get_similar_mappings(source_column: str, similarity_threshold: float = 0.6) -> List[Dict[str, Any]]:
    """
    Get mappings for source columns similar to the given one (fuzzy matching).
    
    Args:
        source_column: Source column name to match
        similarity_threshold: Minimum similarity score (0-1)
    
    Returns:
        List of similar mapping suggestions
    """
    _ensure_memory_db_exists()

    try:
        conn = sqlite3.connect(str(MEMORY_DB_PATH))
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # Get all unique source columns
        cursor.execute("SELECT DISTINCT source_column FROM manual_mappings")
        all_sources = [row[0] for row in cursor.fetchall()]
        conn.close()

        # Simple similarity check using substring matching and length ratio
        similar = []
        source_lower = source_column.lower()
        
        for src in all_sources:
            src_lower = src.lower()
            # Check if one contains the other or if they share significant parts
            if source_lower in src_lower or src_lower in source_lower:
                # Get the mappings for this similar source
                mappings = get_suggested_mapping(src, limit=3)
                similar.extend([{
                    "source_column": src,
                    "target_column": m["target_column"],
                    "usage_count": m["usage_count"]
                } for m in mappings])

        return sorted(similar, key=lambda x: x["usage_count"], reverse=True)[:5]
    except Exception as e:
        logger.error(f"Failed to get similar mappings: {e}")
        return []
