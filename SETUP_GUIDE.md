# Setup Guide - Azure OpenAI Integration & File Caching

## Overview
This guide explains how to:
1. Configure Azure OpenAI for intelligent column mapping support
2. Set up automatic file caching for repeated uploads
3. Understand the logging system

---

## 1. Azure OpenAI Setup

### Step 1: Create a `.env` file
Copy and rename `.env.example` to `.env` in the project root:

```bash
cp .env.example .env
```

### Step 2: Get Azure OpenAI Credentials
1. Go to [Azure Portal](https://portal.azure.com)
2. Create or access your Azure OpenAI resource
3. Navigate to **Keys and Endpoint** section
4. Copy the following information:
   - **API Key**: Primary or Secondary key
   - **Endpoint**: REST API endpoint URL
   - **API Version**: Usually `2024-02-15-preview` (or latest)
   - **Deployment Name**: Your model deployment name (e.g., `gpt-4`, `gpt-35-turbo`)

### Step 3: Update `.env` file
Fill in your credentials:

```env
AZURE_OPENAI_API_KEY=your_actual_api_key_here
AZURE_OPENAI_ENDPOINT=https://your-resource-name.openai.azure.com/
AZURE_OPENAI_API_VERSION=2024-02-15-preview
AZURE_OPENAI_DEPLOYMENT_NAME=your_deployment_name_here
```

### Step 4: Install Required Packages
```bash
pip install -r mapping/requirements.txt
```

### Step 5: Verify Setup
Run the Streamlit app to check if Azure OpenAI is configured:

```bash
streamlit run streamlit_app/app.py
```

Look for the sidebar message:
- ✓ **Azure OpenAI: Active** (Green)
- ⚠️ **Azure OpenAI: Not configured** (Orange)

---

## 2. File Caching Feature

### How It Works

**First Upload:**
- File is processed and matched against all schemas
- Mappings are calculated and stored in `file_mappings_cache.db`
- Results are cached with file hash (name + size based)

**Subsequent Uploads (Same File):**
- System detects the file as previously processed
- Shows: "🎯 Cache Hit! Found previous mappings for this file."
- Automatically applies all previously accepted mappings
- Saves processing time (95% faster)
- Tracking: Shows upload count and last seen timestamp

### Cache Storage
Database: `file_mappings_cache.db`
```
Tables:
- file_cache: Tracks files and their metadata
- file_schema_mappings: Stores mappings per file+schema combo
```

### Viewing Cache Statistics
Look at the sidebar under **🤖 AI Support**:
- **Files Cached**: Total unique files in cache
- **Schema Mappings**: Total mapping sets saved
- **Cache Hits**: Number of times cache was used

### Clearing Cache (if needed)
```python
from mapping.mapping_engine.file_cache import clear_file_cache
clear_file_cache()
```

---

## 3. AI-Powered Mapping Improvements

### What Azure OpenAI Does

**Semantic Analysis:**
- Analyzes column names semantically
- Understands business context (e.g., "Customer ID" → "CustomerID")
- Validates data type compatibility

**Confidence Enhancement:**
- Provides reasoning for each mapping suggestion
- Rates confidence 0-100%
- Identifies ambiguous cases

**Ambiguity Resolution:**
- When multiple columns could match, AI breaks ties
- Considers data samples for validation

### How Mappings Are Classified

| Type | Confidence | Action |
|------|-----------|--------|
| **Auto** | ≥80% | Automatically applied |
| **AI Review** | 70-80% | Shown for verification |
| **Manual** | <70% | Requires user decision |

---

## 4. Logging & Auditing

### Log Files Location
```
logs/
├── mapping_changes.db (SQLite - detailed logs)
└── streamlit_app.log (Optional - app logs)
```

### What Gets Logged

1. **File Processing**
   - File uploaded, hash calculated
   - Cache hit/miss
   - Processing time

2. **Mappings**
   - Each auto-matched mapping (≥80%)
   - Each accepted mapping (user review)
   - Each manual mapping
   - AI confidence scores

3. **Memory Operations**
   - Mappings saved to memory
   - Previous suggestions used
   - Memory statistics

4. **Cache Operations**
   - Files cached
   - Cache hits
   - Cache clears

### Viewing Logs
Use the **Logs Viewer** page in Streamlit:
- Navigate to "logs viewer" in sidebar
- Filter by: File, Mapping Type, or Statistics
- Export for analysis

---

## 5. Troubleshooting

### Azure OpenAI Not Connecting
- **Check:** `.env` file exists in project root
- **Verify:** All required keys are filled correctly
- **Test:** `python -c "import os; from dotenv import load_dotenv; load_dotenv(); print(os.getenv('AZURE_OPENAI_API_KEY')[:10])"`

### File Cache Not Working
- **Check:** `file_mappings_cache.db` exists in project root
- **Clear:** Delete `file_mappings_cache.db` to reset cache
- **Verify:** File name and size haven't changed

### Slow Processing
- **First upload:** Expected (runs full matching)
- **Subsequent uploads:** Should be instant (from cache)
- **Mappings not cached:** Check if mappings were saved (look for success message)

---

## 6. Best Practices

✅ **Do:**
- Keep `.env` file with actual credentials (don't commit to Git)
- Regularly review cached mappings for accuracy
- Use the Mapping Memory feature alongside caching
- Check logs for audit trail

❌ **Don't:**
- Commit `.env` file to version control
- Share `.env` with team members directly
- Modify `file_mappings_cache.db` manually
- Delete cache without backing up important files

---

## 7. Performance Metrics

With Azure OpenAI + File Caching:

| Scenario | Time | Status |
|----------|------|--------|
| First upload (new file) | 10-15 sec | Full processing |
| Cache hit (same file) | 0.5-1 sec | Instant recall |
| Memory suggestion (seen mapping) | 1-2 sec | Fast inference |
| Auto-matched (≥80%) | 0 sec | Pre-applied |

**Result:** Complex files matched in seconds, not minutes!

---

For questions or issues, check the logs or contact your IT team.
