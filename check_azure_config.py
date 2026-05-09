"""
Azure Configuration Diagnostic Script
Check if Azure OpenAI is properly configured
"""

import sys
import os
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

print("=" * 70)
print("AZURE OPENAI CONFIGURATION DIAGNOSTIC")
print("=" * 70 + "\n")

# Load .env file
print("1. Loading .env file...")
env_file = Path(__file__).parent / ".env"
print(f"   .env path: {env_file}")
print(f"   .env exists: {env_file.exists()}")

if env_file.exists():
    from dotenv import load_dotenv
    load_dotenv(env_file)
    print("   ✓ .env file loaded\n")
else:
    print("   ✗ .env file not found\n")

# Check environment variables
print("2. Checking environment variables...")
required_vars = {
    "AZURE_OPENAI_KEY": "Azure OpenAI API Key",
    "AZURE_OPENAI_BASE": "Azure OpenAI Endpoint",
    "AZURE_OPENAI_VERSION": "API Version",
    "AZURE_OPENAI_DEPLOYMENT_NAME": "Deployment Name"
}

all_set = True
for var_name, description in required_vars.items():
    value = os.getenv(var_name)
    if value:
        # Show only first and last 10 chars for sensitive data
        if "KEY" in var_name:
            display_value = f"{value[:10]}...{value[-10:]}"
        else:
            display_value = value
        print(f"   ✓ {var_name}: {display_value}")
    else:
        print(f"   ✗ {var_name}: NOT SET")
        all_set = False

print()

# Check openai package
print("3. Checking openai package...")
try:
    from openai import AzureOpenAI
    print("   ✓ openai package is installed")
    print(f"   ✓ AzureOpenAI class is available\n")
except ImportError as e:
    print(f"   ✗ openai package not installed: {e}")
    print("   Install with: pip install openai>=1.0.0\n")
    all_set = False

# Check azure_ai module
print("4. Checking azure_ai module...")
try:
    from mapping.mapping_engine.azure_ai import AZURE_AVAILABLE, _get_client
    print(f"   AZURE_AVAILABLE: {AZURE_AVAILABLE}")
    
    if AZURE_AVAILABLE:
        print("   ✓ Azure OpenAI is available")
        
        # Try to get client
        client = _get_client()
        if client:
            print("   ✓ Azure OpenAI client created successfully\n")
        else:
            print("   ✗ Failed to create Azure OpenAI client\n")
            all_set = False
    else:
        print("   ✗ Azure OpenAI is not available")
        print("   Reason: Missing credentials or openai package\n")
        all_set = False
        
except Exception as e:
    print(f"   ✗ Error checking azure_ai module: {e}\n")
    all_set = False

# Summary
print("=" * 70)
if all_set:
    print("✓ AZURE OPENAI IS PROPERLY CONFIGURED")
    print("=" * 70)
    print("\nNext steps:")
    print("1. Run: python -m streamlit run streamlit_app/app.py")
    print("2. Upload an Excel file")
    print("3. Azure API should be used for intelligent column matching")
else:
    print("✗ AZURE OPENAI CONFIGURATION ISSUES DETECTED")
    print("=" * 70)
    print("\nFix steps:")
    print("1. Check if .env file exists and has correct values")
    print("2. Install openai: pip install openai>=1.0.0")
    print("3. Set AZURE_OPENAI_KEY, AZURE_OPENAI_BASE, AZURE_OPENAI_DEPLOYMENT_NAME")
    print("4. Restart the app")

print("=" * 70)
