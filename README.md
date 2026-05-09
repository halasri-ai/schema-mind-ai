# SchemaMind AI

AI-powered enterprise Excel header mapping platform using semantic matching, Azure OpenAI, mapping memory, and intelligent ambiguity resolution.

---

# Overview

SchemaMind AI is an enterprise-grade intelligent schema mapping platform designed to automate Excel and CSV header standardization workflows.

The platform automatically maps inconsistent file headers against standardized schemas using:
- semantic similarity matching,
- AI-powered reasoning,
- confidence scoring,
- mapping memory,
- and human-in-the-loop validation.

This significantly reduces manual mapping effort in enterprise ETL and data ingestion workflows.

---

# Problem Statement

Organizations receive Excel and CSV files from multiple vendors, departments, and systems where column names differ significantly despite representing the same data.

Example:

| Incoming Header | Standardized Schema |
|---|---|
| Emp ID | Employee_ID |
| Cust Mail | Customer_Email |
| Ticket No | Incident_Number |
| Open Dt | Created_Date |

Manual mapping:
- consumes time,
- introduces human errors,
- slows enterprise workflows,
- and becomes difficult to scale.

Traditional rule-based systems fail to handle:
- abbreviations,
- semantic similarities,
- inconsistent naming conventions,
- and evolving schemas.

---

# Solution

SchemaMind AI solves this problem using a hybrid AI-assisted mapping engine that combines:
- semantic similarity scoring,
- Azure OpenAI reasoning,
- ambiguity resolution,
- reusable mapping memory,
- confidence evaluation,
- and human review workflows.

The system continuously improves mapping accuracy through reusable learned mappings.

---

# Core Features

## AI-Powered Semantic Mapping
Uses Azure OpenAI to understand semantic relationships between column names.

## Multi-Schema Support
Matches uploaded files against multiple enterprise schemas.

## Intelligent Ambiguity Resolution
Resolves uncertain mappings using heuristic and semantic analysis.

## Mapping Memory
Learns from previously approved mappings and reuses them automatically.

## Confidence Scoring
Displays mapping confidence levels for transparent validation.

## Human-in-the-Loop Validation
Allows users to review and correct mappings before final approval.

## File Cache Optimization
Avoids reprocessing previously uploaded files.

## SQLite Logging & Audit Tracking
Stores mapping history and corrections for enterprise traceability.

## Interactive Streamlit UI
Provides a clean interface for uploads, review, and export workflows.

---

# Tech Stack

| Category | Technologies |
|---|---|
| Frontend | Streamlit |
| Backend | Python |
| AI/LLM | Azure OpenAI |
| Data Processing | Pandas, NumPy |
| Database | SQLite |
| File Handling | OpenPyXL |
| Environment | Python Dotenv |

---

# Project Structure

```bash
schema-mind-ai/
│
├── mapping/
├── streamlit_app/
├── requirements.txt
├── README.md
├── .env.example
└── .gitignore
```

---

# Installation

## Clone Repository

```bash
git clone https://github.com/halasri-ai/schema-mind-ai.git
```

## Navigate to Project

```bash
cd schema-mind-ai
```

## Install Dependencies

```bash
pip install -r requirements.txt
```

## Configure Environment Variables

Create a `.env` file using `.env.example`.

---

# Run Application

```bash
streamlit run streamlit_app/app.py
```

---

# Screenshots

## Upload Interface

_Add screenshot here_

---

## Mapping Results

_Add screenshot here_

---

## Mapping Memory

_Add screenshot here_

---

## Logs Viewer

_Add screenshot here_

---

# Architecture Flow

```text
User Upload
    ↓
Schema Detection
    ↓
Similarity Matching
    ↓
Azure OpenAI Semantic Analysis
    ↓
Ambiguity Resolution
    ↓
Confidence Scoring
    ↓
Human Validation
    ↓
Mapping Memory Storage
    ↓
Export
```

---

# Future Enhancements

- Vector database integration
- Embedding-based semantic search
- PostgreSQL migration
- REST API support
- Docker deployment
- AWS cloud deployment
- RAG-powered schema intelligence
- Multi-user authentication

---

# Real-World Use Cases

- Enterprise ETL workflows
- Hospital data standardization
- Vendor onboarding
- ERP integrations
- Banking data migration
- Insurance workflows
- SaaS integrations

---

# Author

## Halasri Konduru

AI Engineering | Workflow Automation | Data Engineering | LLM Applications