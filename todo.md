# Sarvantaryami Improvement Plan

**Workflow Rule**: Address issues **one by one**. After completing each task, **stop and request user review** before proceeding.

## Priority 0: Renaming & Restructuring (MVC Architecture)
- [x] **Project Renaming**:
  - [x] Rename project root/package from `finassist` to `sarvantaryami`.
  - [x] Update all internal code references.
- [ ] **Architecture Scaffolding (based on `fm-iss`)**:
  - [x] **Create Directory Structure**:
    - `domain/`: Pydantic models (DTOs) and interfaces.
    - `infrastructure/`: Database setup (`database.py` using `AsyncSession` for Postgres) and Repositories.
    - `adapters/`: External interactions.
      - `agents/`: Moved `services/*_agent.py` here.
    - `usecase/`: Business logic layer.
    - `web/`: FastAPI routes (`routers/`) and dependencies.
  - [x] **Implement Dependency Injection**:
    - [x] Create `web/dependencies.py` (mimic `fm-iss`) to inject Usecases/Repos.
    - [x] Refactor `main.py` and routers to use `Depends`.

## Priority 1: Git & GitHub Setup
- [ ] **Git Initialization**:
  - [ ] Initialize git repository.
  - [ ] Update `.gitignore` to exclude `fm-iss/`, `__pycache__/`, `venv/`, `ollama_data`, `qdrant_data`.
  - [ ] Commit code and push to GitHub.

## Priority 2: Core Agent Reliability (Critical Feedback)
- [ ] **Fix API Agent (`api_agent.py`)**:
  - *Symptom*: Agent identifies the correct API operation but fails to invoke it.
  - *Action*: Replace with a custom ReAct/Tool-calling loop that handles specific path params and invokes correctly.
- [ ] **Fix Orchestrator (`lc_agent.py`)**:
  - *Symptom*: Semantic search disabled due to insufficient prompts.
  - *Action*: Enable `semantic_search`, enrich prompts/examples for all intents (SQL/API/RAG), and tune thresholds.
- [ ] **Fix RAG Agent (`rag_agent.py` & `upload.py`)**:
  - *Symptom*: Inconsistent RAG queries and slow upload.
  - *Action*: Optimize `upload_doc` (async/chunking) and debug retrieval consistency.

## Priority 3: Stability & Configuration
- [ ] **Externalize Configuration**:
  - *Action*: Create `config.py` (Pydantic Settings) reading from `.env`. Ensure Docker env vars are used.
- [ ] **Add Resilience**:
  - *Action*: Add `tenacity` retries for LLM and API calls.

## Priority 4: Documentation (Updated)
- [ ] **Update `readme.md`**:
  - **Project Name**: **Sarvantaryami**.
  - **Name Derivation**: Explain "Sarva" (All) + "Antaryami" (Inner Controller/Private).
  - **Vision**: "AI Swiss Army Knife" for Enterprise (OpenAPI + SQL + RAG).
  - **Enterprise/Offline Focus**: Local LLM (Ollama), plug-and-play.
  - **Architecture**: MVC/Adapters explanation.
  - **Deployment & Testing**: `docker-compose` and `fm-iss` usage.
  - **License**: Add details.

## Priority 5: Code Quality & Bugs
- [ ] Fix `chatbot.py` typo (`str{e}`).
- [ ] Fix `sql_agent.py` f-string quoting.
- [ ] Standardize logging.
