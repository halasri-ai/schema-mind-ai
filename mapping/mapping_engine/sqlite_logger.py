"""
SQLite-based logger for mapping updates.
Stores all mapping change history in a local database.
"""
import sqlite3
import datetime
import logging
from pathlib import Path
from typing import List, Dict, Any

logger = logging.getLogger(__name__)

# Database path
DB_PATH = Path(__file__).parent.parent.parent / "mapping_logs.db"


def _ensure_db_exists():
    """Create database and tables if they don't exist."""
    try:
        conn = sqlite3.connect(str(DB_PATH))
        cursor = conn.cursor()

        # Create mapping_logs table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS mapping_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                source_column TEXT NOT NULL,
                target_file_column TEXT,
                mapping_type TEXT NOT NULL,
                confidence_score REAL,
                file_name TEXT,
                sheet_name TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)

        conn.commit()
        conn.close()
        logger.debug(f"SQLite database initialized at {DB_PATH}")
    except Exception as e:
        logger.error(f"Failed to initialize SQLite database: {e}")


def log_mapping_change(
    source_col: str,
    file_col: str,
    mapping_type: str,
    confidence: float = 0,
    file_name: str = None,
    sheet_name: str = None
) -> bool:
    """
    Log a mapping change to SQLite database.

    Args:
        source_col: Source column name
        file_col: Target file column name (or empty if unmapped)
        mapping_type: Type of mapping (engine_auto, manual_remapped, ai_suggested_by_gemini, etc.)
        confidence: Confidence score (0-100)
        file_name: Optional file name being processed
        sheet_name: Optional sheet name being processed

    Returns:
        True if successful, False otherwise
    """
    _ensure_db_exists()

    try:
        timestamp = datetime.datetime.now().isoformat()
        conn = sqlite3.connect(str(DB_PATH))
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO mapping_logs
            (timestamp, source_column, target_file_column, mapping_type, confidence_score, file_name, sheet_name)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (timestamp, source_col, file_col or None, mapping_type, confidence, file_name, sheet_name))

        conn.commit()
        conn.close()

        logger.debug(f"Logged mapping: {source_col} -> {file_col} ({mapping_type})")
        return True
    except Exception as e:
        logger.error(f"Failed to log mapping change: {e}")
        return False


def get_all_logs(limit: int = 1000) -> List[Dict[str, Any]]:
    """
    Retrieve all mapping logs from database.

    Args:
        limit: Maximum number of logs to retrieve

    Returns:
        List of log records as dicts
    """
    _ensure_db_exists()

    try:
        conn = sqlite3.connect(str(DB_PATH))
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute("""
            SELECT id, timestamp, source_column, target_file_column, mapping_type, 
                   confidence_score, file_name, sheet_name, created_at
            FROM mapping_logs
            ORDER BY created_at DESC
            LIMIT ?
        """, (limit,))

        rows = cursor.fetchall()
        conn.close()

        return [dict(row) for row in rows]
    except Exception as e:
        logger.error(f"Failed to retrieve logs: {e}")
        return []


def get_logs_by_file(file_name: str) -> List[Dict[str, Any]]:
    """Get all logs for a specific file."""
    _ensure_db_exists()

    try:
        conn = sqlite3.connect(str(DB_PATH))
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute("""
            SELECT id, timestamp, source_column, target_file_column, mapping_type, 
                   confidence_score, file_name, sheet_name, created_at
            FROM mapping_logs
            WHERE file_name = ?
            ORDER BY created_at DESC
        """, (file_name,))

        rows = cursor.fetchall()
        conn.close()

        return [dict(row) for row in rows]
    except Exception as e:
        logger.error(f"Failed to retrieve file logs: {e}")
        return []


def get_logs_by_type(mapping_type: str) -> List[Dict[str, Any]]:
    """Get all logs of a specific mapping type."""
    _ensure_db_exists()

    try:
        conn = sqlite3.connect(str(DB_PATH))
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute("""
            SELECT id, timestamp, source_column, target_file_column, mapping_type, 
                   confidence_score, file_name, sheet_name, created_at
            FROM mapping_logs
            WHERE mapping_type = ?
            ORDER BY created_at DESC
        """, (mapping_type,))

        rows = cursor.fetchall()
        conn.close()

        return [dict(row) for row in rows]
    except Exception as e:
        logger.error(f"Failed to retrieve logs by type: {e}")
        return []


def clear_logs() -> bool:
    """Delete all logs from database."""
    _ensure_db_exists()

    try:
        conn = sqlite3.connect(str(DB_PATH))
        cursor = conn.cursor()
        cursor.execute("DELETE FROM mapping_logs")
        conn.commit()
        conn.close()
        logger.info("All mapping logs cleared")
        return True
    except Exception as e:
        logger.error(f"Failed to clear logs: {e}")
        return False


def get_stats() -> Dict[str, Any]:
    """Get summary statistics from logs."""
    _ensure_db_exists()

    try:
        conn = sqlite3.connect(str(DB_PATH))
        cursor = conn.cursor()

        # Total logs
        cursor.execute("SELECT COUNT(*) FROM mapping_logs")
        total = cursor.fetchone()[0]

        # Logs by type
        cursor.execute("""
            SELECT mapping_type, COUNT(*) as count
            FROM mapping_logs
            GROUP BY mapping_type
            ORDER BY count DESC
        """)
        by_type = {row[0]: row[1] for row in cursor.fetchall()}

        # Average confidence
        cursor.execute("SELECT AVG(confidence_score) FROM mapping_logs WHERE confidence_score > 0")
        avg_confidence = cursor.fetchone()[0] or 0

        # Unique files
        cursor.execute("SELECT COUNT(DISTINCT file_name) FROM mapping_logs WHERE file_name IS NOT NULL")
        unique_files = cursor.fetchone()[0]

        conn.close()

        return {
            "total_logs": total,
            "by_type": by_type,
            "average_confidence": round(avg_confidence, 2),
            "unique_files": unique_files,
            "db_path": str(DB_PATH)
        }
    except Exception as e:
        logger.error(f"Failed to get stats: {e}")
        return {}
