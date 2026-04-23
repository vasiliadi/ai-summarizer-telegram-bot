# Project Structure

## Directory Tree

```
project-root/
├── AGENTS.md                          ← Core instructions (read every session)
├── templates/                         ← Summary and handoff templates
├── src/                               ← Main application code
│   ├── main.py                       # Bot entry point and command handlers
│   ├── config.py                     # Configuration and settings
│   ├── database.py                   # Database operations
│   ├── handlers.py                   # Message type handlers
│   ├── services.py                   # Business logic services
│   ├── models.py                     # SQLAlchemy models
│   ├── prompts.py                    # AI prompt templates
│   ├── transcription.py              # Audio transcription logic
│   ├── summary.py                    # Summarization logic
│   ├── download.py                   # Media download utilities
│   ├── utils.py                      # Helper functions
│   └── exceptions.py                 # Custom exceptions
├── tests/                            ← Unit and integration tests
│   ├── conftest.py                   # Shared fixtures
│   ├── test_commands.py
│   ├── test_database.py
│   ├── test_download.py
│   ├── test_handlers.py
│   ├── test_services.py
│   ├── test_state.py
│   ├── test_summary.py
│   ├── test_transcription.py
│   └── test_utils.py
├── migrations/                       ← Alembic database migrations
├── scripts/                          ← Utility scripts
│   ├── db.py                        # Database initialisation
│   └── cron.py                      # Modal cron job (rate limit reset)
├── docs/                             ← Documentation
│   ├── context/                      ← Reusable domain knowledge
│   ├── summaries/                    ← Session state and handoffs
│   └── archive/                      ← Processed raw files
├── pyproject.toml                    ← Project configuration
├── alembic.ini                      ← Migration configuration
├── Dockerfile                       ← Container definition
└── compose.yaml                     ← Docker Compose setup
```

## New Project Scaffold

```bash
mkdir -p src tests migrations scripts docs/context docs/summaries docs/archive templates
```
