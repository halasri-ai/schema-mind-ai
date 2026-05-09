"""
Quick Fix Verification - Run this to verify all memory issues are resolved
"""

import sys
import os
sys.path.insert(0, str(os.path.dirname(__file__)))

def test_memory_functions():
    """Test if mapping memory module can be imported and used"""
    print("Testing mapping memory module...")
    
    try:
        from mapping.mapping_engine.mapping_memory import (
            get_memory_stats,
            save_file_mapping,
            save_manual_mapping
        )
        print("✓ Module imported successfully")
        
        # Test get_memory_stats with empty database
        try:
            stats = get_memory_stats()
            print(f"✓ get_memory_stats() returned: {type(stats)}")
            print(f"  - Keys: {list(stats.keys())}")
        except Exception as e:
            print(f"✗ get_memory_stats() failed: {e}")
            return False
        
        # Test save_manual_mapping
        try:
            result = save_manual_mapping("Test", "Target", user_confirmed=True)
            print(f"✓ save_manual_mapping() returned: {result}")
        except Exception as e:
            print(f"✗ save_manual_mapping() failed: {e}")
            return False
        
        # Test save_file_mapping
        try:
            result = save_file_mapping(
                file_name="test.xlsx",
                sheet_name="Sheet1",
                source_columns=["A", "B"],
                target_columns=["X", "Y"],
                successful_mappings=2
            )
            print(f"✓ save_file_mapping() returned: {result}")
        except Exception as e:
            print(f"✗ save_file_mapping() failed: {e}")
            return False
        
        return True
    except Exception as e:
        print(f"✗ Failed to import module: {e}")
        return False

def test_streamlit_import():
    """Test if app.py can be parsed"""
    print("\nTesting app.py syntax...")
    
    try:
        import ast
        with open("streamlit_app/app.py", "r") as f:
            code = f.read()
        ast.parse(code)
        print("✓ app.py syntax is valid")
        return True
    except SyntaxError as e:
        print(f"✗ Syntax error in app.py: {e}")
        return False

def main():
    print("="*60)
    print("MAPPING MEMORY FIX VERIFICATION")
    print("="*60 + "\n")
    
    memory_ok = test_memory_functions()
    streamlit_ok = test_streamlit_import()
    
    print("\n" + "="*60)
    if memory_ok and streamlit_ok:
        print("✓ ALL CHECKS PASSED - Ready to run!")
        print("="*60)
        print("\nNext steps:")
        print("1. python -m streamlit run streamlit_app/app.py")
        print("2. Upload an Excel file")
        print("3. Manually map some columns")
        print("4. Check memory page to see saved mappings")
        return 0
    else:
        print("✗ SOME CHECKS FAILED")
        print("="*60)
        return 1

if __name__ == "__main__":
    sys.exit(main())
