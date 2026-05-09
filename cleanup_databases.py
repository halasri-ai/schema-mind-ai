"""
Cleanup script - removes old databases to start fresh
Run this once to clean up any corrupted databases
"""

import os
from pathlib import Path

def cleanup_databases():
    """Remove old databases that might have issues"""
    
    workspace = Path(__file__).parent
    
    db_files = [
        workspace / "mapping_memory.db",
        workspace / "mapping_logs.db"
    ]
    
    print("="*60)
    print("DATABASE CLEANUP")
    print("="*60 + "\n")
    
    for db_file in db_files:
        if db_file.exists():
            try:
                size_kb = db_file.stat().st_size / 1024
                os.remove(db_file)
                print(f"✓ Deleted {db_file.name} ({size_kb:.1f} KB)")
            except Exception as e:
                print(f"✗ Failed to delete {db_file.name}: {e}")
        else:
            print(f"ℹ {db_file.name} not found (fresh start)")
    
    print("\n" + "="*60)
    print("Cleanup complete!")
    print("Databases will be recreated on next run")
    print("="*60)

if __name__ == "__main__":
    cleanup_databases()
