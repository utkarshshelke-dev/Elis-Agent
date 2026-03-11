# IQC Agent — Google ADK

Investor Qualification Conversation agent built on Google ADK and Vertex AI Agent Engine.

---

## Folder Structure

```
iqc_project/
├── agent.py                    # ADK entry point — root_agent registered here
├── main.py                     # FastAPI server (alternative deployment path)
├── requirements.txt
├── .env.example                # Copy to .env and fill in secrets
├── pytest.ini
│
├── config/
│   ├── __init__.py
│   └── settings.py             # Pydantic BaseSettings — reads .env or env vars
│
├── data/
│   ├── __init__.py
│   ├── engine.py               # SQLAlchemy engine factory (lru_cache singleton)
│   ├── repository.py           # PostgresRepo — all SQL lives here (ACID writes)
│   └── schemas.py              # Pydantic I/O models + domain constants
│
├── services/
│   ├── __init__.py
│   ├── exceptions.py           # IQCBaseException hierarchy
│   ├── logging_service.py      # Central rotating-file + console logging
│   ├── llm_service.py          # LLMClient Protocol + StaticLLMClient
│   ├── scoring_service.py      # Gemini + deterministic fallback scorer
│   ├── pipeline_service.py     # 7-agent ADK pipeline (SequentialAgent)
│   └── a2a_handshake.py        # A2A handshake handler (IQC ↔ IR)
│
├── prompts/
│   ├── __init__.py
│   └── system_prompts.py       # Field metadata, question templates, builder fns
│
├── ir_domain_agent/
│   ├── __init__.py
│   └── agent.py                # IR Domain Agent (calls IQC via Agent Engine API)
│
├── sql/
│   └── schema.sql              # PostgreSQL DDL for all required tables
│
├── logs/                       # Created at runtime by logging_service
│
└── tests/
    ├── __init__.py
    ├── unit/
    │   ├── __init__.py
    │   ├── test_repository.py
    │   ├── test_scoring_service.py
    │   ├── test_pipeline.py
    │   └── test_a2a_handshake.py
    └── bdd/
        ├── __init__.py
        ├── features/
        │   └── investor_qualification.feature
        └── test_investor_qualification_steps.py
```

---

## Quick Start

### 1. Install dependencies

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Configure environment

```bash
cp .env.example .env
# Fill in DB_HOST, DB_PORT, DB_USER, DB_PASS, DB_NAME, GOOGLE_CLOUD_PROJECT
```

### 3. Set up the database

```bash
psql -h $DB_HOST -U $DB_USER -d $DB_NAME -f sql/schema.sql
```

### 4. Authenticate with Google Cloud

```bash
gcloud auth application-default login
gcloud config set project $GOOGLE_CLOUD_PROJECT
```

### 5a. Run with ADK web UI

```bash
adk web
```

### 5b. Run with FastAPI

```bash
uvicorn main:app --host 0.0.0.0 --port 8080 --reload
```

### 5c. Run as ADK API server

```bash
adk api_server
```

---

## Pipeline Architecture

The IQC pipeline is a `SequentialAgent` wrapping 7 specialised sub-agents:

| # | Agent | Responsibility |
|---|-------|---------------|
| 1 | `FounderCheckAgent` | DB user-type check; block founders |
| 2 | `FetchContextAgent` | Load investor profile from DB (Turn 1 only) |
| 3 | `ExtractFromPromptAgent` | Gemini + rule-based field extraction |
| 4 | `AnalyseAgent` | Score profile (Gemini + deterministic fallback) |
| 5 | `QuestionAgent` | Pick next unanswered question |
| 6 | `SaveCollectedAgent` | Write to DB when threshold met (ACID) |
| 7 | `FinalizeAgent` | Emit human-readable response text |

---

## Running Tests

```bash
# All tests
pytest

# Unit tests only
pytest tests/unit/ -v

# BDD tests only
pytest tests/bdd/ -v

# With coverage
pytest --cov=. --cov-report=term-missing
```

---

## Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `DB_HOST` | Yes | localhost | PostgreSQL host |
| `DB_PORT` | No | 5432 | PostgreSQL port |
| `DB_USER` | No | postgres | Database user |
| `DB_PASS` | **Yes** | — | Database password |
| `DB_NAME` | No | grid_os_poc | Database name |
| `GOOGLE_CLOUD_PROJECT` | Yes | — | GCP project ID |
| `GOOGLE_CLOUD_LOCATION` | No | us-central1 | Vertex AI region |
| `VERTEX_MODEL` | No | gemini-2.0-flash | Gemini model |
| `IQC_LOG_LEVEL` | No | INFO | Logging level |
| `IQC_LOG_DIR` | No | logs | Log file directory |
| `PORT` | No | 8080 | HTTP server port |

---

## Standards Compliance

| Standard | Implementation |
|----------|---------------|
| **SRP** | Each agent class has exactly one responsibility |
| **OCP** | Add new fields to `ESSENTIAL_FIELDS` list without modifying agents |
| **DIP** | `PostgresRepo` injected via constructor — never created inside agents |
| **ACID Atomicity** | `engine.begin()` used for all writes (auto-rollback on error) |
| **ACID Isolation** | `SELECT ... FOR UPDATE` inside write transactions |
| **Repository Pattern** | All SQL in `PostgresRepo` — services never write raw SQL |
| **Pydantic Schemas** | All I/O models validated via `data/schemas.py` |
| **Central Logging** | `setup_logging()` in `services/logging_service.py` |
| **Exception Hierarchy** | `IQCBaseException` → domain-specific subclasses |
| **No Hardcoded Secrets** | All credentials via Pydantic `BaseSettings` / env vars |
