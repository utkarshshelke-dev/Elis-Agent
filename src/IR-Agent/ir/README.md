# IR Domain Agent — Google ADK

Investor Relations entry-point agent built on Google ADK and Vertex AI Agent Engine.
Detects investor intent, manages PostgreSQL-backed sessions, and routes qualifying
conversations to the IQC Agent Engine.

---

## Project Structure

```
ir_domain_agent/
├── agent.py                    # ADK entry point — root_agent defined here
│                               # Three tools: get_or_create_session,
│                               #              route_to_iqc, close_session
├── requirements.txt
├── .env                        # Real credentials — git-ignored, never commit
├── .env.example                # Template — safe to commit
├── pytest.ini
│
├── config/
│   ├── __init__.py
│   └── settings.py             # Pydantic BaseSettings — reads .env / env vars
│                               # No hardcoded secrets; DB_PASS must be set
│
├── data/
│   ├── __init__.py
│   ├── repository.py           # IRSessionRepository — ALL SQL lives here
│   │                           # DELETE + INSERT (not ON CONFLICT) for
│   │                           # REPLICA IDENTITY FULL safety
│   └── schemas.py              # Pydantic models: IRSession, ChatTurn,
│                               #   SessionResult, RouteResult
│
├── services/
│   ├── __init__.py
│   ├── exceptions.py           # IRBaseException hierarchy
│   ├── iqc_client.py           # IQCClient — all HTTP to IQC Agent Engine
│   │                           # create_session, stream_query,
│   │                           # build_context, get_token
│   └── logging_service.py      # setup_logging() / get_logger()
│                               # Rotating file + console, idempotent
│
├── sql/
│   └── schema.sql              # PostgreSQL DDL for both session tables
│
├── logs/                       # Created at runtime by logging_service
│
└── tests/
    ├── __init__.py
    └── unit/
        ├── __init__.py
        ├── test_agent_tools.py # Tests for all three ADK tool functions
        ├── test_iqc_client.py  # Tests for IQCClient HTTP calls
        ├── test_repository.py  # Tests for IRSessionRepository SQL ops
        └── test_schemas.py     # Tests for Pydantic model behaviour
```

---

## Architecture

### Conversation Flow

```
User → IR Domain Agent (ADK)
           ├── get_or_create_session(user_id)
           │       └── PostgreSQL: ir_active_sessions
           │               ├── Expired?  → archive → fresh session
           │               ├── History?  → restore → resume
           │               ├── Active?   → resume with last question
           │               ├── Qualified? → return status
           │               └── New?      → create row
           │
           ├── route_to_iqc(user_id, message)
           │       ├── PostgreSQL: load session
           │       ├── IQC Agent Engine: streamQuery
           │       │       └── Vertex AI: us-central1-aiplatform.googleapis.com
           │       │               └── reasoningEngines/6728420724245004288
           │       ├── Capture iqc_session_id (first call only)
           │       ├── Strip __SESSION__ marker
           │       └── PostgreSQL: upsert updated session + new turn
           │
           └── close_session(user_id)
                   ├── PostgreSQL: INSERT into ir_session_history
                   └── PostgreSQL: DELETE from ir_active_sessions
```

### Session State Machine

```
          new_user
             │
             ▼
           open ──────────────────────────────────────────────── expired
             │                                                       │
             │ route_to_iqc (turn 0)                      archive_and_delete
             ▼                                                       │
        qualifying ──► qualified                                    (new)
             │              │
             │ close_session │ close_session
             ▼              ▼
          (history)      (history)
```

### Why DELETE + INSERT (not ON CONFLICT)?

`ir_active_sessions` has `REPLICA IDENTITY FULL` for logical replication (CDC/Pub-Sub).
`UPDATE` on a replicated table can produce unexpected CDC events. `DELETE + INSERT`
within a single transaction is the safest pattern for this setup.

---

## Quick Start

### 1. Install dependencies

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Configure environment

The `.env` file is already populated with the real database credentials.
To verify:

```bash
cat .env
```

### 3. Set up the database

```bash
psql -h 34.69.99.159 -U postgres -d grid_os_poc -f sql/schema.sql
```

### 4. Authenticate with Google Cloud

```bash
gcloud auth application-default login
gcloud config set project the-grid-os
```

### 5a. Run with ADK web UI (recommended for development)

```bash
adk web
```

Open http://localhost:8000 in your browser.

### 5b. Run as ADK API server

```bash
adk api_server
```

### 5c. Deploy to Vertex AI Agent Engine

```bash
# Using the ADK CLI
adk deploy agent_engine \
  --project=the-grid-os \
  --region=us-central1 \
  --display_name="IR Domain Agent"
```

---

## Running Tests

```bash
# All tests
pytest

# Verbose with coverage
pytest tests/ -v --cov=. --cov-report=term-missing

# Single test module
pytest tests/unit/test_agent_tools.py -v
```

---

## Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `GOOGLE_CLOUD_PROJECT` | Yes | `the-grid-os` | GCP project ID |
| `GOOGLE_CLOUD_LOCATION` | No | `us-central1` | Vertex AI region |
| `GOOGLE_GENAI_USE_VERTEXAI` | No | `true` | Use Vertex AI backend |
| `DB_HOST` | No | `34.69.99.159` | PostgreSQL host |
| `DB_PORT` | No | `5432` | PostgreSQL port |
| `DB_USER` | No | `postgres` | Database user |
| `DB_PASS` | **Yes** | — | Database password |
| `DB_NAME` | No | `grid_os_poc` | Database name |
| `SESSION_TTL` | No | `3600` | Session expiry (seconds) |
| `LOG_LEVEL` | No | `INFO` | Logging level |

---

## Database Tables

Both tables have `REPLICA IDENTITY FULL` for logical replication.

### `ir_active_sessions`

Holds one row per active investor conversation. Rows are `DELETE + INSERT`
(never `UPDATE`) and are moved to history on close or expiry.

| Column | Type | Description |
|--------|------|-------------|
| `user_id` | UUID PK | Investor UUID |
| `session_id` | UUID | IR session UUID |
| `iqc_session_id` | TEXT | IQC Agent Engine session ID |
| `status` | VARCHAR(20) | `open`, `qualifying`, `qualified`, `closed`, `expired` |
| `started_at` | TIMESTAMPTZ | Session creation time |
| `turn_number` | INTEGER | Number of completed turns |
| `chat_history` | JSONB | Array of `{turn, user_message, iqc_response, timestamp}` |
| `updated_at` | TIMESTAMPTZ | Last upsert time |

### `ir_session_history`

Archive of all closed and expired sessions. Never updated — always freshly
`INSERT`ed. `load_history()` selects the most recent row by `inserted_at DESC`.

| Column | Type | Description |
|--------|------|-------------|
| `id` | BIGSERIAL PK | Auto-increment row ID |
| `session_id` | UUID | Original IR session UUID |
| `user_id` | UUID | Investor UUID |
| `iqc_session_id` | TEXT | IQC session ID at close time |
| `started_at` | TIMESTAMPTZ | When session started |
| `ended_at` | TIMESTAMPTZ | When session was closed/expired |
| `end_reason` | VARCHAR(20) | `exit`, `expiry`, `qualified` |
| `turns` | JSONB | Full `chat_history` array |
| `final_status` | VARCHAR(20) | Status at archive time |
| `inserted_at` | TIMESTAMPTZ | Archive row insert time (used for ordering) |

---

## Standards Applied

| Standard | Implementation |
|----------|---------------|
| **SRP** | `agent.py` handles ADK tool routing only; no SQL, no HTTP |
| **DIP** | `IRSessionRepository` injected as `_repo` singleton; never instantiated inside tools |
| **Repository Pattern** | All SQL in `data/repository.py`; tools call `_repo.*` only |
| **Pydantic Schemas** | `IRSession`, `ChatTurn` validate all session data |
| **Central Logging** | `setup_logging()` called once at module load; all modules use `get_logger(__name__)` |
| **Exception Hierarchy** | `IRBaseException` → domain-specific subclasses in `services/exceptions.py` |
| **No Hardcoded Secrets** | All credentials via Pydantic `BaseSettings` / env vars |
| **Idempotent Setup** | `setup_logging()` is a no-op on subsequent calls |
| **Replication-Safe Writes** | `DELETE + INSERT` instead of `ON CONFLICT UPDATE` for CDC safety |
| **Graceful Degradation** | IQC session creation failure falls back to context-string approach |
