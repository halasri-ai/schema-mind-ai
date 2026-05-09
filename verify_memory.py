"""
Quick verification script to check memory database status
Run this anytime to see what's stored in the mapping memory
"""

import sqlite3
from pathlib import Path
from mapping.mapping_engine.mapping_memory import (
    get_memory_stats,
    get_all_file_mappings,
    get_suggested_mapping,
    MEMORY_DB_PATH
)

def print_section(title):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}\n")

def verify_memory_database():
    """Quick diagnostic check of the memory database"""
    
    print_section("MAPPING MEMORY DATABASE STATUS")
    
    # Check if database exists
    if not MEMORY_DB_PATH.exists():
        print(f"❌ Database not found at: {MEMORY_DB_PATH}")
        print("   Database will be created on first manual mapping save.")
        return
    
    print(f"✓ Database found at: {MEMORY_DB_PATH}")
    print(f"  File size: {MEMORY_DB_PATH.stat().st_size / 1024:.2f} KB")
    
    # Check tables
    print_section("DATABASE TABLES")
    
    try:
        conn = sqlite3.connect(str(MEMORY_DB_PATH))
        cursor = conn.cursor()
        
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = cursor.fetchall()
        
        if tables:
            for table_name in tables:
                print(f"✓ {table_name[0]}")
                
                # Get row count
                cursor.execute(f"SELECT COUNT(*) FROM {table_name[0]}")
                count = cursor.fetchone()[0]
                print(f"  └─ Records: {count}")
        else:
            print("❌ No tables found")
            return
        
        conn.close()
    except Exception as e:
        print(f"❌ Error reading database: {e}")
        return
    
    # Get and display stats
    print_section("MEMORY STATISTICS")
    
    try:
        stats = get_memory_stats()
        
        print(f"Total manual mappings: {stats.get('total_manual_mappings', 0)}")
        print(f"Files processed: {stats.get('total_files_processed', 0)}")
        print(f"Average success rate: {stats.get('average_success_rate', 0):.1f}%")
        
        if stats['top_mappings']:
            print(f"\nTop 5 frequently used mappings:")
            for i, mapping in enumerate(stats['top_mappings'], 1):
                print(f"  {i}. {mapping['source']} → {mapping['target']} ({mapping['count']}x)")
        
        if stats['recent_mappings']:
            print(f"\nMost recent mappings:")
            for i, mapping in enumerate(stats['recent_mappings'], 1):
                print(f"  {i}. {mapping['source']} → {mapping['target']}")
                print(f"     Last used: {mapping['last_used']}")
    
    except Exception as e:
        print(f"❌ Error getting stats: {e}")
        return
    
    # Get file mappings
    print_section("FILE PROCESSING HISTORY")
    
    try:
        file_mappings = get_all_file_mappings(limit=10)
        
        if file_mappings:
            for file_map in file_mappings:
                print(f"📁 {file_map['file_name']}")
                print(f"   Sheet: {file_map['sheet_name']}")
                print(f"   Mappings: {file_map['successful_mappings']}/{file_map['total_mappings']}")
                print(f"   Success rate: {(file_map['successful_mappings'] / file_map['total_mappings'] * 100):.0f}%" if file_map['total_mappings'] > 0 else "   Success rate: N/A")
                print(f"   Created: {file_map['created_at']}")
                print()
        else:
            print("No file mappings recorded yet.")
    
    except Exception as e:
        print(f"❌ Error getting file mappings: {e}")
        return
    
    # Summary
    print_section("SUMMARY")
    
    try:
        stats = get_memory_stats()
        
        if stats['total_manual_mappings'] > 0:
            print(f"✓ Memory is working!")
            print(f"  - {stats['total_manual_mappings']} mappings saved")
            print(f"  - {stats['total_files_processed']} files processed")
            print(f"  - {stats['average_success_rate']:.1f}% average success rate")
        else:
            print("ℹ No mappings in memory yet.")
            print("  Start by manually mapping columns in the main app.")
            print("  All manual mappings will be automatically saved.")
    
    except Exception as e:
        print(f"❌ Error: {e}")
    
    print("\n" + "="*60)

if __name__ == "__main__":
    verify_memory_database()
