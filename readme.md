# Sarvantaryamin

**Sarvāntaryāmin** (सर्वान्तर्यामिन्) is derived from:
- **Sarva** (सर्व): *Everything* or *All*.
- **Antar** (अन्तः): *Inside* or *Within*.
- **Yāmin** (यामि): *Controller*, *Guide*, or *Mover* (from root *yam*).

It translates to **"The Inner Controller of Everything"** or *"One who controls everything from within"*. In philosophy, it refers to the all-pervading universal Self that dwells within, guiding all thoughts and actions.

Sarvantaryamin is an "AI Swiss Army Knife" for Enterprise, designed to run fully offline/locally using Ollama. It serves as a private, secure, and intelligent interface to your enterprise data and services.

## Vision

To provide a secure, local-first AI agent that can seamlessly interact with:
1.  **SQL Databases**: Querying structured business data.
2.  **APIs**: Invoking enterprise services via OpenAPI specifications.
3.  **Documents (RAG)**: Answering questions from technical PDFs, docs, and standards.

## Architecture

The project follows a clean **MVC (Model-View-Controller)** architecture with **Hexagonal/Clean Architecture** principles:

-   **`web/` (Primary Adapter)**: FastAPI entry points, routers, and dependencies.
-   **`usecase/` (Application Layer)**: Business logic and orchestration of agents.
-   **`domain/` (Domain Layer)**: Core entities and interfaces.
-   **`adapters/` (Secondary Adapters)**:
    -   **`agents/`**: specialized AI agents (SQL, API, RAG).
    -   **`infrastructure/`**: Database connections, Configuration.

## Prerequisites

-   **Docker & Docker Compose**: Recommended for running the full stack.
-   **Ollama**: Installed locally with required models (see Model Requirements below).

## Model Requirements

Sarvantaryami uses **two types of models** for optimal performance:

| Model Type | Purpose | Used By |
|------------|---------|---------|
| **LLM (Chat)** | SQL generation, API reasoning, RAG answering, general queries | All agents |
| **Embeddings** | Intent routing, document retrieval, semantic search | Router, RAG Agent |

### Local Development (Mac M2/M3, 16-32GB RAM)

| Component | Model | Size | Command |
|-----------|-------|------|---------|
| **LLM** | `llama3.2:3b` | ~2GB | `ollama pull llama3.2:3b` |
| **Embeddings** | `nomic-embed-text` | ~274MB | `ollama pull nomic-embed-text` |

**Why these models?**
- Fast inference on Apple Silicon (~20-40 tok/s)
- Low memory footprint, leaves room for other services
- Good enough accuracy for testing all 4 use cases (SQL, API, RAG, General)

### Production (Medium Enterprise, 32GB+ RAM, optional GPU)

| Component | Model | Size | Command |
|-----------|-------|------|---------|
| **LLM** | `llama3.1:8b-instruct` | ~5GB | `ollama pull llama3.1:8b-instruct` |
| **Embeddings** | `nomic-embed-text` | ~274MB | `ollama pull nomic-embed-text` |

**Hardware Recommendation:**
- **Minimum**: 32GB RAM, no GPU (CPU inference ~5-10 tok/s)
- **Recommended**: 32GB RAM + RTX 4060 Ti 16GB (~$400) for 25+ tok/s
- **Optimal**: 64GB RAM + RTX 4080 16GB (~$1000) for 50+ tok/s

**Why Llama 3.1 8B?**
- 128K context window (excellent for long PDFs in RAG)
- Superior instruction following and reasoning
- Enterprise-proven, well-tested

## Quick Start (Docker)
The easiest way to run Sarvantaryamin is via Docker Compose.

1.  **Pull Required Models**:
    ```bash
    # For local development
    ollama pull llama3.2:3b
    ollama pull nomic-embed-text
    ```

2.  **Configure Environment**:
    Create a `.env` file in the root directory.
    ```bash
    cp .env.example .env
    ```
    Set `DB_URI` to point to your target database.

3.  **Run with Docker**:
    The `docker-compose.yml` builds the service using `Dockerfile.agent` (named `agent_service` in compose).
    ```bash
    docker compose up -d
    ```
    This will start:
    -   **Ollama Service** (Local LLM)
    -   **Qdrant** (Vector Store)
    -   **Agent Service** (The Sarvantaryamin Agent App)

## Configuration

Configuration is managed in `infrastructure/config.py` and sourced from `.env`.

| Variable | Description | Default |
|----------|-------------|---------|
| `LLM_MODEL` | Chat/reasoning model name | `llama3.2:3b` |
| `EMBEDDING_MODEL` | Embedding model name | `nomic-embed-text` |
| `DB_URI` | Database connection string | `postgresql+psycopg2://...` |
| `OLLAMA_BASE_URL` | Ollama server URL | `http://localhost:11434` |
| `QDRANT_HOST` | Qdrant vector DB host | `localhost` |

## Development Setup (Testing)

If you need a test database and services to validate the agents, this project includes a reference setup in `pg_service/`.

**To start the test environment (Infrastructure):**
```bash
cd pg_service
docker compose up -d
```
This spins up a complete ecosystem with Postgres (`entity_service`), Keycloak, etc., which the Agent can be configured to interact with for testing purposes.

**Minimal Setup (Entity Service only):**
```bash
cd pg_service
docker compose up -d entity_db_pg_service entity_pg_service kc_pg_service kc_db_pg_service kafka_pg_service zk_pg_service
```

## Usage

**Interactive API Documentation**: `http://localhost:8010/docs` (port 8010 for Docker/local).

### Capabilities
-   **Agent Interaction**: `POST /api/v1/agent/ask` - Main entry point.
    -   *"Show me all countries in the database"* → SQL Agent
    -   *"Get currency details for USD"* → API Agent  
    -   *"How does the ISO 8583 protocol work?"* → RAG Agent (after uploading docs)
    -   *"Hello, what can you do?"* → General LLM

-   **Document Upload**: `POST /api/v1/agent/upload_doc` - Upload PDFs/Text for RAG.

