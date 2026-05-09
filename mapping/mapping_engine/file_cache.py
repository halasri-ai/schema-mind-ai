"""
File-based mapping cache.
Saves mappings per file so repeated uploads are automatically mapped.
"""

import sqlite3
import json
import logging
import hashlib
from pathlib import Path
from typing import Dict, List, Optional, Any
from datetime import datetime

logger = logging.getLogger(__name__)

# Database path for file mappings
FILE_CACHE_DB_PATH = Path(__file__).parent.parent.parent / "file_mappings_cache.db"


def _ensure_cache_db_exists():
    """Create file mapping cache database if it doesn't exist."""
    try:
        conn = sqlite3.connect(str(FILE_CACHE_DB_PATH))
        cursor = conn.cursor()

        # Table for file hashes and metadata
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS file_cache (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                file_hash TEXT UNIQUE NOT NULL,
                file_name TEXT NOT NULL,
                file_size INTEGER,
                file_columns TEXT,
                upload_count INTEGER DEFAULT 1,
                first_seen DATETIME DEFAULT CURRENT_TIMESTAMP,
                last_seen DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Table for file-specific mappings (per file + schema)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS file_schema_mappings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                file_hash TEXT NOT NULL,
                schema_name TEXT NOT NULL,
                mappings_json TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(file_hash) REFERENCES file_cache(file_hash),
                UNIQUE(file_hash, schema_name)
            )
        """)

        conn.commit()
        conn.close()
        logger.debug(f"File cache database ready at {FILE_CACHE_DB_PATH}")
    except Exception as e:
        logger.error(f"Failed to initialize file cache database: {e}")


def calculate_file_hash(file_path: str, file_name: str, file_size: int) -> str:
    """
    Calculate a hash for a file based on name, size, and columns.
    
    Args:
        file_path: Path to the file
        file_name: File name
        file_size: File size in bytes
    
    Returns:
        MD5 hash of file characteristics
    """
    try:
        hash_input = f"{file_name}_{file_size}"
        return hashlib.md5(hash_input.encode()).hexdigest()
    except Exception as e:
        logger.error(f"Failed to calculate file hash: {e}")
        return None


def save_file_mapping_cache(
    file_hash: str,
    file_name: str,
    file_size: int,
    file_columns: List[str],
    schema_name: str,
    mappings: Dict[str, str]
) -> bool:
    """
    Save file mappings to cache for future use.
    
    Args:
        file_hash: Hash of the file
        file_name: Name of the file
        file_size: Size of the file
        file_columns: Columns in the file
        schema_name: Schema name
        mappings: Dict of source_column -> file_column mappings
    
    Returns:
        True if successful
    """
    _ensure_cache_db_exists()

    try:
        conn = sqlite3.connect(str(FILE_CACHE_DB_PATH))
        cursor = conn.cursor()

        # Update or insert file record
        cursor.execute("""
            INSERT INTO file_cache (file_hash, file_name, file_size, file_columns)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(file_hash)
            DO UPDATE SET upload_count = upload_count + 1, last_seen = CURRENT_TIMESTAMP
        """, (file_hash, file_name, file_size, json.dumps(file_columns)))

        # Save mappings for this file+schema
        mappings_json = json.dumps(mappings)
        cursor.execute("""
            INSERT INTO file_schema_mappings (file_hash, schema_name, mappings_json)
            VALUES (?, ?, ?)
            ON CONFLICT(file_hash, schema_name)
            DO UPDATE SET mappings_json = ?, created_at = CURRENT_TIMESTAMP
        """, (file_hash, schema_name, mappings_json, mappings_json))

        conn.commit()
        conn.close()

        logger.info(f"Cached mappings for file {file_name} (hash: {file_hash[:8]}...)")
        return True
    except Exception as e:
        logger.error(f"Failed to save file mapping cache: {e}")
        return False


def get_cached_file_mappings(
    file_hash: str,
    schema_name: str = None
) -> Dict[str, Any]:
    """
    Retrieve cached mappings for a file.
    
    Args:
        file_hash: Hash of the file
        schema_name: Optional schema to filter by
    
    Returns:
        {
            "found": bool,
            "file_name": str,
            "file_columns": List[str],
            "schemas": {schema_name: mappings_dict}
        }
    """
    _ensure_cache_db_exists()

    try:
        conn = sqlite3.connect(str(FILE_CACHE_DB_PATH))
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # Get file info
        cursor.execute("""
            SELECT file_name, file_columns, upload_count, last_seen
            FROM file_cache
            WHERE file_hash = ?
        """, (file_hash,))

        file_record = cursor.fetchone()
        if not file_record:
            conn.close()
            return {"found": False}

        # Get mappings
        if schema_name:
            cursor.execute("""
                SELECT schema_name, mappings_json
                FROM file_schema_mappings
                WHERE file_hash = ? AND schema_name = ?
            """, (file_hash, schema_name))
        else:
            cursor.execute("""
                SELECT schema_name, mappings_json
                FROM file_schema_mappings
                WHERE file_hash = ?
            """, (file_hash,))

        mappings = {}
        for row in cursor.fetchall():
            mappings[row["schema_name"]] = json.loads(row["mappings_json"])

        conn.close()

        result = {
            "found": True,
            "file_name": file_record["file_name"],
            "file_columns": json.loads(file_record["file_columns"]),
            "upload_count": file_record["upload_count"],
            "last_seen": file_record["last_seen"],
            "schemas": mappings
        }

        logger.info(f"Retrieved cached mappings for file {file_record['file_name']} (upload #{file_record['upload_count']})")
        return result

    except Exception as e:
        logger.error(f"Failed to retrieve file mapping cache: {e}")
        return {"found": False}


def file_exists_in_cache(file_hash: str) -> bool:
    """Check if a file already exists in cache."""
    _ensure_cache_db_exists()

    try:
        conn = sqlite3.connect(str(FILE_CACHE_DB_PATH))
        cursor = conn.cursor()

        cursor.execute("SELECT 1 FROM file_cache WHERE file_hash = ?", (file_hash,))
        exists = cursor.fetchone() is not None

        conn.close()
        return exists
    except Exception as e:
        logger.error(f"Failed to check file cache: {e}")
        return False


def clear_file_cache() -> bool:
    """Clear all file mapping cache."""
    _ensure_cache_db_exists()

    try:
        conn = sqlite3.connect(str(FILE_CACHE_DB_PATH))
        cursor = conn.cursor()

        cursor.execute("DELETE FROM file_schema_mappings")
        cursor.execute("DELETE FROM file_cache")

        conn.commit()
        conn.close()

        logger.info("File mapping cache cleared")
        return True
    except Exception as e:
        logger.error(f"Failed to clear file cache: {e}")
        return False


def get_cache_stats() -> Dict[str, Any]:
    """Get statistics about the file mapping cache."""
    _ensure_cache_db_exists()

    try:
        conn = sqlite3.connect(str(FILE_CACHE_DB_PATH))
        cursor = conn.cursor()

        cursor.execute("SELECT COUNT(*) FROM file_cache")
        total_files = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM file_schema_mappings")
        total_mappings = cursor.fetchone()[0]

        cursor.execute("SELECT SUM(upload_count) FROM file_cache")
        total_uploads = cursor.fetchone()[0] or 0

        cursor.execute("SELECT AVG(upload_count) FROM file_cache")
        avg_uploads = cursor.fetchone()[0] or 0

        conn.close()

        return {
            "total_files_cached": total_files,
            "total_schema_mappings": total_mappings,
            "total_uploads_from_cache": total_uploads,
            "average_uploads_per_file": round(avg_uploads, 2)
        }
    except Exception as e:
        logger.error(f"Failed to get cache stats: {e}")
        return {}
